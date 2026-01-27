# Plan

## Problem
Need free, citable downloads of Georgia authorities (state statutes, appellate opinions) and Gwinnett County ordinances for AI search; store text with citations and source URLs.

## Approach
- Use MIT-licensed `openlawlibrary/ga-code` mirror for statutes.
- Use CourtListener REST API for Georgia Supreme & GA Court of Appeals opinions (metadata + text URLs) as free source.
- Use Municode JSON endpoints for Gwinnett County code.
- Normalize to JSONL (fields: jurisdiction, source, cite, title/section, date, url, text, type) plus raw artifacts.
- Add CLI to run collectors with rate limits and resumable outputs.

## Workplan
- [x] Set up project structure and dependencies (using UV).
- [x] Implement Georgia Code sync and normalization (using Law.Resource.Org bulk archive - 38,838 sections).
- [x] Implement CourtListener opinions fetcher (GA Supreme & GA Court of Appeals) - optional with API token.
- [~] Implement Gwinnett Municode fetcher and normalization (API endpoint deprecated - needs alternative approach).
- [x] Add CLI entrypoint and usage docs.
- [x] Smoke-run limited fetch to validate output shape.

## Notes
- Respect robots/ToS and add polite delay; allow resume by skipping existing files.
- Prefer JSONL for ingestion; keep raw HTML/PDF where feasible.

## Implementation Status

### ✅ Completed
- **Georgia Code**: Successfully fetching from Law.Resource.Org (Public.Resource.Org's bulk archive)
  - Source: 2019-08-21 release (38,838 sections)
  - Format: RTF files parsed to plain text with striprtf library
  - Output: Structured JSONL with cite, title, text, and metadata
  - Free and public domain per Supreme Court ruling

- **CourtListener**: Implemented with optional API token support
  - Requires free API token from courtlistener.com
  - Fetches GA Supreme Court and Court of Appeals opinions
  - Supports environment variable or CLI argument for token

- **Project Setup**: Modern Python tooling with UV
  - Fast dependency management
  - Single command setup (`uv sync`)
  - Clean pyproject.toml configuration

### ⚠️ Needs Work
- **Municode (Gwinnett County)**: API endpoint returned 404
  - May require authentication or endpoint changed
  - Alternative: Could scrape library.municode.com/ga/gwinnett_county
  - Or find alternative source for county ordinances

### 🎯 Next Steps
1. Get CourtListener API token to fetch case law
2. Explore alternative sources for Gwinnett ordinances (web scraping with BeautifulSoup?)
3. Consider adding more Georgia jurisdictions (e.g., Atlanta, Fulton County)
