# Jurisdictional Hierarchy Design

## Problem

Legal sources need proper geographic/jurisdictional context:
- A **state statute** applies to the entire state
- A **county ordinance** applies to the county (and inherits state + federal law)
- A **city ordinance** applies to the city (and inherits county + state + federal law)
- A **court decision** has a jurisdiction (district, circuit, state supreme, federal)

Users need to:
1. Search laws by jurisdiction: "What are the DUI laws in Gwinnett County?"
2. Understand hierarchy: "Show all laws that apply in Atlanta" (city + county + state + federal)
3. Compare jurisdictions: "Compare gun laws in Atlanta vs Savannah"
4. Filter by region type: "Show only state-level statutes"

## Data Model

### Region Types

```python
from enum import Enum

class RegionType(str, Enum):
    COUNTRY = "COUNTRY"      # USA
    STATE = "STATE"          # Georgia
    COUNTY = "COUNTY"        # Gwinnett County
    CITY = "CITY"            # Lawrenceville
    TRIBAL = "TRIBAL"        # Tribal jurisdiction (future)
```

### Jurisdiction Structure

Each legal document has:
1. **Primary region** - Where this law directly applies
2. **Region type** - Level of government
3. **Hierarchical path** - All parent jurisdictions

```python
{
    "cite": "O.C.G.A. § 16-5-1",
    "title": "Murder; malice murder",
    "text": "...",

    # Jurisdiction fields
    "region_type": "STATE",
    "primary_region": {
        "name": "Georgia",
        "code": "GA",
        "type": "STATE"
    },
    "jurisdiction_hierarchy": [
        {"name": "United States", "code": "US", "type": "COUNTRY"},
        {"name": "Georgia", "code": "GA", "type": "STATE"}
    ],

    # For filtering
    "applies_to_country": "US",
    "applies_to_state": "GA",
    "applies_to_county": null,
    "applies_to_city": null,

    # Source info
    "source": "GA_CODE",
    "source_url": "..."
}
```

### Example: Gwinnett County Ordinance

```python
{
    "cite": "Gwinnett County Code § 1-2-3",
    "title": "Noise ordinance",

    "region_type": "COUNTY",
    "primary_region": {
        "name": "Gwinnett County",
        "code": "GA-GWINNETT",
        "type": "COUNTY"
    },
    "jurisdiction_hierarchy": [
        {"name": "United States", "code": "US", "type": "COUNTRY"},
        {"name": "Georgia", "code": "GA", "type": "STATE"},
        {"name": "Gwinnett County", "code": "GA-GWINNETT", "type": "COUNTY"}
    ],

    "applies_to_country": "US",
    "applies_to_state": "GA",
    "applies_to_county": "GA-GWINNETT",
    "applies_to_city": null,

    "source": "MUNICODE",
}
```

### Example: Atlanta City Ordinance (Multi-County City)

```python
{
    "cite": "Atlanta City Code § 30-1",
    "title": "Parking regulations",

    "region_type": "CITY",
    "primary_region": {
        "name": "Atlanta",
        "code": "GA-ATLANTA",
        "type": "CITY"
    },
    "jurisdiction_hierarchy": [
        {"name": "United States", "code": "US", "type": "COUNTRY"},
        {"name": "Georgia", "code": "GA", "type": "STATE"},
        # Atlanta spans multiple counties
        {
            "type": "COUNTY_GROUP",
            "counties": [
                {"name": "Fulton County", "code": "GA-FULTON", "is_primary": true, "coverage": 90.0},
                {"name": "DeKalb County", "code": "GA-DEKALB", "is_primary": false, "coverage": 9.0},
                {"name": "Cobb County", "code": "GA-COBB", "is_primary": false, "coverage": 1.0}
            ]
        },
        {"name": "Atlanta", "code": "GA-ATLANTA", "type": "CITY"}
    ],

    "applies_to_country": "US",
    "applies_to_state": "GA",
    # Multiple counties - store as JSON array
    "applies_to_counties": ["GA-FULTON", "GA-DEKALB", "GA-COBB"],
    "primary_county": "GA-FULTON",
    "applies_to_city": "GA-ATLANTA",

    "source": "MUNICODE",
}
```

## Region Lookup Table

Create a normalized region database for consistent lookups.

### SQLite Schema (Updated for Multi-County Cities)

```sql
-- Region definitions
CREATE TABLE regions (
    id TEXT PRIMARY KEY,            -- e.g., "GA-ATLANTA", "GA-FULTON"
    name TEXT NOT NULL,              -- e.g., "Atlanta", "Fulton County"
    type TEXT NOT NULL,              -- COUNTRY, STATE, COUNTY, CITY
    state_id TEXT,                   -- e.g., "GA" (for quick lookups)

    -- Codes for lookups
    state_code TEXT,                 -- e.g., "GA"
    fips_code TEXT,                  -- Federal FIPS code
    census_place_code TEXT,          -- For cities

    -- Geographic data (optional, for future map features)
    latitude REAL,
    longitude REAL,
    bounds TEXT,                     -- GeoJSON bounds

    metadata TEXT,                   -- JSON for extra data

    INDEX idx_name (name),
    INDEX idx_type (type),
    INDEX idx_state (state_id)
);

-- Many-to-many: Cities can belong to multiple counties
CREATE TABLE region_relationships (
    child_id TEXT NOT NULL REFERENCES regions(id),
    parent_id TEXT NOT NULL REFERENCES regions(id),
    relationship_type TEXT NOT NULL,  -- 'contains', 'part_of'
    is_primary BOOLEAN DEFAULT 0,     -- Is this the primary county for the city?
    coverage_percentage REAL,         -- What % of city is in this county?

    PRIMARY KEY (child_id, parent_id),
    INDEX idx_child (child_id),
    INDEX idx_parent (parent_id)
);

-- Pre-populate with known regions
INSERT INTO regions VALUES
    ('US', 'United States', 'COUNTRY', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
    ('GA', 'Georgia', 'STATE', NULL, 'GA', '13', NULL, NULL, NULL, NULL, NULL),
    ('GA-FULTON', 'Fulton County', 'COUNTY', 'GA', 'GA', '13121', NULL, NULL, NULL, NULL, NULL),
    ('GA-DEKALB', 'DeKalb County', 'COUNTY', 'GA', 'GA', '13089', NULL, NULL, NULL, NULL, NULL),
    ('GA-COBB', 'Cobb County', 'COUNTY', 'GA', 'GA', '13067', NULL, NULL, NULL, NULL, NULL),
    ('GA-GWINNETT', 'Gwinnett County', 'COUNTY', 'GA', 'GA', '13135', NULL, NULL, NULL, NULL, NULL),
    ('GA-ATLANTA', 'Atlanta', 'CITY', 'GA', 'GA', NULL, '1304000', 33.7490, -84.3880, NULL, NULL),
    ('GA-LAWRENCEVILLE', 'Lawrenceville', 'CITY', 'GA', 'GA', NULL, '1345488', 33.9526, -83.9880, NULL, NULL);

-- Define relationships - Atlanta spans 3 counties!
INSERT INTO region_relationships VALUES
    -- Atlanta is in Fulton (primary, ~90% of city)
    ('GA-ATLANTA', 'GA-FULTON', 'part_of', 1, 90.0),
    -- Atlanta is in DeKalb (~9% of city)
    ('GA-ATLANTA', 'GA-DEKALB', 'part_of', 0, 9.0),
    -- Atlanta is in Cobb (~1% of city)
    ('GA-ATLANTA', 'GA-COBB', 'part_of', 0, 1.0),
    -- Lawrenceville is entirely in Gwinnett
    ('GA-LAWRENCEVILLE', 'GA-GWINNETT', 'part_of', 1, 100.0),
    -- State contains counties
    ('GA-FULTON', 'GA', 'part_of', 1, 100.0),
    ('GA-DEKALB', 'GA', 'part_of', 1, 100.0),
    ('GA-COBB', 'GA', 'part_of', 1, 100.0),
    ('GA-GWINNETT', 'GA', 'part_of', 1, 100.0),
    -- State is part of country
    ('GA', 'US', 'part_of', 1, 100.0);
```

### Region Lookup Functions (Updated for Multi-Parent)

```python
def get_region_hierarchy(region_id: str, include_all_counties: bool = False) -> List[Dict]:
    """
    Get full hierarchy for a region.

    For cities spanning multiple counties, returns primary county by default,
    or all counties if include_all_counties=True.

    Example (Atlanta with primary county only):
        get_region_hierarchy('GA-ATLANTA')
        Returns: [
            {'id': 'US', 'name': 'United States', 'type': 'COUNTRY'},
            {'id': 'GA', 'name': 'Georgia', 'type': 'STATE'},
            {'id': 'GA-FULTON', 'name': 'Fulton County', 'type': 'COUNTY', 'is_primary': True},
            {'id': 'GA-ATLANTA', 'name': 'Atlanta', 'type': 'CITY'}
        ]

    Example (Atlanta with all counties):
        get_region_hierarchy('GA-ATLANTA', include_all_counties=True)
        Returns: [
            {'id': 'US', 'name': 'United States', 'type': 'COUNTRY'},
            {'id': 'GA', 'name': 'Georgia', 'type': 'STATE'},
            [
                {'id': 'GA-FULTON', 'name': 'Fulton County', 'type': 'COUNTY', 'is_primary': True, 'coverage': 90.0},
                {'id': 'GA-DEKALB', 'name': 'DeKalb County', 'type': 'COUNTY', 'is_primary': False, 'coverage': 9.0},
                {'id': 'GA-COBB', 'name': 'Cobb County', 'type': 'COUNTY', 'is_primary': False, 'coverage': 1.0}
            ],
            {'id': 'GA-ATLANTA', 'name': 'Atlanta', 'type': 'CITY'}
        ]
    """
    conn = sqlite3.connect('law_ai.db')
    cursor = conn.cursor()

    hierarchy = []
    current_id = region_id

    # Start from the given region and work up
    visited = set()

    def get_parents(child_id):
        if child_id in visited:
            return []
        visited.add(child_id)

        cursor.execute("""
            SELECT r.id, r.name, r.type, rr.is_primary, rr.coverage_percentage
            FROM regions r
            JOIN region_relationships rr ON r.id = rr.parent_id
            WHERE rr.child_id = ?
            ORDER BY rr.is_primary DESC, rr.coverage_percentage DESC
        """, (child_id,))

        parents = cursor.fetchall()
        return [{
            'id': p[0],
            'name': p[1],
            'type': p[2],
            'is_primary': bool(p[3]),
            'coverage': p[4]
        } for p in parents]

    # Get current region info
    cursor.execute("SELECT id, name, type FROM regions WHERE id = ?", (region_id,))
    current = cursor.fetchone()
    if current:
        hierarchy.append({'id': current[0], 'name': current[1], 'type': current[2]})

    # Build hierarchy upward
    current_id = region_id
    while True:
        parents = get_parents(current_id)

        if not parents:
            break

        if include_all_counties and len(parents) > 1 and parents[0]['type'] == 'COUNTY':
            # Multiple counties - include all
            hierarchy.insert(0, parents)
            current_id = parents[0]['id']  # Continue from primary county
        else:
            # Single parent or use primary only
            hierarchy.insert(0, parents[0])
            current_id = parents[0]['id']

    conn.close()
    return hierarchy


def get_all_parent_counties(city_id: str) -> List[Dict]:
    """
    Get all counties a city belongs to.

    Example:
        get_all_parent_counties('GA-ATLANTA')
        Returns: [
            {'id': 'GA-FULTON', 'name': 'Fulton County', 'is_primary': True, 'coverage': 90.0},
            {'id': 'GA-DEKALB', 'name': 'DeKalb County', 'is_primary': False, 'coverage': 9.0},
            {'id': 'GA-COBB', 'name': 'Cobb County', 'is_primary': False, 'coverage': 1.0}
        ]
    """
    conn = sqlite3.connect('law_ai.db')
    cursor = conn.cursor()

    cursor.execute("""
        SELECT r.id, r.name, rr.is_primary, rr.coverage_percentage
        FROM regions r
        JOIN region_relationships rr ON r.id = rr.parent_id
        WHERE rr.child_id = ? AND r.type = 'COUNTY'
        ORDER BY rr.is_primary DESC, rr.coverage_percentage DESC
    """, (city_id,))

    counties = cursor.fetchall()
    conn.close()

    return [{
        'id': c[0],
        'name': c[1],
        'is_primary': bool(c[2]),
        'coverage': c[3]
    } for c in counties]


def detect_region_from_source(doc: Dict) -> Dict:
    """
    Auto-detect region from document source.

    Examples:
        GA_CODE → Georgia (STATE)
        COURTLISTENER with court='gaapp' → Georgia (STATE)
        MUNICODE for Gwinnett → Gwinnett County (COUNTY)
    """
    source = doc.get('source')

    if source == 'GA_CODE':
        return {
            'region_type': 'STATE',
            'region_id': 'GA'
        }

    elif source == 'COURTLISTENER':
        court = doc.get('court', '')
        if court in ['ga', 'gaapp']:
            return {
                'region_type': 'STATE',
                'region_id': 'GA'
            }

    elif source == 'MUNICODE':
        # Parse from jurisdiction field
        jurisdiction = doc.get('jurisdiction', '')
        if 'Gwinnett' in jurisdiction:
            return {
                'region_type': 'COUNTY',
                'region_id': 'GA-GWINNETT'
            }

    # Default to state level
    return {
        'region_type': 'STATE',
        'region_id': 'GA'
    }
```

## Qdrant Schema Update (Supporting Multi-County)

Add jurisdiction fields to vector database payload:

```python
{
    "id": "ga_code_16-5-1_chunk_0",
    "vector": [...],
    "payload": {
        # Existing fields
        "source": "GA_CODE",
        "cite": "16-5-1",
        "title": "Murder; malice murder",
        "text": "...",

        # NEW: Jurisdiction fields
        "region_type": "STATE",
        "region_id": "GA",
        "region_name": "Georgia",

        # For filtering (denormalized for performance)
        "applies_to_country": "US",
        "applies_to_state": "GA",

        # UPDATED: Support multiple counties as array
        "applies_to_counties": null,  # or ["GA-FULTON", "GA-DEKALB"] for multi-county cities
        "primary_county": null,       # Primary county for the city (if applicable)

        "applies_to_city": null,

        # Hierarchy as JSON for display
        "jurisdiction_hierarchy": [
            {"id": "US", "name": "United States", "type": "COUNTRY"},
            {"id": "GA", "name": "Georgia", "type": "STATE"}
        ]
    }
}
```

### Example: Atlanta City Ordinance Payload

```python
{
    "id": "atlanta_code_30-1_chunk_0",
    "vector": [...],
    "payload": {
        "source": "MUNICODE",
        "cite": "Atlanta City Code § 30-1",
        "title": "Parking regulations",
        "text": "...",

        "region_type": "CITY",
        "region_id": "GA-ATLANTA",
        "region_name": "Atlanta",

        # Multi-county support
        "applies_to_country": "US",
        "applies_to_state": "GA",
        "applies_to_counties": ["GA-FULTON", "GA-DEKALB", "GA-COBB"],
        "primary_county": "GA-FULTON",
        "applies_to_city": "GA-ATLANTA",

        "jurisdiction_hierarchy": [
            {"id": "US", "name": "United States", "type": "COUNTRY"},
            {"id": "GA", "name": "Georgia", "type": "STATE"},
            {"id": "GA-FULTON", "name": "Fulton County", "type": "COUNTY", "is_primary": true},
            {"id": "GA-ATLANTA", "name": "Atlanta", "type": "CITY"}
        ]
    }
}
```

## Search Query Examples

### Query 1: "What laws apply in Gwinnett County?"

```python
from qdrant_client.models import Filter, FieldCondition, MatchAny

# Search for laws that apply to Gwinnett County
# Includes: state laws, county laws, and any city laws within the county
results = client.search(
    collection_name="georgia_law",
    query_vector=query_embedding,
    query_filter=Filter(
        should=[
            # State laws (apply to whole state, including Gwinnett)
            FieldCondition(key="applies_to_state", match=MatchValue(value="GA")),
            # Gwinnett County laws
            FieldCondition(key="applies_to_county", match=MatchValue(value="GA-GWINNETT")),
        ]
    )
)
```

### Query 2: "Show only state-level statutes"

```python
results = client.search(
    collection_name="georgia_law",
    query_vector=query_embedding,
    query_filter=Filter(
        must=[
            FieldCondition(key="region_type", match=MatchValue(value="STATE"))
        ]
    )
)
```

### Query 3: "What are the noise laws in Atlanta?"

```python
# CHALLENGE: Atlanta spans Fulton, DeKalb, and Cobb counties!
# Need to include laws from all 3 counties plus state and federal

# Get all counties for Atlanta
counties = get_all_parent_counties('GA-ATLANTA')
county_ids = [c['id'] for c in counties]  # ['GA-FULTON', 'GA-DEKALB', 'GA-COBB']

# Search with all applicable jurisdictions
from qdrant_client.models import Filter, FieldCondition, MatchAny

results = client.search(
    collection_name="georgia_law",
    query_vector=query_embedding,
    query_filter=Filter(
        should=[
            # City ordinances
            FieldCondition(key="applies_to_city", match=MatchValue(value="GA-ATLANTA")),
            # County ordinances from ANY of the 3 counties
            FieldCondition(key="applies_to_counties", match=MatchAny(any=county_ids)),
            # OR primary county for simpler queries
            FieldCondition(key="primary_county", match=MatchAny(any=county_ids)),
            # State laws
            FieldCondition(key="applies_to_state", match=MatchValue(value="GA")),
        ]
    )
)
```

### Query 4: "Compare DUI laws in Atlanta vs Lawrenceville"

```python
# Atlanta is multi-county, Lawrenceville is single-county

# Get jurisdictions for both
atlanta_counties = get_all_parent_counties('GA-ATLANTA')
lawrenceville_counties = get_all_parent_counties('GA-LAWRENCEVILLE')

# Search for Atlanta
atlanta_results = client.search(
    collection_name="georgia_law",
    query_vector=query_embedding,
    query_filter=Filter(should=[
        FieldCondition(key="applies_to_city", match=MatchValue(value="GA-ATLANTA")),
        FieldCondition(key="primary_county", match=MatchAny(any=[c['id'] for c in atlanta_counties])),
        FieldCondition(key="applies_to_state", match=MatchValue(value="GA")),
    ])
)

# Search for Lawrenceville
lawrenceville_results = client.search(
    collection_name="georgia_law",
    query_vector=query_embedding,
    query_filter=Filter(should=[
        FieldCondition(key="applies_to_city", match=MatchValue(value="GA-LAWRENCEVILLE")),
        FieldCondition(key="primary_county", match=MatchValue(value="GA-GWINNETT")),
        FieldCondition(key="applies_to_state", match=MatchValue(value="GA")),
    ])
)

# Compare results...
```

## Implementation Plan

### Step 1: Create regions table and populate

```bash
# Add to scripts/init_db.py
python scripts/init_db.py --add-regions
```

### Step 2: Update ingestion to detect regions

```python
# In scripts/ingest.py

def enrich_with_jurisdiction(doc: Dict) -> Dict:
    """Add jurisdiction metadata to document."""

    # Detect region
    region_info = detect_region_from_source(doc)
    region_id = region_info['region_id']

    # Get hierarchy
    hierarchy = get_region_hierarchy(region_id)

    # Add to document
    doc['region_type'] = region_info['region_type']
    doc['region_id'] = region_id
    doc['region_name'] = hierarchy[-1]['name']
    doc['jurisdiction_hierarchy'] = hierarchy

    # Add denormalized fields for filtering
    doc['applies_to_country'] = hierarchy[0]['id'] if len(hierarchy) > 0 else None
    doc['applies_to_state'] = hierarchy[1]['id'] if len(hierarchy) > 1 else None
    doc['applies_to_county'] = hierarchy[2]['id'] if len(hierarchy) > 2 else None
    doc['applies_to_city'] = hierarchy[3]['id'] if len(hierarchy) > 3 else None

    return doc
```

### Step 3: Update search to support jurisdiction filtering

```python
# In scripts/search.py

def search_by_jurisdiction(
    query: str,
    region_id: str,
    include_parent_jurisdictions: bool = True
):
    """
    Search within a specific jurisdiction.

    Args:
        query: Search query
        region_id: Region ID (e.g., 'GA-GWINNETT')
        include_parent_jurisdictions: Include laws from parent jurisdictions (state, federal)
    """

    if include_parent_jurisdictions:
        # Get all applicable jurisdictions
        hierarchy = get_region_hierarchy(region_id)
        region_ids = [r['id'] for r in hierarchy]

        # Search across all applicable jurisdictions
        filter_conditions = [
            FieldCondition(key=f"applies_to_{r['type'].lower()}", match=MatchValue(value=r['id']))
            for r in hierarchy
        ]
    else:
        # Only this jurisdiction
        filter_conditions = [
            FieldCondition(key="region_id", match=MatchValue(value=region_id))
        ]

    # Execute search with jurisdiction filter
    # ...
```

## Edge Cases & Multi-County Considerations

### Challenge: Cities Spanning Multiple Counties

**Common scenarios in Georgia:**
- **Atlanta**: Spans Fulton (~90%), DeKalb (~9%), Cobb (~1%)
- **Columbus**: Primarily Muscogee County, touches Harris and Chattahoochee
- **Augusta-Richmond**: Consolidated city-county, but touches Columbia County
- **Sandy Springs**: Mostly Fulton, small part in Cobb

**Implications:**
1. **County ordinances** from ALL counties may apply to different parts of the city
2. **Property at county border** may be subject to ordinances from multiple counties
3. **Court jurisdiction** depends on which part of city the case originates
4. **Tax rates** differ by county portion

### Design Decisions

**Option 1: Include ALL counties** (RECOMMENDED)
- Store all counties in `applies_to_counties` array
- Search includes ordinances from all relevant counties
- User sees: "Atlanta (Fulton, DeKalb, Cobb Counties)"
- **Pro**: Most comprehensive, legally accurate
- **Con**: More complex queries, may return county laws that don't apply to specific address

**Option 2: Primary county only**
- Store only primary county (highest coverage)
- Simpler queries and results
- **Pro**: Simpler implementation
- **Con**: May miss applicable laws from secondary counties

**Our approach**: Implement Option 1 (all counties) but provide filtering:
```python
search_in_jurisdiction(
    city_id="GA-ATLANTA",
    include_all_counties=True,  # Default: True
    primary_county_only=False
)
```

### Address-Specific Lookups (Future Enhancement)

For precise legal research, need actual address:
```python
# Input: "123 Main St, Atlanta, GA 30303"
# Lookup: Which specific county?
# Output: "GA-FULTON"
# Then: Search laws applicable to Fulton County portion of Atlanta
```

This requires geocoding and county boundary data (future Phase 4).

### Data Quality Considerations

**Challenge**: Determining which cities span multiple counties

**Solutions**:
1. **US Census TIGER/Line shapefiles** - Authoritative boundary data
2. **Census Place definitions** - Cities and their county relationships
3. **Manual verification** - For Georgia's 159 counties and 500+ cities

**Implementation priority**:
1. Phase 1: Manually curate major cities (Atlanta, Columbus, Augusta, etc.)
2. Phase 2: Add US Census data import for all GA cities
3. Phase 3: Add address-specific lookup with geocoding

## Region Data Sources

To populate the regions table:

1. **US Census Bureau** - County/city data with FIPS codes
2. **US Postal Service** - State codes
3. **Georgia GIS** - County boundaries and cities
4. **Manual curation** - For accuracy

Example data file: `data/georgia_regions.json`

```json
{
  "regions": [
    {
      "id": "US",
      "name": "United States",
      "type": "COUNTRY",
      "parent_id": null
    },
    {
      "id": "GA",
      "name": "Georgia",
      "type": "STATE",
      "parent_id": "US",
      "state_code": "GA",
      "fips_code": "13"
    },
    {
      "id": "GA-GWINNETT",
      "name": "Gwinnett County",
      "type": "COUNTY",
      "parent_id": "GA",
      "state_code": "GA",
      "fips_code": "13135"
    },
    {
      "id": "GA-GWINNETT-LAWRENCEVILLE",
      "name": "Lawrenceville",
      "type": "CITY",
      "parent_id": "GA-GWINNETT",
      "state_code": "GA"
    }
  ]
}
```

## Benefits

1. **Accurate jurisdiction filtering** - "Show me laws for Atlanta"
2. **Hierarchical understanding** - City laws inherit from county/state
3. **Comparative analysis** - Compare laws between jurisdictions
4. **Compliance checking** - "What laws apply at this address?"
5. **Scalability** - Easy to add new cities/counties/states

## Next Steps

1. Create regions table and populate with GA data
2. Update ingestion pipeline to detect and enrich jurisdictions
3. Update search to support jurisdiction filtering
4. Add Make commands for region-based search
5. Build UI showing jurisdiction hierarchy

Should I implement this jurisdiction system now?
