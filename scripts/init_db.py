#!/usr/bin/env python3
"""
Initialize Law AI PostgreSQL database with pgvector extension.

Creates:
- PostgreSQL database with pgvector extension
- Tables: documents, chunks (with vector embeddings), regions, region_relationships
- Indexes for fast search and filtering
- Loads region/jurisdiction data
"""

import json
import os
import sys
from pathlib import Path

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from dotenv import load_dotenv

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


def init_postgres():
    """Initialize PostgreSQL database with pgvector extension."""
    config = get_db_config()

    print(f"Connecting to PostgreSQL at {config['host']}:{config['port']}...")

    # Connect to default postgres database to check if our DB exists
    conn = psycopg2.connect(
        host=config['host'],
        port=config['port'],
        dbname='postgres',
        user=config['user'],
        password=config['password']
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cursor = conn.cursor()

    # Check if database exists
    cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (config['dbname'],))
    exists = cursor.fetchone()

    if not exists:
        print(f"Creating database '{config['dbname']}'...")
        cursor.execute(f"CREATE DATABASE {config['dbname']}")
        print(f"✓ Created database '{config['dbname']}'")
    else:
        print(f"✓ Database '{config['dbname']}' already exists")

    cursor.close()
    conn.close()

    # Connect to our database
    conn = psycopg2.connect(**config)
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cursor = conn.cursor()

    # Enable pgvector extension
    print("Enabling pgvector extension...")
    cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
    print("✓ pgvector extension enabled")

    # Create regions table
    print("Creating regions table...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS regions (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            state_id TEXT,
            state_code TEXT,
            fips_code TEXT,
            census_place_code TEXT,
            latitude REAL,
            longitude REAL,
            bounds TEXT,
            metadata JSONB
        )
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_region_name ON regions(name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_region_type ON regions(type)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_region_state ON regions(state_id)")
    print("✓ Created regions table")

    # Create region_relationships table
    print("Creating region_relationships table...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS region_relationships (
            child_id TEXT NOT NULL REFERENCES regions(id),
            parent_id TEXT NOT NULL REFERENCES regions(id),
            relationship_type TEXT NOT NULL,
            is_primary BOOLEAN DEFAULT false,
            coverage_percentage REAL,
            PRIMARY KEY (child_id, parent_id)
        )
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_rel_child ON region_relationships(child_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_rel_parent ON region_relationships(parent_id)")
    print("✓ Created region_relationships table")

    # Create documents table
    print("Creating documents table...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            jurisdiction TEXT NOT NULL,
            cite TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            full_text TEXT NOT NULL,
            metadata JSONB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_source ON documents(source)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_jurisdiction ON documents(jurisdiction)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_cite ON documents(cite)")

    # Full-text search index
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_documents_fulltext
        ON documents USING gin(to_tsvector('english', title || ' ' || full_text))
    """)
    print("✓ Created documents table")

    # Create chunks table with vector column
    print("Creating chunks table with vector embeddings...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chunks (
            chunk_id TEXT PRIMARY KEY,
            document_id TEXT REFERENCES documents(id),
            chunk_index INTEGER NOT NULL,
            chunk_text TEXT NOT NULL,
            embedding vector(1536),  -- text-embedding-3-small dimension
            embedding_model TEXT DEFAULT 'text-embedding-3-small',

            -- Metadata for filtering (denormalized from documents)
            source TEXT NOT NULL,
            cite TEXT NOT NULL,
            title TEXT NOT NULL,

            -- Hierarchical structure (for GA Code)
            title_num TEXT,
            chapter TEXT,

            -- Additional metadata
            source_url TEXT,
            date TEXT,

            -- Jurisdiction fields (denormalized for fast filtering)
            region_type TEXT DEFAULT 'STATE',
            region_id TEXT DEFAULT 'GA',
            region_name TEXT DEFAULT 'Georgia',
            applies_to_country TEXT,
            applies_to_state TEXT,
            applies_to_counties TEXT[],  -- Array for multi-county cities
            primary_county TEXT,
            applies_to_city TEXT,
            jurisdiction_hierarchy JSONB,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunk_document ON chunks(document_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunk_source ON chunks(source)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunk_region_type ON chunks(region_type)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunk_applies_state ON chunks(applies_to_state)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunk_applies_county ON chunks(primary_county)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunk_applies_city ON chunks(applies_to_city)")

    # Vector similarity search index (HNSW for fast approximate search)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_chunk_embedding
        ON chunks USING hnsw (embedding vector_cosine_ops)
    """)
    print("✓ Created chunks table with vector index")

    # Create search_history table
    print("Creating search_history table...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS search_history (
            id SERIAL PRIMARY KEY,
            query TEXT NOT NULL,
            source_filter TEXT,
            region_filter TEXT,
            results_count INTEGER,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("✓ Created search_history table")

    cursor.close()
    conn.close()

    print("\n✓ PostgreSQL database initialized successfully!")


def load_regions(regions_file: Path = Path("data/georgia_regions.json")):
    """Load regions data from JSON file into database."""
    if not regions_file.exists():
        print(f"⚠ Regions file not found: {regions_file}")
        print("  Skipping region data load. Run 'python scripts/create_regions_data.py' to generate.")
        return

    print(f"\nLoading regions from {regions_file}...")
    config = get_db_config()
    conn = psycopg2.connect(**config)
    cursor = conn.cursor()

    with open(regions_file, 'r') as f:
        data = json.load(f)

    # Load regions
    regions = data.get('regions', [])
    for region in regions:
        cursor.execute("""
            INSERT INTO regions
            (id, name, type, state_id, state_code, fips_code, census_place_code,
             latitude, longitude, bounds, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name,
                type = EXCLUDED.type,
                state_id = EXCLUDED.state_id,
                state_code = EXCLUDED.state_code,
                fips_code = EXCLUDED.fips_code,
                census_place_code = EXCLUDED.census_place_code,
                latitude = EXCLUDED.latitude,
                longitude = EXCLUDED.longitude,
                bounds = EXCLUDED.bounds,
                metadata = EXCLUDED.metadata
        """, (
            region['id'],
            region['name'],
            region['type'],
            region.get('state_id'),
            region.get('state_code'),
            region.get('fips_code'),
            region.get('census_place_code'),
            region.get('latitude'),
            region.get('longitude'),
            region.get('bounds'),
            json.dumps(region.get('metadata', {}))
        ))

    # Load relationships
    relationships = data.get('relationships', [])
    for rel in relationships:
        cursor.execute("""
            INSERT INTO region_relationships
            (child_id, parent_id, relationship_type, is_primary, coverage_percentage)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (child_id, parent_id) DO UPDATE SET
                relationship_type = EXCLUDED.relationship_type,
                is_primary = EXCLUDED.is_primary,
                coverage_percentage = EXCLUDED.coverage_percentage
        """, (
            rel['child_id'],
            rel['parent_id'],
            rel.get('relationship_type', 'part_of'),
            rel.get('is_primary', False),
            rel.get('coverage_percentage', 100.0)
        ))

    conn.commit()
    cursor.close()
    conn.close()

    print(f"✓ Loaded {len(regions)} regions and {len(relationships)} relationships")


def main():
    """Initialize all databases."""
    print("Initializing Law AI PostgreSQL database...\n")

    try:
        init_postgres()
        load_regions()
        print("\n✓ Database initialization complete!")
        print("\nNext steps:")
        print("  1. Fetch legal data:  python law_fetch.py --out data --no-verify")
        print("  2. Ingest documents:  make ingest-docs")
        print("  3. Generate embeddings: make generate-embeddings")
        print("  4. Search:            make search QUERY='murder laws in Georgia'")
        return 0
    except Exception as e:
        print(f"\n✗ Error during initialization: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
