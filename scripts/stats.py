#!/usr/bin/env python3
"""
Show statistics about the Law AI database.
"""

import sqlite3
import sys
from collections import Counter

from qdrant_client import QdrantClient


def get_qdrant_stats():
    """Get statistics from Qdrant."""
    try:
        client = QdrantClient("localhost", port=6333)
        info = client.get_collection("georgia_law")

        return {
            'total_vectors': info.vectors_count or 0,
            'total_points': info.points_count or 0,
            'indexed': info.status == 'green'
        }
    except Exception as e:
        return {'error': str(e)}


def get_sqlite_stats():
    """Get statistics from SQLite."""
    try:
        conn = sqlite3.connect('law_ai.db')
        cursor = conn.cursor()

        # Total documents
        cursor.execute("SELECT COUNT(*) FROM documents")
        total_docs = cursor.fetchone()[0]

        # Total chunks
        cursor.execute("SELECT COUNT(*) FROM chunks")
        total_chunks = cursor.fetchone()[0]

        # Documents by source
        cursor.execute("""
            SELECT source, COUNT(*)
            FROM documents
            GROUP BY source
        """)
        by_source = dict(cursor.fetchall())

        # Recent searches
        cursor.execute("""
            SELECT COUNT(*)
            FROM search_history
            WHERE datetime(timestamp) > datetime('now', '-24 hours')
        """)
        searches_24h = cursor.fetchone()[0]

        # Most common search terms
        cursor.execute("""
            SELECT query, COUNT(*) as count
            FROM search_history
            GROUP BY query
            ORDER BY count DESC
            LIMIT 5
        """)
        top_queries = cursor.fetchall()

        conn.close()

        return {
            'total_docs': total_docs,
            'total_chunks': total_chunks,
            'by_source': by_source,
            'searches_24h': searches_24h,
            'top_queries': top_queries
        }
    except Exception as e:
        return {'error': str(e)}


def print_stats():
    """Print formatted statistics."""
    print("\n" + "="*80)
    print(" Law AI Database Statistics")
    print("="*80 + "\n")

    # Qdrant stats
    print("📊 Vector Database (Qdrant)")
    print("-" * 40)
    qdrant_stats = get_qdrant_stats()

    if 'error' in qdrant_stats:
        print(f"  ✗ Error: {qdrant_stats['error']}")
    else:
        print(f"  Total Vectors:  {qdrant_stats['total_vectors']:,}")
        print(f"  Total Points:   {qdrant_stats['total_points']:,}")
        print(f"  Status:         {'✓ Indexed' if qdrant_stats['indexed'] else '⚠ Indexing...'}")

    print()

    # SQLite stats
    print("📚 Document Store (SQLite)")
    print("-" * 40)
    sqlite_stats = get_sqlite_stats()

    if 'error' in sqlite_stats:
        print(f"  ✗ Error: {sqlite_stats['error']}")
    else:
        print(f"  Total Documents: {sqlite_stats['total_docs']:,}")
        print(f"  Total Chunks:    {sqlite_stats['total_chunks']:,}")

        if sqlite_stats['by_source']:
            print("\n  Documents by Source:")
            for source, count in sqlite_stats['by_source'].items():
                icon = {'GA_CODE': '📘', 'COURTLISTENER': '⚖️', 'MUNICODE': '🏛️'}.get(source, '📄')
                print(f"    {icon} {source:15s}: {count:,}")

        print(f"\n  Searches (24h):  {sqlite_stats['searches_24h']:,}")

        if sqlite_stats['top_queries']:
            print("\n  Top Search Queries:")
            for query, count in sqlite_stats['top_queries']:
                preview = query[:50] + "..." if len(query) > 50 else query
                print(f"    • \"{preview}\" ({count}x)")

    print("\n" + "="*80 + "\n")


def main():
    print_stats()
    return 0


if __name__ == "__main__":
    sys.exit(main())
