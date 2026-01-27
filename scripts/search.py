#!/usr/bin/env python3
"""
Search Georgia legal sources using semantic similarity.

Usage:
    python search.py "What are the laws about murder in Georgia?"
    python search.py "speeding violations" --source GA_CODE
    python search.py "duty of care" --limit 5
    python search.py "noise laws" --region GA-ATLANTA
    python search.py "parking rules" --region GA-GWINNETT
"""

import argparse
import json
import sys
import sqlite3
from typing import List, Dict, Optional

from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue, MatchAny
from sentence_transformers import SentenceTransformer


def load_model():
    """Load the embedding model."""
    return SentenceTransformer('all-mpnet-base-v2')


def get_all_parent_counties(region_id: str) -> List[str]:
    """
    Get all county IDs for a region (handles multi-county cities).

    Args:
        region_id: Region ID

    Returns:
        List of county IDs
    """
    conn = sqlite3.connect('law_ai.db')
    cursor = conn.cursor()

    cursor.execute("""
        SELECT r.id
        FROM regions r
        JOIN region_relationships rr ON r.id = rr.parent_id
        WHERE rr.child_id = ? AND r.type = 'COUNTY'
        ORDER BY rr.is_primary DESC
    """, (region_id,))

    county_ids = [row[0] for row in cursor.fetchall()]
    conn.close()

    return county_ids


def get_region_hierarchy_ids(region_id: str) -> List[str]:
    """
    Get all parent region IDs for filtering.

    Args:
        region_id: Region ID

    Returns:
        List of region IDs from country to given region
    """
    conn = sqlite3.connect('law_ai.db')
    cursor = conn.cursor()

    hierarchy = []
    visited = set()

    def get_parents(child_id):
        if child_id in visited:
            return []
        visited.add(child_id)

        cursor.execute("""
            SELECT r.id, r.type
            FROM regions r
            JOIN region_relationships rr ON r.id = rr.parent_id
            WHERE rr.child_id = ?
            ORDER BY rr.is_primary DESC
            LIMIT 1
        """, (child_id,))

        row = cursor.fetchone()
        return [{'id': row[0], 'type': row[1]}] if row else []

    # Add current region
    hierarchy.append(region_id)

    # Walk up hierarchy
    current_id = region_id
    while True:
        parents = get_parents(current_id)
        if not parents:
            break
        hierarchy.insert(0, parents[0]['id'])
        current_id = parents[0]['id']

    conn.close()
    return hierarchy


def build_jurisdiction_filter(region_id: str, include_parents: bool = True) -> Filter:
    """
    Build Qdrant filter for jurisdiction-based search.

    Args:
        region_id: Region ID to search
        include_parents: Include laws from parent jurisdictions (state, federal)

    Returns:
        Qdrant filter object
    """
    conn = sqlite3.connect('law_ai.db')
    cursor = conn.cursor()

    # Get region info
    cursor.execute("SELECT id, type FROM regions WHERE id = ?", (region_id,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        # Fallback to state filter
        return Filter(must=[
            FieldCondition(key="applies_to_state", match=MatchValue(value="GA"))
        ])

    region_type = row[1]
    conn.close()

    conditions = []

    if region_type == 'COUNTRY':
        # All laws in country
        conditions.append(
            FieldCondition(key="applies_to_country", match=MatchValue(value=region_id))
        )

    elif region_type == 'STATE':
        # State laws
        conditions.append(
            FieldCondition(key="applies_to_state", match=MatchValue(value=region_id))
        )
        if include_parents:
            conditions.append(
                FieldCondition(key="applies_to_country", match=MatchValue(value="US"))
            )

    elif region_type == 'COUNTY':
        # County laws
        conditions.append(
            FieldCondition(key="primary_county", match=MatchValue(value=region_id))
        )
        if include_parents:
            # Also include state laws
            hierarchy_ids = get_region_hierarchy_ids(region_id)
            state_id = next((r for r in hierarchy_ids if r.startswith('GA') and len(r) == 2), None)
            if state_id:
                conditions.append(
                    FieldCondition(key="applies_to_state", match=MatchValue(value=state_id))
                )

    elif region_type == 'CITY':
        # City laws
        conditions.append(
            FieldCondition(key="applies_to_city", match=MatchValue(value=region_id))
        )

        if include_parents:
            # Get all counties (for multi-county cities)
            county_ids = get_all_parent_counties(region_id)

            if county_ids:
                # County laws from any applicable county
                conditions.append(
                    FieldCondition(key="primary_county", match=MatchAny(any=county_ids))
                )

            # State laws
            hierarchy_ids = get_region_hierarchy_ids(region_id)
            state_id = next((r for r in hierarchy_ids if r.startswith('GA') and len(r) == 2), None)
            if state_id:
                conditions.append(
                    FieldCondition(key="applies_to_state", match=MatchValue(value=state_id))
                )

    return Filter(should=conditions) if conditions else None


def search_vector(
    query: str,
    model: SentenceTransformer,
    client: QdrantClient,
    limit: int = 10,
    source_filter: Optional[str] = None,
    region_filter: Optional[str] = None,
    include_parent_jurisdictions: bool = True
) -> List[Dict]:
    """
    Perform semantic vector search.

    Args:
        query: Natural language query
        model: Embedding model
        client: Qdrant client
        limit: Number of results
        source_filter: Filter by source (GA_CODE, COURTLISTENER, MUNICODE)
        region_filter: Filter by region (e.g., 'GA', 'GA-GWINNETT', 'GA-ATLANTA')
        include_parent_jurisdictions: Include laws from parent jurisdictions

    Returns:
        List of search results
    """
    # Generate query embedding
    query_vector = model.encode(query, convert_to_numpy=True).tolist()

    # Prepare filters
    conditions = []

    # Source filter
    if source_filter:
        conditions.append(
            FieldCondition(key="source", match=MatchValue(value=source_filter))
        )

    # Region/jurisdiction filter
    if region_filter:
        jurisdiction_filter = build_jurisdiction_filter(region_filter, include_parent_jurisdictions)
        # Combine with source filter if both present
        if conditions:
            search_filter = Filter(
                must=conditions,
                should=jurisdiction_filter.should if jurisdiction_filter else []
            )
        else:
            search_filter = jurisdiction_filter
    else:
        search_filter = Filter(must=conditions) if conditions else None

    # Search Qdrant
    results = client.search(
        collection_name="georgia_law",
        query_vector=query_vector,
        limit=limit,
        query_filter=search_filter,
        with_payload=True
    )

    return results


def get_full_document(cite: str) -> Optional[Dict]:
    """
    Get full document from SQLite by citation.

    Args:
        cite: Document citation

    Returns:
        Document dictionary or None
    """
    conn = sqlite3.connect('law_ai.db')
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, source, jurisdiction, cite, title, full_text
        FROM documents
        WHERE cite = ?
    """, (cite,))

    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    return {
        'id': row[0],
        'source': row[1],
        'jurisdiction': row[2],
        'cite': row[3],
        'title': row[4],
        'full_text': row[5]
    }


def log_search(query: str, source_filter: Optional[str], results_count: int):
    """Log search to history."""
    conn = sqlite3.connect('law_ai.db')
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO search_history (query, source_filter, results_count)
        VALUES (?, ?, ?)
    """, (query, source_filter, results_count))

    conn.commit()
    conn.close()


def format_source_badge(source: str) -> str:
    """Format source as a colored badge."""
    badges = {
        'GA_CODE': '📘 GA Code',
        'COURTLISTENER': '⚖️  Case Law',
        'MUNICODE': '🏛️  Ordinance'
    }
    return badges.get(source, source)


def print_results(query: str, results: List, show_full: bool = False, show_jurisdiction: bool = True):
    """
    Print search results in a formatted way.

    Args:
        query: Original query
        results: Search results from Qdrant
        show_full: Show full document text
        show_jurisdiction: Show jurisdiction hierarchy
    """
    print(f"\n{'='*80}")
    print(f"Query: {query}")
    print(f"Found {len(results)} results")
    print(f"{'='*80}\n")

    for i, hit in enumerate(results, 1):
        payload = hit.payload
        score = hit.score

        # Extract fields
        source = payload.get('source', 'UNKNOWN')
        cite = payload.get('cite', 'N/A')
        title = payload.get('title', 'Untitled')
        text = payload.get('text', '')
        chunk_info = f"[chunk {payload.get('chunk_index', 0) + 1}/{payload.get('total_chunks', 1)}]"
        source_url = payload.get('source_url', '')

        # Jurisdiction info
        region_type = payload.get('region_type', '')
        region_name = payload.get('region_name', '')
        jurisdiction_hierarchy_json = payload.get('jurisdiction_hierarchy', '[]')

        # Print result
        print(f"{i}. {format_source_badge(source)} {cite} {chunk_info}")
        print(f"   Score: {score:.4f}")
        print(f"   Title: {title}")

        # Show jurisdiction
        if show_jurisdiction and jurisdiction_hierarchy_json:
            try:
                hierarchy = json.loads(jurisdiction_hierarchy_json)
                if hierarchy:
                    hierarchy_str = " → ".join([r.get('name', '') for r in hierarchy])
                    print(f"   Jurisdiction: {hierarchy_str}")
            except:
                if region_name:
                    print(f"   Jurisdiction: {region_name} ({region_type})")

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

    print("Loading embedding model...")
    model = load_model()

    print("Connecting to Qdrant...")
    client = QdrantClient("localhost", port=6333)

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
        model,
        client,
        args.limit,
        args.source,
        args.region,
        include_parent_jurisdictions=not args.region_only
    )

    # Log search
    log_search(args.query, args.source, len(results))

    # Print results
    print_results(args.query, results, args.full, show_jurisdiction=not args.no_jurisdiction)

    return 0


if __name__ == "__main__":
    sys.exit(main())
