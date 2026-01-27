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
- [ ] Set up project structure and dependencies.
- [ ] Implement Georgia Code sync and normalization.
- [ ] Implement CourtListener opinions fetcher (GA Supreme & GA Court of Appeals).
- [ ] Implement Gwinnett Municode fetcher and normalization.
- [ ] Add CLI entrypoint and usage docs.
- [ ] Smoke-run limited fetch to validate output shape.

## Notes
- Respect robots/ToS and add polite delay; allow resume by skipping existing files.
- Prefer JSONL for ingestion; keep raw HTML/PDF where feasible.
