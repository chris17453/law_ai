#!/usr/bin/env python3
"""
Search Georgia legal sources using semantic similarity with PostgreSQL + pgvector.

Usage:
    python search.py "What are the laws about murder in Georgia?"
    python search.py "speeding violations" --source GA_CODE
    python search.py "duty of care" --limit 5
    python search.py "noise laws" --region GA-ATLANTA
    python search.py "parking rules" --region GA-GWINNETT
"""

import argparse
import json
import os
import sys
from typing import List, Dict, Optional

import psycopg2
from dotenv import load_dotenv
from openai import AzureOpenAI

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


def generate_query_embedding(query: str, azure_client: AzureOpenAI) -> List[float]:
    """Generate embedding for search query."""
    embedding_model = os.getenv("AZURE_OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")

    response = azure_client.embeddings.create(
        input=[query],
        model=embedding_model
    )

    return response.data[0].embedding


def get_region_hierarchy_ids(region_id: str, conn) -> List[str]:
    """Get all parent region IDs for filtering."""
    cursor = conn.cursor()

    hierarchy = [region_id]
    visited = set([region_id])

    current_id = region_id
    while True:
        cursor.execute("""
            SELECT parent_id
            FROM region_relationships
            WHERE child_id = %s AND is_primary = true
            LIMIT 1
        """, (current_id,))

        row = cursor.fetchone()
        if not row:
            break

        parent_id = row[0]
        if parent_id in visited:
            break

        hierarchy.insert(0, parent_id)
        visited.add(parent_id)
        current_id = parent_id

    cursor.close()
    return hierarchy


def get_all_parent_counties(region_id: str, conn) -> List[str]:
    """Get all county IDs for a region (handles multi-county cities)."""
    cursor = conn.cursor()

    cursor.execute("""
        SELECT r.id
        FROM regions r
        JOIN region_relationships rr ON r.id = rr.parent_id
        WHERE rr.child_id = %s AND r.type = 'COUNTY'
        ORDER BY rr.is_primary DESC
    """, (region_id,))

    county_ids = [row[0] for row in cursor.fetchall()]
    cursor.close()

    return county_ids


def build_jurisdiction_filter(region_id: str, include_parents: bool, conn) -> tuple:
    """
    Build SQL filter for jurisdiction-based search.

    Returns:
        (where_clause, params) tuple for SQL query
    """
    cursor = conn.cursor()

    # Get region info
    cursor.execute("SELECT id, type FROM regions WHERE id = %s", (region_id,))
    row = cursor.fetchone()
    cursor.close()

    if not row:
        # Fallback to state filter
        return ("applies_to_state = %s", ['GA'])

    region_type = row[1]
    conditions = []
    params = []

    if region_type == 'COUNTRY':
        conditions.append("applies_to_country = %s")
        params.append(region_id)

    elif region_type == 'STATE':
        conditions.append("applies_to_state = %s")
        params.append(region_id)
        if include_parents:
            conditions.append("applies_to_country = %s")
            params.append("US")

    elif region_type == 'COUNTY':
        conditions.append("primary_county = %s")
        params.append(region_id)
        if include_parents:
            hierarchy_ids = get_region_hierarchy_ids(region_id, conn)
            state_id = next((r for r in hierarchy_ids if r.startswith('GA') and len(r) == 2), None)
            if state_id:
                conditions.append("applies_to_state = %s")
                params.append(state_id)

    elif region_type == 'CITY':
        conditions.append("applies_to_city = %s")
        params.append(region_id)

        if include_parents:
            # Get all counties (for multi-county cities)
            county_ids = get_all_parent_counties(region_id, conn)

            if county_ids:
                placeholders = ','.join(['%s'] * len(county_ids))
                conditions.append(f"primary_county IN ({placeholders})")
                params.extend(county_ids)

            # State laws
            hierarchy_ids = get_region_hierarchy_ids(region_id, conn)
            state_id = next((r for r in hierarchy_ids if r.startswith('GA') and len(r) == 2), None)
            if state_id:
                conditions.append("applies_to_state = %s")
                params.append(state_id)

    where_clause = " OR ".join(f"({c})" for c in conditions) if conditions else "1=1"
    return (where_clause, params)


def search_vector(
    query: str,
    azure_client: AzureOpenAI,
    limit: int = 10,
    source_filter: Optional[str] = None,
    region_filter: Optional[str] = None,
    include_parent_jurisdictions: bool = True
) -> List[Dict]:
    """
    Perform semantic vector search using PostgreSQL + pgvector.

    Args:
        query: Natural language query
        azure_client: Azure OpenAI client
        limit: Number of results
        source_filter: Filter by source (GA_CODE, COURTLISTENER, MUNICODE)
        region_filter: Filter by region (e.g., 'GA', 'GA-GWINNETT', 'GA-ATLANTA')
        include_parent_jurisdictions: Include laws from parent jurisdictions

    Returns:
        List of search results
    """
    # Generate query embedding
    print("Generating query embedding...")
    query_vector = generate_query_embedding(query, azure_client)

    # Connect to database
    config = get_db_config()
    conn = psycopg2.connect(**config)
    cursor = conn.cursor()

    # Build WHERE clause
    where_clauses = []
    params = []

    # Source filter
    if source_filter:
        where_clauses.append("source = %s")
        params.append(source_filter)

    # Region/jurisdiction filter
    if region_filter:
        jurisdiction_clause, jurisdiction_params = build_jurisdiction_filter(
            region_filter, include_parent_jurisdictions, conn
        )
        where_clauses.append(f"({jurisdiction_clause})")
        params.extend(jurisdiction_params)

    # Combine filters
    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

    # Vector similarity search query
    # Using cosine distance: embedding <=> query_vector
    query_sql = f"""
        SELECT
            chunk_id,
            chunk_text,
            source,
            cite,
            title,
            chunk_index,
            source_url,
            region_type,
            region_name,
            jurisdiction_hierarchy,
            1 - (embedding <=> %s::vector) as similarity_score
        FROM chunks
        WHERE {where_sql}
        ORDER BY embedding <=> %s::vector
        LIMIT %s
    """

    # Execute search
    print(f"Searching database...")
    cursor.execute(query_sql, [query_vector] + params + [query_vector, limit])
    results = cursor.fetchall()

    # Format results
    formatted_results = []
    for row in results:
        result = {
            'chunk_id': row[0],
            'text': row[1],
            'source': row[2],
            'cite': row[3],
            'title': row[4],
            'chunk_index': row[5],
            'source_url': row[6],
            'region_type': row[7],
            'region_name': row[8],
            'jurisdiction_hierarchy': row[9] if row[9] else [],
            'score': float(row[10])
        }
        formatted_results.append(result)

    cursor.close()
    conn.close()

    # Log search
    log_search(query, source_filter, len(formatted_results))

    return formatted_results


def log_search(query: str, source_filter: Optional[str], results_count: int):
    """Log search to history."""
    config = get_db_config()
    conn = psycopg2.connect(**config)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO search_history (query, source_filter, results_count)
        VALUES (%s, %s, %s)
    """, (query, source_filter, results_count))

    conn.commit()
    cursor.close()
    conn.close()


def format_source_badge(source: str) -> str:
    """Format source as a colored badge."""
    badges = {
        'GA_CODE': '📘 GA Code',
        'COURTLISTENER': '⚖️  Case Law',
        'MUNICODE': '🏛️  Ordinance'
    }
    return badges.get(source, source)


def print_results(query: str, results: List[Dict], show_full: bool = False, show_jurisdiction: bool = True):
    """Print search results in a formatted way."""
    print(f"\n{'='*80}")
    print(f"Query: {query}")
    print(f"Found {len(results)} results")
    print(f"{'='*80}\n")

    for i, result in enumerate(results, 1):
        source = result.get('source', 'UNKNOWN')
        cite = result.get('cite', 'N/A')
        title = result.get('title', 'Untitled')
        text = result.get('text', '')
        chunk_index = result.get('chunk_index', 0)
        score = result.get('score', 0)
        source_url = result.get('source_url', '')

        # Jurisdiction info
        region_name = result.get('region_name', '')
        jurisdiction_hierarchy = result.get('jurisdiction_hierarchy', [])

        # Print result
        print(f"{i}. {format_source_badge(source)} {cite} [chunk {chunk_index}]")
        print(f"   Score: {score:.4f}")
        print(f"   Title: {title}")

        # Show jurisdiction
        if show_jurisdiction and jurisdiction_hierarchy:
            hierarchy_str = " → ".join([r.get('name', '') for r in jurisdiction_hierarchy])
            print(f"   Jurisdiction: {hierarchy_str}")
        elif region_name:
            print(f"   Jurisdiction: {region_name}")

        if show_full:
            print(f"\n   {text}\n")
        else:
            # Show preview (first 300 chars)
            preview = text[:300] + "..." if len(text) > 300 else text
            print(f"   {preview}")

        if source_url:
            print(f"   URL: {source_url}")

        print()

    print(f"{'='*80}\n")


def main():
    parser = argparse.ArgumentParser(description="Search Georgia legal sources")
    parser.add_argument('query', type=str, help='Search query')
    parser.add_argument('--limit', '-l', type=int, default=10, help='Number of results (default: 10)')
    parser.add_argument('--source', '-s', choices=['GA_CODE', 'COURTLISTENER', 'MUNICODE'], help='Filter by source')
    parser.add_argument('--region', '-r', type=str, help='Filter by region (e.g., GA, GA-GWINNETT, GA-ATLANTA)')
    parser.add_argument('--region-only', action='store_true', help='Exclude parent jurisdictions (only exact region)')
    parser.add_argument('--full', '-f', action='store_true', help='Show full text of results')
    parser.add_argument('--no-jurisdiction', action='store_true', help='Hide jurisdiction hierarchy in results')
    args = parser.parse_args()

    print("Initializing Azure OpenAI client...")
    azure_client = get_azure_client()

    # Build search description
    search_desc = f"'{args.query}'"
    if args.source:
        search_desc += f" [source: {args.source}]"
    if args.region:
        region_mode = "exact region" if args.region_only else "with parent jurisdictions"
        search_desc += f" [region: {args.region}, {region_mode}]"

    print(f"Searching for: {search_desc}...")

    results = search_vector(
        args.query,
        azure_client,
        args.limit,
        args.source,
        args.region,
        include_parent_jurisdictions=not args.region_only
    )

    # Print results
    print_results(args.query, results, args.full, show_jurisdiction=not args.no_jurisdiction)

    return 0


if __name__ == "__main__":
    sys.exit(main())
