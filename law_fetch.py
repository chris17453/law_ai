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


# --- Georgia Code via openlawlibrary mirror on GitHub (raw JSON already normalized) ---
def fetch_ga_code(output_dir: Path):
    repo_url = "https://raw.githubusercontent.com/openlawlibrary/ga-code/master"
    index_url = f"{repo_url}/index.json"
    resp = requests.get(index_url, timeout=30)
    resp.raise_for_status()
    index = resp.json()
    items = index.get("files", [])
    records = []
    for item in tqdm(items, desc="ga-code"):
        path = item["path"]
        if not path.endswith(".json"):
            continue
        url = f"{repo_url}/{path}"
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        data = r.json()
        sec = data.get("section", {})
        records.append(
            {
                "jurisdiction": "GA",
                "source": "GA_CODE",
                "cite": sec.get("cite"),
                "title": sec.get("name"),
                "structure": {
                    "title": sec.get("title"),
                    "chapter": sec.get("chapter"),
                    "article": sec.get("article"),
                    "part": sec.get("part"),
                    "subpart": sec.get("subpart"),
                },
                "history": sec.get("history"),
                "text": sec.get("text"),
                "source_url": url,
            }
        )
    out = output_dir / "ga_code.jsonl"
    save_jsonl(records, out)
    return out


# --- CourtListener opinions (GA Supreme & Court of Appeals) ---
def fetch_courtlistener(output_dir: Path, court_slugs: List[str], limit: Optional[int], sleep: float):
    base = "https://www.courtlistener.com/api/rest/v3/opinions/"
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
        resp = requests.get(next_url, params=params if next_url == base else None, timeout=30)
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
def fetch_municode_gwinnett(output_dir: Path, sleep: float):
    base = "https://mcclibraryfunctions.azurewebsites.us/api"
    code_id = 13292
    chapters_url = f"{base}/v1/content?municipalCodeId={code_id}"
    resp = requests.get(chapters_url, timeout=30)
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
    out = output_dir / "municode_gwinnett.jsonl"
    save_jsonl(records, out)
    return out


def main():
    parser = argparse.ArgumentParser(description="Fetch Georgia legal sources into JSONL.")
    parser.add_argument("--out", type=Path, default=Path("data"), help="Output directory")
    parser.add_argument("--courtlistener-limit", type=int, default=200, help="Max opinions to fetch")
    parser.add_argument("--sleep", type=float, default=0.5, help="Sleep between paginated requests")
    args = parser.parse_args()

    output_dir = args.out
    ensure_dir(output_dir)

    ga_code_path = fetch_ga_code(output_dir)
    cl_path = fetch_courtlistener(output_dir, ["ga", "gaapp"], args.courtlistener_limit, args.sleep)
    muni_path = fetch_municode_gwinnett(output_dir, args.sleep)

    print("Wrote:", ga_code_path)
    print("Wrote:", cl_path)
    print("Wrote:", muni_path)


if __name__ == "__main__":
    main()
