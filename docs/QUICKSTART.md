# Law AI - Quick Start Guide

## 🚀 Quick Start (5 minutes)

```bash
# 1. Start the vector database and initialize
make setup

# 2. Fetch Georgia legal data (if not already done)
uv run law_fetch.py --out data --no-verify

# 3. Ingest data into vector database (45-60 min on CPU)
make ingest

# 4. Search!
make search QUERY='murder laws in Georgia'
```

## 📋 Prerequisites

- **Docker** - For running Qdrant vector database
- **Python 3.12+** - With UV package manager
- **8GB+ RAM** - For embedding model
- **~2GB disk space** - For vector database

## 🔧 Installation

### 1. Clone and Setup

```bash
git clone <repo>
cd law_ai

# Install dependencies and start services
make setup
```

This will:
- Install Python dependencies via UV
- Start Qdrant in Docker
- Initialize database collections
- Create SQLite document store

### 2. Fetch Legal Data

```bash
# Fetch Georgia Code, case law, and ordinances
uv run law_fetch.py --out data --no-verify

# Optional: Get CourtListener API token for case law
export COURTLISTENER_TOKEN=your-token
uv run law_fetch.py --out data --courtlistener-limit 500 --no-verify
```

**Output:**
- `data/ga_code.jsonl` - 38,838 Georgia Code sections (101MB)
- `data/courtlistener_ga.jsonl` - GA court opinions (requires token)
- `data/municode_gwinnett.jsonl` - County ordinances (API deprecated)

### 3. Ingest into Vector Database

```bash
# Ingest all sources
make ingest

# Or ingest specific sources
make ingest-ga-code       # Just Georgia Code
make ingest-cases         # Just case law
make ingest-ordinances    # Just ordinances
```

**Time estimates:**
- **CPU**: 45-60 minutes for 38,838 documents
- **GPU (CUDA)**: 10-15 minutes

**What happens:**
- Documents are chunked into 750-word segments
- Each chunk gets 768-dimensional embedding (all-mpnet-base-v2)
- Stored in Qdrant for vector search
- Full text stored in SQLite for retrieval

## 🔍 Searching

### Basic Search

```bash
make search QUERY='speeding violations in Georgia'
```

### Filter by Source

```bash
# Search only statutes
make search-ga QUERY='vehicular homicide'

# Search only case law
make search-cases QUERY='precedents for self defense'
```

### Advanced Search (Python)

```python
from scripts.search import search_vector, load_model
from qdrant_client import QdrantClient

model = load_model()
client = QdrantClient("localhost", port=6333)

results = search_vector(
    query="What are the penalties for DUI?",
    model=model,
    client=client,
    limit=5,
    source_filter="GA_CODE"  # Optional: GA_CODE, COURTLISTENER, MUNICODE
)

for hit in results:
    print(f"{hit.payload['cite']}: {hit.payload['title']}")
    print(f"Score: {hit.score:.4f}")
    print(f"Text: {hit.payload['text'][:200]}...")
    print()
```

## 📊 Monitoring

### Database Statistics

```bash
make stats
```

Output:
```
==============================================================================
 Law AI Database Statistics
==============================================================================

📊 Vector Database (Qdrant)
----------------------------------------
  Total Vectors:  42,156
  Total Points:   42,156
  Status:         ✓ Indexed

📚 Document Store (SQLite)
----------------------------------------
  Total Documents: 38,838
  Total Chunks:    42,156

  Documents by Source:
    📘 GA_CODE         : 38,838

  Searches (24h):  127

  Top Search Queries:
    • "murder laws in Georgia" (15x)
    • "speeding violations" (8x)
```

### Service Status

```bash
make status     # Check if Qdrant is running
make logs       # View Qdrant logs
```

## 📁 Project Structure

```
law_ai/
├── Makefile                    # Command shortcuts
├── docker-compose.yml          # Qdrant service
├── pyproject.toml              # Dependencies
│
├── data/                       # Legal source data (JSONL)
│   ├── ga_code.jsonl          # Georgia Code sections
│   ├── courtlistener_ga.jsonl # Court opinions
│   └── municode_gwinnett.jsonl# County ordinances
│
├── scripts/                    # Main scripts
│   ├── init_db.py             # Initialize databases
│   ├── ingest.py              # Ingest data → vector DB
│   ├── search.py              # Semantic search
│   └── stats.py               # Database statistics
│
├── law_fetch.py               # Fetch legal sources
│
├── qdrant_storage/            # Vector database data
└── law_ai.db                  # SQLite document store
```

## 🛠️ Makefile Commands

### Setup & Management
- `make setup` - Install dependencies and initialize
- `make start` - Start services
- `make stop` - Stop services
- `make restart` - Restart services

### Data Ingestion
- `make ingest` - Ingest all sources
- `make ingest-ga-code` - Ingest GA Code only
- `make ingest-cases` - Ingest case law only

### Search
- `make search QUERY='...'` - Search all sources
- `make search-ga QUERY='...'` - Search GA Code only
- `make search-cases QUERY='...'` - Search case law only

### Monitoring
- `make status` - Service status
- `make stats` - Database statistics
- `make logs` - View logs

### Cleanup
- `make clean` - Remove ALL data and containers
- `make clean-data` - Remove only database data

## 🔬 How It Works

### 1. Document Chunking

Legal documents are split into manageable chunks:
- Max 750 words per chunk
- 75-word overlap between chunks
- Preserves context across boundaries

### 2. Embedding Generation

Each chunk gets a 768-dimensional vector embedding:
- Model: `sentence-transformers/all-mpnet-base-v2`
- Captures semantic meaning
- Enables similarity search

### 3. Vector Search

When you search:
1. Query text → 768-dimensional embedding
2. Find similar vectors in Qdrant (cosine similarity)
3. Return most relevant chunks
4. Optional: Filter by source, jurisdiction, etc.

### 4. Multi-Source Architecture

All sources stored together, filterable by metadata:
- `source: GA_CODE` - Georgia statutes
- `source: COURTLISTENER` - Court opinions
- `source: MUNICODE` - Municipal ordinances

## 🚧 Troubleshooting

### Qdrant won't start

```bash
# Check if port 6333 is in use
lsof -i :6333

# Restart services
make restart
```

### Out of memory during ingestion

```bash
# Reduce batch size in scripts/ingest.py
# Change: batch_size=16 → batch_size=8
```

### Slow search

```bash
# Check if Qdrant is indexed
make status

# Restart if needed
make restart
```

### Missing data

```bash
# Re-fetch legal sources
uv run law_fetch.py --out data --no-verify

# Re-ingest
make clean-data
make setup
make ingest
```

## 🎯 Next Steps

1. **Phase 2**: Add hybrid search (vector + keyword)
2. **Phase 3**: Build AI agent system for complex queries
3. **Phase 4**: Add citation graph analysis
4. **Phase 5**: Build web UI

## 📚 Learn More

- [ARCHITECTURE.md](ARCHITECTURE.md) - Full system design
- [PHASE1_PLAN.md](PHASE1_PLAN.md) - Implementation details
- [EMBEDDING_COMPARISON.md](EMBEDDING_COMPARISON.md) - Why 768 dimensions

## 🤝 Support

Issues? Questions?
- Check the Makefile: `make help`
- Review the logs: `make logs`
- Check database stats: `make stats`
