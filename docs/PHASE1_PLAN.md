# Phase 1: Vector Database Setup & Data Ingestion

## Goal
Ingest 38,838 Georgia Code sections into Qdrant vector database with embeddings for semantic search.

## Architecture Decision: Qdrant vs Alternatives

| Feature | Qdrant | ChromaDB | Weaviate | pgvector |
|---------|--------|----------|----------|----------|
| Setup Complexity | Easy (Docker) | Easiest (Python only) | Medium | Medium (Postgres) |
| Performance | Excellent | Good | Excellent | Good |
| Filtering | Rich | Basic | Rich | SQL-based |
| Scale | Production | Small-Medium | Production | Good |
| Python Client | Native | Native | Native | psycopg2 |
| **Recommendation** | ✅ **BEST** | Development only | Overkill | If using PG already |

**Decision: Qdrant** - Best balance of ease-of-use and production capability.

## Implementation Steps

### Step 1: Environment Setup

**Install dependencies:**
```bash
uv add qdrant-client sentence-transformers torch
```

**Start Qdrant:**
```bash
# Option 1: Docker (recommended)
docker run -p 6333:6333 -p 6334:6334 \
    -v $(pwd)/qdrant_storage:/qdrant/storage:z \
    qdrant/qdrant

# Option 2: Docker Compose (persistent)
# Create docker-compose.yml with Qdrant service

# Option 3: Cloud (later)
# Use Qdrant Cloud for production
```

### Step 2: Document Chunking Strategy

**Chunking Rules:**
```python
MAX_CHUNK_SIZE = 1000  # tokens (~750 words)
OVERLAP = 200          # tokens overlap between chunks

def chunk_legal_document(doc):
    """
    Smart chunking for legal documents:
    1. Try to keep sections intact
    2. If section > MAX_CHUNK_SIZE, split by subsections
    3. Always include section header in each chunk
    4. Preserve citation context
    """
    pass
```

**Why chunk?**
- Legal sections can be 5000+ words (exceeds embedding model context)
- Better search precision (match specific subsections)
- Faster retrieval

**Metadata preserved:**
- Full citation (e.g., "O.C.G.A. § 16-5-1")
- Section title
- Title/Chapter/Article numbers
- Source (GA_CODE, COURTLISTENER, etc.)
- Chunk position (chunk 1 of 3)

### Step 3: Embedding Generation

**Model Choice: sentence-transformers/all-mpnet-base-v2** ⬅️ UPDATED
- **768 dimensions** (high quality)
- Excellent inference (~100ms per doc on CPU)
- Best open-source model for semantic similarity
- Runs locally (no API costs)
- Better captures legal nuance than smaller models

**Alternative options:**
- Faster (but lower quality): `all-MiniLM-L6-v2` (384d) - not recommended for legal
- **Best quality**: OpenAI `text-embedding-3-large` (3072d) - paid, requires API
- Good middle ground: OpenAI `text-embedding-3-small` (1536d) - paid
- Legal-specific: Fine-tune on legal corpus later

**Recommendation: Start with all-mpnet-base-v2 (768d), upgrade to OpenAI later for production**

**Batch processing:**
```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer('all-mpnet-base-v2')
embeddings = model.encode(
    texts,
    batch_size=16,  # Lower batch size for larger model
    show_progress_bar=True,
    convert_to_numpy=True
)
# embeddings shape: (num_texts, 768)
```

### Step 4: Qdrant Schema Design

**Collection Configuration:**
```python
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

client = QdrantClient("localhost", port=6333)

client.create_collection(
    collection_name="georgia_law",
    vectors_config=VectorParams(
        size=768,  # all-mpnet-base-v2 embedding size
        distance=Distance.COSINE
    )
)
```

**Point Structure:**
```python
{
    "id": "ga_code_16-5-1_chunk_0",  # Unique ID
    "vector": [0.123, -0.456, ...],   # 768-dim embedding
    "payload": {
        # Core fields
        "source": "GA_CODE",
        "jurisdiction": "GA",
        "cite": "16-5-1",
        "cite_full": "O.C.G.A. § 16-5-1",
        "title": "Murder; malice murder; felony murder",

        # Hierarchical structure
        "title_num": "16",
        "chapter": "5",
        "section": "1",

        # Chunk info
        "text": "Full text of this chunk...",
        "chunk_index": 0,
        "total_chunks": 3,

        # Search metadata
        "text_length": 1200,
        "word_count": 180,

        # Source metadata
        "source_url": "https://...",
        "release_date": "2019-08-21",

        # For filtering
        "document_type": "statute",  # statute, case, ordinance
        "criminal": true,             # is criminal law?
        "civil": false,
    }
}
```

### Step 5: Ingestion Pipeline

**Pipeline Flow:**
```
JSONL files → Parse → Chunk → Embed → Store (Qdrant + SQLite)
```

**File: `ingest.py`**
```python
#!/usr/bin/env python3
"""
Ingest Georgia legal sources into vector database.

Usage:
    python ingest.py --source data/ga_code.jsonl
    python ingest.py --all  # Process all JSONL files
"""

import argparse
from pathlib import Path
from tqdm import tqdm
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

def main():
    # 1. Load embedding model (768 dimensions)
    model = SentenceTransformer('all-mpnet-base-v2')

    # 2. Connect to Qdrant
    client = QdrantClient("localhost", port=6333)

    # 3. Create collection if not exists
    setup_collection(client)

    # 4. Process each JSONL file
    for jsonl_file in find_jsonl_files(args.source):
        ingest_file(jsonl_file, client, model)

    print("Ingestion complete!")

def ingest_file(jsonl_file, client, model):
    """Process a single JSONL file."""
    documents = read_jsonl(jsonl_file)

    for doc in tqdm(documents, desc=f"Ingesting {jsonl_file}"):
        # Chunk document
        chunks = chunk_document(doc)

        # Generate embeddings (batch)
        texts = [c['text'] for c in chunks]
        embeddings = model.encode(texts, show_progress_bar=False)

        # Upload to Qdrant
        points = [
            {
                "id": f"{doc['cite']}_chunk_{i}",
                "vector": embedding.tolist(),
                "payload": {**chunk, "embedding_model": "all-mpnet-base-v2"}
            }
            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings))
        ]

        client.upsert(
            collection_name="georgia_law",
            points=points
        )

def chunk_document(doc):
    """Smart chunking for legal documents."""
    text = doc['text']

    # If short enough, return as single chunk
    if len(text.split()) < 750:
        return [{
            **doc,
            'chunk_index': 0,
            'total_chunks': 1
        }]

    # Otherwise, split intelligently
    # TODO: Implement subsection-aware splitting
    chunks = []
    # ... chunking logic ...
    return chunks
```

### Step 6: Basic Search Implementation

**File: `search.py`**
```python
#!/usr/bin/env python3
"""
Search Georgia legal sources using semantic similarity.

Usage:
    python search.py "What are the laws about murder in Georgia?"
"""

from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

def search(query: str, limit: int = 10, filter_by: dict = None):
    """
    Semantic search across Georgia legal sources.

    Args:
        query: Natural language query
        limit: Number of results to return
        filter_by: Optional filters (e.g., {"source": "GA_CODE"})

    Returns:
        List of matching documents with scores
    """
    # Load model and client
    model = SentenceTransformer('all-mpnet-base-v2')  # 768 dimensions
    client = QdrantClient("localhost", port=6333)

    # Generate query embedding
    query_vector = model.encode(query).tolist()

    # Search Qdrant
    results = client.search(
        collection_name="georgia_law",
        query_vector=query_vector,
        limit=limit,
        query_filter=filter_by,  # Optional filters
        with_payload=True
    )

    # Format results
    return [
        {
            "score": hit.score,
            "cite": hit.payload['cite'],
            "title": hit.payload['title'],
            "text": hit.payload['text'][:500] + "...",
            "source_url": hit.payload['source_url']
        }
        for hit in results
    ]

if __name__ == "__main__":
    import sys
    query = " ".join(sys.argv[1:])
    results = search(query)

    for i, result in enumerate(results, 1):
        print(f"\n{i}. [{result['cite']}] {result['title']}")
        print(f"   Score: {result['score']:.4f}")
        print(f"   {result['text']}")
        print(f"   URL: {result['source_url']}")
```

### Step 7: SQLite Document Store

**Why SQLite + Qdrant?**
- Qdrant: Fast vector search
- SQLite: Full text storage, relational queries, citation graph
- Together: Best of both worlds

**File: `db_schema.sql`**
```sql
-- Full documents
CREATE TABLE documents (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    jurisdiction TEXT NOT NULL,
    cite TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    full_text TEXT NOT NULL,
    metadata JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_source ON documents(source);
CREATE INDEX idx_cite ON documents(cite);

-- Chunks (maps to Qdrant)
CREATE TABLE chunks (
    chunk_id TEXT PRIMARY KEY,
    document_id TEXT REFERENCES documents(id),
    chunk_index INTEGER,
    chunk_text TEXT NOT NULL,
    qdrant_point_id TEXT,
    embedding_model TEXT DEFAULT 'all-mpnet-base-v2'
);

-- Full-text search
CREATE VIRTUAL TABLE documents_fts USING fts5(
    cite, title, full_text,
    content=documents,
    content_rowid=rowid
);
```

## Testing & Validation

### Test 1: Verify Ingestion
```bash
python ingest.py --source data/ga_code.jsonl

# Expected output:
# Ingesting ga_code.jsonl: 100%|████████| 38838/38838
# Ingestion complete!
# Total documents: 38838
# Total chunks: 42156  (some sections split into multiple chunks)
```

### Test 2: Basic Search
```bash
python search.py "murder laws in Georgia"

# Expected output:
# 1. [16-5-1] Murder; malice murder; felony murder
#    Score: 0.8234
#    A person commits murder when he unlawfully...
```

### Test 3: Filtered Search
```python
# Search only statutes (not case law)
results = search(
    "speeding violations",
    filter_by={"source": "GA_CODE"}
)
```

## Performance Expectations

**Ingestion:**
- 38,838 documents
- ~42,000 chunks (estimate)
- ~45-60 minutes on modern laptop (CPU only, 768d embeddings are 2x slower)
- Storage: ~1.2GB (768d embeddings + metadata)
- **GPU acceleration**: ~10-15 minutes with CUDA

**Search:**
- Query time: 80-150ms
- Embedding generation: 50-80ms (768d is slower but more accurate)
- Vector search: 30-70ms
- Still very fast for this dataset size
- **Trade-off**: 2x slower but significantly better search quality

## Deliverables Checklist

- [ ] `docker-compose.yml` - Qdrant setup
- [ ] `ingest.py` - Data ingestion pipeline
- [ ] `search.py` - Basic semantic search
- [ ] `db_schema.sql` - SQLite schema
- [ ] `requirements.txt` or `pyproject.toml` updated
- [ ] Test queries demonstrating search works
- [ ] Documentation for running locally

## Next: Phase 2

Once Phase 1 is complete:
- Hybrid search (vector + keyword)
- Advanced filtering
- Result re-ranking
- Citation graph analysis
- Related statute discovery

## Ready to implement?

Would you like me to:
1. Start implementing `ingest.py` now?
2. Set up the Docker Compose file for Qdrant?
3. Both?
