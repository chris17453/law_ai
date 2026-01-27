#!/usr/bin/env python3
"""
Ingest legal documents into PostgreSQL database.

This is Pass 1: Load documents and chunks (without embeddings) into PostgreSQL.
For Pass 2 (embeddings), use generate_embeddings.py.

Supports multiple sources:
- GA_CODE: Georgia Code statutes
- COURTLISTENER: Court opinions
- MUNICODE: Municipal ordinances

Automatically enriches documents with jurisdiction/region metadata.

Usage:
    python ingest.py --all
    python ingest.py --source data/ga_code.jsonl --source-type GA_CODE
    python ingest.py --source data/courtlistener_ga.jsonl --source-type COURTLISTENER
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional
from uuid import uuid4

import psycopg2
from dotenv import load_dotenv
from tqdm import tqdm

# Load environment variables
load_dotenv()


# Chunking parameters
MAX_CHUNK_SIZE = 1000  # tokens (~750 words)
OVERLAP = 100  # token overlap between chunks


# ====================
# Database Connection
# ====================

def get_db_config():
    """Get database configuration from environment."""
    return {
        'host': os.getenv('POSTGRES_HOST', 'localhost'),
        'port': int(os.getenv('POSTGRES_PORT', 5432)),
        'dbname': os.getenv('POSTGRES_DB', 'law_ai'),
        'user': os.getenv('POSTGRES_USER', 'law_ai_user'),
        'password': os.getenv('POSTGRES_PASSWORD', 'law_ai_password')
    }


# ====================
# Jurisdiction Functions
# ====================

# Cache for regions data (loaded once at startup)
_regions_cache = None
_relationships_cache = None

def load_regions_cache():
    """Load all regions and relationships into memory once."""
    global _regions_cache, _relationships_cache

    if _regions_cache is not None:
        return

    config = get_db_config()
    conn = psycopg2.connect(**config)
    cursor = conn.cursor()

    # Load all regions
    cursor.execute("SELECT id, name, type FROM regions")
    _regions_cache = {row[0]: {'id': row[0], 'name': row[1], 'type': row[2]} for row in cursor.fetchall()}

    # Load all relationships
    cursor.execute("""
        SELECT child_id, parent_id, is_primary, coverage_percentage
        FROM region_relationships
        ORDER BY is_primary DESC, coverage_percentage DESC
    """)
    _relationships_cache = {}
    for row in cursor.fetchall():
        child_id = row[0]
        if child_id not in _relationships_cache:
            _relationships_cache[child_id] = []
        _relationships_cache[child_id].append({
            'parent_id': row[1],
            'is_primary': bool(row[2]),
            'coverage': row[3]
        })

    cursor.close()
    conn.close()
    print(f"  Loaded {len(_regions_cache)} regions into cache")

def get_region_hierarchy(region_id: str) -> List[Dict[str, Any]]:
    """
    Get full jurisdiction hierarchy for a region (using in-memory cache).

    Args:
        region_id: Region ID (e.g., 'GA', 'GA-GWINNETT', 'GA-ATLANTA')

    Returns:
        List of regions from country down to given region
    """
    hierarchy = []
    visited = set()

    # Get current region from cache
    if region_id not in _regions_cache:
        return []

    hierarchy.append(_regions_cache[region_id].copy())

    # Build hierarchy upward using cached relationships
    current_id = region_id
    while True:
        if current_id not in _relationships_cache:
            break
        if current_id in visited:
            break
        visited.add(current_id)

        # Get parent relationships (already sorted by is_primary DESC)
        parents = _relationships_cache[current_id]
        if not parents:
            break

        # Use primary parent
        parent_id = parents[0]['parent_id']
        if parent_id not in _regions_cache:
            break

        parent_region = _regions_cache[parent_id].copy()
        parent_region.update(parents[0])  # Add is_primary and coverage
        hierarchy.insert(0, parent_region)
        current_id = parent_id

    return hierarchy


def get_all_parent_counties(region_id: str) -> List[Dict[str, Any]]:
    """
    Get all counties a city belongs to (for multi-county cities, using cache).

    Args:
        region_id: City region ID

    Returns:
        List of county dictionaries
    """
    if region_id not in _relationships_cache:
        return []

    counties = []
    for rel in _relationships_cache[region_id]:
        parent_id = rel['parent_id']
        if parent_id in _regions_cache and _regions_cache[parent_id]['type'] == 'COUNTY':
            county = _regions_cache[parent_id].copy()
            county.update(rel)  # Add is_primary and coverage
            counties.append(county)

    return counties


def detect_region_from_source(doc: Dict[str, Any]) -> str:
    """
    Auto-detect region ID from document source.

    Args:
        doc: Document dictionary

    Returns:
        Region ID (e.g., 'GA', 'GA-GWINNETT')
    """
    source = doc.get('source', '')
    jurisdiction = doc.get('jurisdiction', '')

    # GA Code -> Georgia state
    if source == 'GA_CODE':
        return 'GA'

    # CourtListener -> Georgia state (for GA courts)
    if source == 'COURTLISTENER':
        court = doc.get('court', '')
        if 'ga' in court.lower():
            return 'GA'

    # Municode -> detect county/city from jurisdiction field
    if source == 'MUNICODE':
        if 'Gwinnett' in jurisdiction:
            return 'GA-GWINNETT'
        if 'Fulton' in jurisdiction:
            return 'GA-FULTON'
        if 'Atlanta' in jurisdiction:
            return 'GA-ATLANTA'

    # Default to Georgia state
    return 'GA'


def enrich_with_jurisdiction(doc: Dict[str, Any]) -> Dict[str, Any]:
    """
    Add jurisdiction metadata to document.

    Args:
        doc: Document dictionary

    Returns:
        Enriched document with jurisdiction fields
    """
    # Detect region
    region_id = detect_region_from_source(doc)

    # Get hierarchy
    hierarchy = get_region_hierarchy(region_id)

    if not hierarchy:
        # Fallback if region not found
        doc['region_type'] = 'STATE'
        doc['region_id'] = 'GA'
        doc['region_name'] = 'Georgia'
        doc['applies_to_country'] = 'US'
        doc['applies_to_state'] = 'GA'
        doc['applies_to_counties'] = None
        doc['primary_county'] = None
        doc['applies_to_city'] = None
        doc['jurisdiction_hierarchy'] = []
        return doc

    # Current region (last in hierarchy)
    current_region = hierarchy[-1]

    # Extract hierarchy levels
    country = next((r for r in hierarchy if r['type'] == 'COUNTRY'), None)
    state = next((r for r in hierarchy if r['type'] == 'STATE'), None)
    city = next((r for r in hierarchy if r['type'] == 'CITY'), None)

    # Handle counties (may be multiple for cities)
    if city:
        counties = get_all_parent_counties(city['id'])
        county_ids = [c['id'] for c in counties] if counties else None
        primary_county = counties[0]['id'] if counties else None
    else:
        county = next((r for r in hierarchy if r['type'] == 'COUNTY'), None)
        county_ids = [county['id']] if county else None
        primary_county = county['id'] if county else None

    # Add to document
    doc['region_type'] = current_region['type']
    doc['region_id'] = current_region['id']
    doc['region_name'] = current_region['name']

    # Denormalized fields for filtering
    doc['applies_to_country'] = country['id'] if country else None
    doc['applies_to_state'] = state['id'] if state else None
    doc['applies_to_counties'] = county_ids
    doc['primary_county'] = primary_county
    doc['applies_to_city'] = city['id'] if city else None

    # Full hierarchy for display
    doc['jurisdiction_hierarchy'] = hierarchy

    return doc


# ====================
# Chunking
# ====================

def chunk_text(text: str, max_words: int = 750, overlap_words: int = 75) -> List[str]:
    """
    Split text into overlapping chunks.

    Args:
        text: Text to chunk
        max_words: Maximum words per chunk
        overlap_words: Number of words to overlap between chunks

    Returns:
        List of text chunks
    """
    words = text.split()

    if len(words) <= max_words:
        return [text]

    chunks = []
    start = 0

    while start < len(words):
        end = min(start + max_words, len(words))
        chunk_words = words[start:end]
        chunks.append(" ".join(chunk_words))

        if end >= len(words):
            break

        # Overlap for context
        start = end - overlap_words

    return chunks


def create_chunks(doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Create chunks from a document.

    Args:
        doc: Document dictionary with 'text', 'cite', 'title', etc.

    Returns:
        List of chunk dictionaries
    """
    text = doc.get('text', '')

    if not text:
        return []

    # Chunk the text
    text_chunks = chunk_text(text)

    # Create chunk metadata
    chunks = []
    for i, chunk_content in enumerate(text_chunks):
        chunk = {
            **doc,  # Copy all document metadata
            'text': chunk_content,
            'chunk_index': i,
            'total_chunks': len(text_chunks),
            'chunk_id': f"{doc.get('cite', uuid4().hex)}__chunk_{i}"
        }
        chunks.append(chunk)

    return chunks


# ====================
# Database Ingestion
# ====================

def ingest_to_postgres(docs: List[Dict], chunks: List[Dict]):
    """
    Ingest documents and chunks into PostgreSQL.

    Args:
        docs: List of document dictionaries
        chunks: List of chunk dictionaries (without embeddings)
    """
    config = get_db_config()
    conn = psycopg2.connect(**config)
    cursor = conn.cursor()

    # Insert documents
    for doc in docs:
        cursor.execute("""
            INSERT INTO documents (id, source, jurisdiction, cite, title, full_text, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (cite) DO UPDATE SET
                source = EXCLUDED.source,
                jurisdiction = EXCLUDED.jurisdiction,
                title = EXCLUDED.title,
                full_text = EXCLUDED.full_text,
                metadata = EXCLUDED.metadata
        """, (
            doc.get('cite', str(uuid4())),
            doc.get('source', 'UNKNOWN'),
            doc.get('jurisdiction', 'GA'),
            doc.get('cite', ''),
            doc.get('title', ''),
            doc.get('text', ''),
            json.dumps({k: v for k, v in doc.items() if k not in ['id', 'source', 'jurisdiction', 'cite', 'title', 'text']})
        ))

    # Insert chunks (without embeddings)
    embedding_model_name = os.getenv("AZURE_OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")

    for chunk in chunks:
        cursor.execute("""
            INSERT INTO chunks (
                chunk_id, document_id, chunk_index, chunk_text, embedding_model,
                source, cite, title, title_num, chapter, source_url, date,
                region_type, region_id, region_name,
                applies_to_country, applies_to_state, applies_to_counties,
                primary_county, applies_to_city, jurisdiction_hierarchy
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (chunk_id) DO UPDATE SET
                chunk_text = EXCLUDED.chunk_text,
                source = EXCLUDED.source,
                cite = EXCLUDED.cite,
                title = EXCLUDED.title,
                region_type = EXCLUDED.region_type,
                region_id = EXCLUDED.region_id,
                region_name = EXCLUDED.region_name,
                applies_to_country = EXCLUDED.applies_to_country,
                applies_to_state = EXCLUDED.applies_to_state,
                applies_to_counties = EXCLUDED.applies_to_counties,
                primary_county = EXCLUDED.primary_county,
                applies_to_city = EXCLUDED.applies_to_city,
                jurisdiction_hierarchy = EXCLUDED.jurisdiction_hierarchy
        """, (
            chunk['chunk_id'],
            chunk.get('cite', ''),
            chunk['chunk_index'],
            chunk['text'],
            embedding_model_name,
            chunk.get('source', 'UNKNOWN'),
            chunk.get('cite', ''),
            chunk.get('title', ''),
            chunk.get('title_num', ''),
            chunk.get('chapter', ''),
            chunk.get('source_url', ''),
            chunk.get('date', chunk.get('release', '')),
            chunk.get('region_type', 'STATE'),
            chunk.get('region_id', 'GA'),
            chunk.get('region_name', 'Georgia'),
            chunk.get('applies_to_country'),
            chunk.get('applies_to_state'),
            chunk.get('applies_to_counties'),
            chunk.get('primary_county'),
            chunk.get('applies_to_city'),
            json.dumps(chunk.get('jurisdiction_hierarchy', []))
        ))

    conn.commit()
    cursor.close()
    conn.close()


def ingest_file(file_path: Path, source_type: str, verbose: bool = False):
    """
    Ingest a single JSONL file.

    Args:
        file_path: Path to JSONL file
        source_type: Source type (GA_CODE, COURTLISTENER, MUNICODE)
        verbose: Enable verbose output
    """
    if not file_path.exists():
        print(f"✗ File not found: {file_path}")
        return

    print(f"\nIngesting {file_path.name} (source: {source_type})...")

    # Load regions cache once for fast jurisdiction lookups
    load_regions_cache()

    # Load documents
    documents = []
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                doc = json.loads(line)
                doc['source'] = source_type  # Ensure source is set
                documents.append(doc)

    if not documents:
        print(f"  No documents found in {file_path.name}")
        return

    print(f"  Loaded {len(documents)} documents")

    # Enrich with jurisdiction metadata
    print(f"  Enriching with jurisdiction metadata...")
    for doc in documents:
        enrich_with_jurisdiction(doc)

    # Create chunks
    print(f"  Creating chunks...")
    all_chunks = []
    for doc in tqdm(documents, desc="  Chunking", disable=not verbose):
        chunks = create_chunks(doc)
        all_chunks.extend(chunks)

    print(f"  Created {len(all_chunks)} chunks from {len(documents)} documents")

    # Ingest to PostgreSQL
    print(f"  Storing in PostgreSQL...")
    ingest_to_postgres(documents, all_chunks)

    print(f"✓ Ingested {len(documents)} documents ({len(all_chunks)} chunks) from {file_path.name}")
    print(f"  Note: Embeddings not generated yet. Run 'make generate-embeddings' to create vector embeddings.")


def main():
    parser = argparse.ArgumentParser(description="Ingest legal documents into PostgreSQL")
    parser.add_argument('--all', action='store_true', help='Ingest all JSONL files in data/')
    parser.add_argument('--source', type=Path, help='Path to specific JSONL file')
    parser.add_argument('--source-type', choices=['GA_CODE', 'COURTLISTENER', 'MUNICODE'], help='Type of source data')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    args = parser.parse_args()

    if not args.all and not args.source:
        parser.print_help()
        return 1

    print("Pass 1: Ingesting documents into PostgreSQL (without embeddings)\n")

    if args.all:
        # Ingest all files
        data_dir = Path("data")
        files = [
            (data_dir / "ga_code.jsonl", "GA_CODE"),
            (data_dir / "courtlistener_ga.jsonl", "COURTLISTENER"),
            (data_dir / "municode_gwinnett.jsonl", "MUNICODE"),
        ]

        for file_path, source_type in files:
            if file_path.exists():
                ingest_file(file_path, source_type, args.verbose)
            else:
                print(f"Skipping {file_path.name} (not found)")

    elif args.source:
        # Ingest specific file
        if not args.source_type:
            print("Error: --source-type required when using --source")
            return 1

        ingest_file(args.source, args.source_type, args.verbose)

    print("\n✓ Document ingestion complete!")
    print("\nNext step: Generate embeddings with 'make generate-embeddings'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
