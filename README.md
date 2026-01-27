# law_ai

Fetch Georgia legal sources (state code, appellate opinions, Gwinnett County ordinances) into JSONL for search.

## Setup
```bash
uv sync
```

## CourtListener API Token (Optional)

To fetch Georgia court opinions, you need a free CourtListener API token:

1. Sign up at https://www.courtlistener.com/sign-in/
2. Get your token from https://www.courtlistener.com/api/
3. Set environment variable: `export COURTLISTENER_TOKEN=your-token-here`

Or pass it via `--courtlistener-token` flag.

## Usage

Basic usage (without CourtListener):
```bash
uv run law_fetch.py --out data --sleep 0.5 --no-verify
```

With CourtListener token:
```bash
export COURTLISTENER_TOKEN=your-token
uv run law_fetch.py --out data --courtlistener-limit 200 --sleep 0.5 --no-verify
```

## Outputs

- `data/ga_code.jsonl` – Georgia Code sections from Law.Resource.Org (38,838 sections)
- `data/courtlistener_ga.jsonl` – GA Supreme & Court of Appeals opinions (requires API token)
- `data/municode_gwinnett.jsonl` – Gwinnett County ordinances

## Data Sources

- **Georgia Code**: [Law.Resource.Org](https://law.resource.org/pub/us/code/ga/) (Public.Resource.Org - public domain)
- **Court Opinions**: [CourtListener API](https://www.courtlistener.com/api/) (Free Law Project - free with registration)
- **Gwinnett Ordinances**: [Municode JSON API](https://library.municode.com/) (public access)
