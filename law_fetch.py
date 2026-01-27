#!/usr/bin/env python3
"""
Fetch Georgia legal sources (Georgia Code, appellate opinions via CourtListener, Gwinnett County ordinances via Municode).

Outputs normalized JSONL plus raw artifacts.
"""
import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional

import requests
from bs4 import BeautifulSoup
from tqdm import tqdm


def ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)


def save_jsonl(records: Iterable[dict], path: Path):
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def slugify(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()


# --- Georgia Code via Law.Resource.Org (Public.Resource.Org) ---
def fetch_ga_code(output_dir: Path, verify: bool = True):
    """Fetch Georgia Code from Law.Resource.Org (Public.Resource.Org bulk archive)."""
    import zipfile
    import tempfile
    from striprtf.striprtf import rtf_to_text

    # Download the most recent OCGA release
    base_url = "https://law.resource.org/pub/us/code/ga"
    zip_filename = "gov.ga.ocga.2019.08.21.release.73.zip"
    zip_url = f"{base_url}/{zip_filename}"

    print(f"Downloading {zip_filename}...")
    resp = requests.get(zip_url, timeout=300, verify=verify, stream=True)
    resp.raise_for_status()

    # Save to temp file
    with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp:
        for chunk in resp.iter_content(chunk_size=8192):
            tmp.write(chunk)
        zip_path = tmp.name

    records = []
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            # Get all title RTF files (title.01 through title.53)
            title_files = [f for f in zf.namelist() if re.match(r'.*\.title\.\d+\.rtf$', f)]

            for filename in tqdm(sorted(title_files), desc="Parsing GA Code"):
                with zf.open(filename) as f:
                    rtf_content = f.read().decode('latin-1', errors='ignore')
                    text = rtf_to_text(rtf_content)

                    # Extract title number from filename
                    title_match = re.search(r'title\.(\d+)\.rtf$', filename)
                    title_num = title_match.group(1) if title_match else "Unknown"

                    # Parse sections using regex
                    # Sections look like: "1-1-1. Section title"
                    section_pattern = re.compile(
                        r'(\d+-\d+-\d+(?:\.\d+)?)\.\s+([^\n]+?)(?:\n\n|\nStatute text\n)',
                        re.MULTILINE
                    )

                    matches = list(section_pattern.finditer(text))
                    for i, match in enumerate(matches):
                        cite = match.group(1)
                        section_title = match.group(2).strip()

                        # Extract text until next section or end
                        start = match.end()
                        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
                        section_text = text[start:end].strip()

                        # Extract statute text (between "Statute text" and "History" or "Annotations")
                        statute_match = re.search(
                            r'Statute text\s+(.*?)(?:\n\nHistory|$)',
                            section_text,
                            re.DOTALL
                        )
                        statute_only = statute_match.group(1).strip() if statute_match else section_text

                        records.append({
                            "jurisdiction": "GA",
                            "source": "GA_CODE",
                            "cite": cite,
                            "title": section_title,
                            "title_num": title_num,
                            "text": statute_only,
                            "source_url": f"{base_url}/{zip_filename}#Title-{title_num}",
                            "release": "2019-08-21-r73"
                        })
    finally:
        os.unlink(zip_path)

    out = output_dir / "ga_code.jsonl"
    save_jsonl(records, out)
    print(f"Parsed {len(records)} Georgia Code sections")
    return out


# --- CourtListener opinions (GA Supreme & Court of Appeals) ---
def fetch_courtlistener(output_dir: Path, court_slugs: List[str], limit: Optional[int], sleep: float, verify: bool = True, api_token: Optional[str] = None):
    """Fetch opinions from CourtListener. Requires API token (get from courtlistener.com/api/)."""
    if not api_token:
        print("WARNING: Skipping CourtListener - requires API token.")
        print("Get a free token from https://www.courtlistener.com/sign-in/")
        print("Then set environment variable: export COURTLISTENER_TOKEN=your-token")
        out = output_dir / "courtlistener_ga.jsonl"
        save_jsonl([], out)
        return out

    base = "https://www.courtlistener.com/api/rest/v3/opinions/"
    headers = {"Authorization": f"Token {api_token}"}
    params = {
        "court__slug": ",".join(court_slugs),
        "order_by": "-date_filed",
        "cluster__has_pdf": "true",
        "page_size": 100,
    }
    records = []
    next_url = base
    fetched = 0
    while next_url:
        resp = requests.get(next_url, params=params if next_url == base else None, headers=headers, timeout=30, verify=verify)
        resp.raise_for_status()
        data = resp.json()
        for result in data.get("results", []):
            if limit and fetched >= limit:
                next_url = None
                break
            cluster = result.get("cluster")
            pdf_url = result.get("pdf_url") or result.get("local_path")
            records.append(
                {
                    "jurisdiction": "GA",
                    "source": "COURTLISTENER",
                    "court": result.get("court"),
                    "slug": result.get("slug"),
                    "cite": result.get("citation"),
                    "docket": result.get("docket_number"),
                    "date": result.get("date_filed"),
                    "source_url": result.get("absolute_url"),
                    "pdf_url": pdf_url,
                    "cluster": cluster,
                    "text": result.get("plain_text"),
                }
            )
            fetched += 1
        next_url = data.get("next")
        if next_url and sleep:
            time.sleep(sleep)
    out = output_dir / "courtlistener_ga.jsonl"
    save_jsonl(records, out)
    return out


# --- Municode Gwinnett ---
def fetch_municode_gwinnett(output_dir: Path, sleep: float, verify: bool = True):
    """Fetch Gwinnett County ordinances from Municode (if API is available)."""
    base = "https://mcclibraryfunctions.azurewebsites.us/api"
    code_id = 13292
    chapters_url = f"{base}/v1/content?municipalCodeId={code_id}"

    out = output_dir / "municode_gwinnett.jsonl"

    try:
        resp = requests.get(chapters_url, timeout=30, verify=verify)
        resp.raise_for_status()
        data = resp.json()
        records = []
        for chapter in tqdm(data.get("children", []), desc="municode chapters"):
            for section in chapter.get("children", []):
                text_html = section.get("content")
                plain = BeautifulSoup(text_html or "", "html.parser").get_text("\n").strip()
                records.append(
                    {
                        "jurisdiction": "GA-Gwinnett",
                        "source": "MUNICODE",
                        "title": chapter.get("title"),
                        "section": section.get("title"),
                        "cite": section.get("path"),
                        "source_url": f"https://library.municode.com/ga/gwinnett_county/codes/code_of_ordinances?nodeId={section.get('path')}",
                        "text": plain,
                        "html": text_html,
                    }
                )
            if sleep:
                time.sleep(sleep)
        save_jsonl(records, out)
        return out
    except requests.exceptions.RequestException as e:
        print(f"WARNING: Municode API failed ({e}). Skipping Gwinnett County ordinances.")
        print("The Municode API endpoint may have changed or requires authentication.")
        print("View ordinances at: https://library.municode.com/ga/gwinnett_county")
        save_jsonl([], out)
        return out


def main():
    parser = argparse.ArgumentParser(description="Fetch Georgia legal sources into JSONL.")
    parser.add_argument("--out", type=Path, default=Path("data"), help="Output directory")
    parser.add_argument("--courtlistener-limit", type=int, default=200, help="Max opinions to fetch")
    parser.add_argument("--courtlistener-token", type=str, help="CourtListener API token (or set COURTLISTENER_TOKEN env var)")
    parser.add_argument("--sleep", type=float, default=0.5, help="Sleep between paginated requests")
    parser.add_argument("--no-verify", action="store_true", help="Disable SSL certificate verification")
    args = parser.parse_args()

    output_dir = args.out
    ensure_dir(output_dir)

    verify_ssl = not args.no_verify
    if not verify_ssl:
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    # Get CourtListener token from args or environment
    cl_token = args.courtlistener_token or os.environ.get("COURTLISTENER_TOKEN")

    ga_code_path = fetch_ga_code(output_dir, verify=verify_ssl)
    cl_path = fetch_courtlistener(output_dir, ["ga", "gaapp"], args.courtlistener_limit, args.sleep, verify=verify_ssl, api_token=cl_token)
    muni_path = fetch_municode_gwinnett(output_dir, args.sleep, verify=verify_ssl)

    print("Wrote:", ga_code_path)
    print("Wrote:", cl_path)
    print("Wrote:", muni_path)


if __name__ == "__main__":
    main()
