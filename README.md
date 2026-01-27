# law_ai

Fetch Georgia legal sources (state code, appellate opinions, Gwinnett County ordinances) into JSONL for search.

## Setup
```
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Usage
```
python law_fetch.py --out data --courtlistener-limit 200 --sleep 0.5
```

Outputs:
- `data/ga_code.jsonl` – Georgia Code sections (MIT mirror).
- `data/courtlistener_ga.jsonl` – GA Supreme & Court of Appeals opinions (subset by limit).
- `data/municode_gwinnett.jsonl` – Gwinnett ordinances.
