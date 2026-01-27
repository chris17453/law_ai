# AI Legal Search System Architecture

## Overview
Build an AI-powered semantic search system for Georgia legal sources that uses vector embeddings for similarity search and AI agents for complex legal research tasks.

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     USER INTERFACE                          │
│            (CLI / API / Web Interface)                      │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│                  ORCHESTRATOR AGENT                         │
│  - Parse user query                                         │
│  - Create search plan                                       │
│  - Delegate to specialist agents                            │
│  - Synthesize results                                       │
└──────────────────────┬──────────────────────────────────────┘
                       │
        ┌──────────────┼──────────────┐
        │              │              │
┌───────▼────┐  ┌──────▼─────┐  ┌────▼─────────┐
│  Statute   │  │  Case Law  │  │  Ordinance   │
│  Search    │  │  Search    │  │  Search      │
│  Agent     │  │  Agent     │  │  Agent       │
└───────┬────┘  └──────┬─────┘  └────┬─────────┘
        │              │              │
        └──────────────┼──────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│              VECTOR SEARCH LAYER                            │
│  - Embedding generation                                     │
│  - Semantic similarity search                               │
│  - Hybrid search (vector + keyword)                         │
│  - Result re-ranking                                        │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│              VECTOR DATABASE                                │
│  - Embeddings storage                                       │
│  - Metadata filtering                                       │
│  - Fast similarity search                                   │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│              DOCUMENT STORE                                 │
│  - Full text storage                                        │
│  - Metadata storage                                         │
│  - Citation graph                                           │
└─────────────────────────────────────────────────────────────┘
```

## Technology Stack Recommendation

### Vector Database: **Qdrant**

**Why Qdrant:**
- ✅ Open source and self-hosted
- ✅ Excellent performance for legal-scale datasets
- ✅ Rich filtering capabilities (by jurisdiction, source, date, etc.)
- ✅ Python-native client
- ✅ Supports hybrid search (dense + sparse vectors)
- ✅ Payload storage (metadata + full text)
- ✅ Easy to run locally via Docker
- ✅ Scales to production

**Alternatives considered:**
- ChromaDB: Simpler but less performant at scale
- Weaviate: Good but more complex setup
- Pinecone: Cloud-only, paid
- pgvector: Good if already using Postgres, but slower

### Embedding Model: **sentence-transformers/all-mpnet-base-v2**

**Why this model:**
- ✅ Free and runs locally
- ✅ **768 dimensions** - excellent semantic understanding
- ✅ Best open-source sentence embedding model
- ✅ Superior quality for complex legal concepts
- ✅ Works very well for legal text

**Upgrade path:**
- For highest quality: `OpenAI text-embedding-3-large` (3072d, paid)
- For good balance: `OpenAI text-embedding-3-small` (1536d, paid)
- For legal-specific: Fine-tune on legal corpus
- For faster (not recommended): `all-MiniLM-L6-v2` (384d, lower quality)

### Document Store: **SQLite** (for now)

**Why SQLite:**
- ✅ No separate database server needed
- ✅ Perfect for local development
- ✅ Can store full documents + metadata
- ✅ Easy to query and join with vector results
- ✅ Upgrade path to PostgreSQL for production

### AI Agent Framework: **Custom with Claude API**

**Components:**
- Orchestrator Agent (Claude Sonnet 4.5)
- Specialist Search Agents (Claude Haiku for speed)
- Tool: Vector search function
- Tool: Keyword search function
- Tool: Citation lookup function

## Data Model

### Vector Database Schema (Qdrant)

```python
{
    "collection_name": "georgia_law",
    "vectors": {
        "size": 768,  # all-mpnet-base-v2 embedding dimension
        "distance": "Cosine"
    },
    "payload": {
        "id": "ga_code_16-5-1",
        "source": "GA_CODE",  # or COURTLISTENER, MUNICODE
        "jurisdiction": "GA",
        "cite": "16-5-1",
        "title": "Murder; malice murder; felony murder...",
        "title_num": "16",  # Title number
        "chapter": "5",     # Chapter number
        "text_chunk": "...",  # Actual text chunk
        "chunk_index": 0,     # Which chunk of the section
        "full_text_length": 5000,
        "date": "2019-08-21",
        "source_url": "https://...",
        "metadata": {
            # Additional source-specific metadata
        }
    }
}
```

### Document Store Schema (SQLite)

```sql
-- Full documents table
CREATE TABLE documents (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    jurisdiction TEXT NOT NULL,
    cite TEXT NOT NULL,
    title TEXT NOT NULL,
    full_text TEXT NOT NULL,
    metadata JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_source (source),
    INDEX idx_jurisdiction (jurisdiction),
    INDEX idx_cite (cite)
);

-- Document chunks table (maps to vector DB)
CREATE TABLE chunks (
    chunk_id TEXT PRIMARY KEY,
    document_id TEXT REFERENCES documents(id),
    chunk_index INTEGER,
    chunk_text TEXT NOT NULL,
    vector_id TEXT, -- ID in Qdrant
    embedding_model TEXT,
    INDEX idx_document (document_id)
);

-- Citation graph table
CREATE TABLE citations (
    from_cite TEXT,
    to_cite TEXT,
    citation_context TEXT,
    PRIMARY KEY (from_cite, to_cite)
);

-- Search history table
CREATE TABLE search_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query TEXT NOT NULL,
    results JSON,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## Implementation Phases

### Phase 1: Data Ingestion & Vector Storage ⬅️ START HERE
**Goal:** Get data into vector database

**Tasks:**
1. Set up Qdrant (Docker or local)
2. Install embedding model (sentence-transformers)
3. Create ingestion pipeline:
   - Read JSONL files
   - Chunk long documents (legal sections can be 5000+ words)
   - Generate embeddings
   - Store in Qdrant + SQLite
4. Build basic search function

**Deliverables:**
- `ingest.py` - Pipeline to load data
- `search.py` - Basic semantic search
- Qdrant collection with 38,838+ documents

### Phase 2: Search Layer
**Goal:** Implement hybrid search with filtering

**Tasks:**
1. Implement semantic search (vector similarity)
2. Add keyword search (BM25 or similar)
3. Hybrid search combining both
4. Metadata filtering (by source, jurisdiction, etc.)
5. Result re-ranking
6. Find related statutes by similarity

**Deliverables:**
- `search_engine.py` - Comprehensive search API
- Support for complex queries

### Phase 3: AI Agent System
**Goal:** Build agent-based search orchestration

**Tasks:**
1. Orchestrator Agent
   - Parse natural language legal questions
   - Create multi-step search plan
   - Delegate to specialist agents
2. Specialist Agents:
   - Statute Search Agent
   - Case Law Search Agent
   - Citation Analysis Agent
   - Relevance Ranker Agent
3. Agent Tools:
   - Vector search tool
   - Keyword search tool
   - Citation graph traversal
4. Result synthesis

**Deliverables:**
- `agents/orchestrator.py`
- `agents/specialists.py`
- `agents/tools.py`
- End-to-end query answering

### Phase 4: Advanced Features
**Goal:** Production-ready system

**Tasks:**
1. Citation extraction and graph building
2. Legal concept extraction (NER for legal entities)
3. Cross-reference analysis
4. Query expansion with legal synonyms
5. Caching and optimization
6. Web UI or API

## Chunking Strategy for Legal Documents

Legal documents need special handling:

```python
# Chunking rules for Georgia Code
1. Preserve section boundaries (don't split mid-section)
2. For long sections (>2000 tokens):
   - Split by subsections (a), (b), (c)
   - Keep section header with each chunk
   - Store chunk_index and total_chunks
3. Store section metadata with each chunk:
   - Title number, chapter, article
   - Full citation
   - Section title

# Example chunk:
{
    "cite": "16-5-1",
    "title": "Murder; malice murder; felony murder",
    "chunk_text": "16-5-1. Murder; malice murder...\n\n(a) A person commits murder when...",
    "chunk_index": 0,
    "total_chunks": 1
}
```

## Query Examples

### Simple Semantic Search
```
User: "What are the laws about speeding in Georgia?"
→ Vector search for similar statutes
→ Return relevant sections with citations
```

### Complex Multi-Agent Search
```
User: "What are my legal obligations if I witness a car accident in Georgia?"

Orchestrator Agent Plan:
1. Search for "duty to render aid" statutes
2. Search for "hit and run witness" laws
3. Search for "good samaritan" protections
4. Search case law for relevant precedents
5. Synthesize obligations and protections

Sub-Agents Execute:
- Statute Agent → Finds O.C.G.A. § 40-6-270 (duty to stop)
- Statute Agent → Finds O.C.G.A. § 51-1-29 (Good Samaritan)
- Case Law Agent → Finds relevant GA Supreme Court cases
- Citation Agent → Maps relationships between statutes

Orchestrator Synthesizes:
"In Georgia, you have the following obligations..."
```

### Related Law Discovery
```
User: "Show me laws related to O.C.G.A. § 16-5-1"
→ Vector similarity search for related statutes
→ Citation graph traversal
→ Find statutes that reference this one
→ Find similar criminal code sections
```

## Next Steps

1. **Start with Phase 1**: Get Qdrant running and ingest Georgia Code
2. **Test basic search**: Verify embeddings and similarity work
3. **Build incrementally**: Add agents after search works well

Would you like me to start implementing Phase 1?
