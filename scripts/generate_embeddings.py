#!/usr/bin/env python3
"""
Generate embeddings for chunks already in PostgreSQL.

This is Pass 2 of the two-pass ingestion process:
- Pass 1: ingest.py (load documents into PostgreSQL)
- Pass 2: generate_embeddings.py (generate embeddings with Azure OpenAI)

Usage:
    python generate_embeddings.py --all
    python generate_embeddings.py --source GA_CODE
    python generate_embeddings.py --limit 100  # Process only first 100 chunks
"""

import argparse
import json
import os
import sys
from typing import List, Dict

import psycopg2
from dotenv import load_dotenv
from openai import AzureOpenAI
from tqdm import tqdm

# Load environment variables
load_dotenv()


def get_db_config():
    """Get database configuration from environment."""
    return {
        'host': os.getenv('POSTGRES_HOST', 'localhost'),
        'port': int(os.getenv('POSTGRES_PORT', 5432)),
        'dbname': os.getenv('POSTGRES_DB', 'law_ai'),
        'user': os.getenv('POSTGRES_USER', 'law_ai_user'),
        'password': os.getenv('POSTGRES_PASSWORD', 'law_ai_password')
    }


def get_azure_client():
    """Initialize Azure OpenAI client."""
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    api_key = os.getenv("AZURE_OPENAI_KEY")
    api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-08-01-preview")

    if not endpoint or not api_key:
        raise ValueError(
            "Missing Azure OpenAI credentials. "
            "Please set AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_KEY in .env file."
        )

    return AzureOpenAI(
        azure_endpoint=endpoint,
        api_key=api_key,
        api_version=api_version
    )


def get_chunks_without_embeddings(source_filter: str = None, limit: int = None) -> List[Dict]:
    """
    Load chunks from PostgreSQL that don't have embeddings yet.

    Args:
        source_filter: Filter by source (GA_CODE, COURTLISTENER, MUNICODE)
        limit: Limit number of chunks to process

    Returns:
        List of (chunk_id, chunk_text) tuples
    """
    config = get_db_config()
    conn = psycopg2.connect(**config)
    cursor = conn.cursor()

    # Build query
    query = "SELECT chunk_id, chunk_text FROM chunks WHERE embedding IS NULL"

    params = []
    if source_filter:
        query += " AND source = %s"
        params.append(source_filter)

    if limit:
        query += f" LIMIT {limit}"

    cursor.execute(query, params)
    rows = cursor.fetchall()

    chunks = [{'chunk_id': row[0], 'text': row[1]} for row in rows]

    cursor.close()
    conn.close()
    return chunks


def generate_embeddings_batch(azure_client: AzureOpenAI, texts: List[str], batch_size: int = 100) -> List[List[float]]:
    """
    Generate embeddings for a list of texts.

    Args:
        azure_client: Azure OpenAI client
        texts: List of texts to embed
        batch_size: Batch size for API calls

    Returns:
        List of embedding vectors
    """
    embedding_model = os.getenv("AZURE_OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
    embeddings = []

    print(f"Generating embeddings for {len(texts)} chunks...")

    for i in tqdm(range(0, len(texts), batch_size), desc="Embedding batches"):
        batch = texts[i:i + batch_size]

        try:
            response = azure_client.embeddings.create(
                input=batch,
                model=embedding_model
            )

            batch_embeddings = [item.embedding for item in response.data]
            embeddings.extend(batch_embeddings)
        except Exception as e:
            print(f"\nError generating embeddings for batch {i//batch_size + 1}: {e}")
            # Add None placeholders for failed batch
            embeddings.extend([None] * len(batch))

    return embeddings


def update_embeddings(chunk_ids: List[str], embeddings: List[List[float]]):
    """
    Update chunks with embeddings in PostgreSQL.

    Args:
        chunk_ids: List of chunk IDs
        embeddings: List of embedding vectors
    """
    config = get_db_config()
    conn = psycopg2.connect(**config)
    cursor = conn.cursor()

    print(f"Updating {len(chunk_ids)} chunks with embeddings...")

    successful = 0
    failed = 0

    for chunk_id, embedding in tqdm(zip(chunk_ids, embeddings), total=len(chunk_ids), desc="Updating DB"):
        if embedding is None:
            failed += 1
            continue

        try:
            cursor.execute("""
                UPDATE chunks
                SET embedding = %s::vector
                WHERE chunk_id = %s
            """, (embedding, chunk_id))
            successful += 1
        except Exception as e:
            print(f"\nError updating chunk {chunk_id}: {e}")
            failed += 1

    conn.commit()
    cursor.close()
    conn.close()

    print(f"✓ Successfully updated {successful} chunks")
    if failed > 0:
        print(f"✗ Failed to update {failed} chunks")


def main():
    parser = argparse.ArgumentParser(description="Generate embeddings from PostgreSQL chunks")
    parser.add_argument('--all', action='store_true', help='Process all chunks without embeddings')
    parser.add_argument('--source', choices=['GA_CODE', 'COURTLISTENER', 'MUNICODE'], help='Filter by source')
    parser.add_argument('--limit', type=int, help='Limit number of chunks to process')
    parser.add_argument('--batch-size', type=int, default=100, help='Batch size for API calls (default: 100)')
    args = parser.parse_args()

    if not args.all and not args.source:
        print("Error: Must specify --all or --source")
        parser.print_help()
        return 1

    print("Pass 2: Generating embeddings with Azure OpenAI\n")

    # Initialize Azure OpenAI client
    print("Initializing Azure OpenAI client...")
    azure_client = get_azure_client()
    print("✓ Azure OpenAI client initialized")

    # Load chunks without embeddings
    print("\nLoading chunks from PostgreSQL...")
    source_filter = args.source if args.source else None
    chunks = get_chunks_without_embeddings(source_filter, args.limit)

    if not chunks:
        print("No chunks found without embeddings.")
        return 0

    print(f"✓ Loaded {len(chunks)} chunks without embeddings\n")

    # Generate embeddings
    texts = [c['text'] for c in chunks]
    chunk_ids = [c['chunk_id'] for c in chunks]

    embeddings = generate_embeddings_batch(azure_client, texts, args.batch_size)

    # Update database
    print()
    update_embeddings(chunk_ids, embeddings)

    print(f"\n✓ Embedding generation complete!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
