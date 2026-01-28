"""Vector search integration."""

import os
import ssl
import warnings
from typing import List, Dict, Optional
from .config import Config

# Completely disable SSL verification before any imports
os.environ['CURL_CA_BUNDLE'] = ''
os.environ['REQUESTS_CA_BUNDLE'] = ''
os.environ['SSL_CERT_FILE'] = ''
os.environ['SSL_CERT_DIR'] = ''
os.environ['PYTHONHTTPSVERIFY'] = '0'

import ssl as ssl_module
ssl_module._create_default_https_context = ssl_module._create_unverified_context

# Disable warnings
warnings.filterwarnings('ignore')

# Cache the model at module level to avoid reloading
_model_cache = None


def expand_query(query: str, config: Config) -> str:
    """
    Use LLM to expand and enrich the search query with legal concepts.

    Args:
        query: Original user query
        config: Configuration object

    Returns:
        Enriched query string with key legal terms and concepts
    """
    try:
        from .llm import get_llm_client

        llm = get_llm_client(config)

        expansion_prompt = f"""You are a legal research assistant. Analyze this query and extract key legal concepts, statutes, and terms that would help find relevant Georgia laws.

User query: "{query}"

Provide:
1. Key legal concepts and topics
2. Relevant statute areas (e.g., contracts, torts, criminal law, property law)
3. Important legal terms and synonyms
4. Related Georgia Code sections if identifiable (O.C.G.A.)

Return ONLY a concise enriched search query (2-3 sentences max) that includes the original intent plus expanded legal terminology. Do not include explanations or formatting."""

        messages = [{"role": "user", "content": expansion_prompt}]
        enriched = llm.chat(messages, stream=False)

        # Combine original query with enrichment
        expanded = f"{query} {enriched}"
        print(f"DEBUG: Query expanded from '{query}' to '{expanded[:100]}...'")
        return expanded

    except Exception as e:
        # If expansion fails, return original query
        print(f"DEBUG: Query expansion failed: {e}, using original query")
        return query


def search_laws(
    query: str,
    config: Config,
    limit: Optional[int] = None,
    expand: bool = True,
) -> List[Dict]:
    """
    Search for relevant laws using pgvector similarity search.

    Args:
        query: Search query
        config: Configuration object
        limit: Max results (uses config default if not specified)
        expand: Whether to use LLM query expansion (default: True)

    Returns:
        List of search results with cite, title, text, source, score
    """
    try:
        import psycopg2
        global _model_cache

        limit = limit or config.search_limit

        # Expand query using LLM for better semantic search
        search_query = expand_query(query, config) if expand else query

        # Try vector search, fall back to text search if it fails
        use_vector_search = False
        query_vector = None

        try:
            from sentence_transformers import SentenceTransformer

            # Load model (use cached version if available)
            if _model_cache is None:
                _model_cache = SentenceTransformer('all-mpnet-base-v2')

            model = _model_cache
            # Generate query embedding from expanded query
            query_vector = model.encode(search_query, convert_to_numpy=True).tolist()
            use_vector_search = True
        except Exception as model_error:
            # Fall back to text search
            print(f"Vector search unavailable, using text search: {model_error}")
            use_vector_search = False

        # Connect to PostgreSQL
        print(f"DEBUG: Connecting to DB {config.postgres_db} at {config.postgres_host}:{config.postgres_port}")
        conn = psycopg2.connect(
            host=config.postgres_host,
            port=config.postgres_port,
            database=config.postgres_db,
            user=config.postgres_user,
            password=config.postgres_password
        )
        cur = conn.cursor()
        print(f"DEBUG: Connected successfully")

        # Build WHERE clause for region filtering
        region_filter = ""
        region = config.region
        if region:
            if len(region) == 2:  # State code
                region_filter = f"AND applies_to_state = '{region}'"
            elif "-" in region:  # County/city like "GA-GWINNETT"
                region_filter = f"AND region_id = '{region}'"

        # Use vector or text search depending on availability
        if use_vector_search and query_vector:
            # Vector similarity search
            query_sql = f"""
                SELECT
                    cite,
                    title,
                    chunk_text as text,
                    source,
                    source_url,
                    1 - (embedding <=> %s::vector) as score
                FROM chunks
                WHERE 1=1 {region_filter}
                ORDER BY embedding <=> %s::vector
                LIMIT %s
            """
            cur.execute(query_sql, (query_vector, query_vector, limit))
        else:
            # Fallback to text search - search for ANY of the words
            words = [w.strip() for w in search_query.split() if len(w.strip()) > 2]
            print(f"DEBUG: Using text search for words: {words}")

            # Build OR conditions for each word
            where_conditions = []
            params = []
            for word in words:
                word_pattern = f"%{word}%"
                where_conditions.append(f"(chunk_text ILIKE %s OR title ILIKE %s OR cite ILIKE %s)")
                params.extend([word_pattern, word_pattern, word_pattern])

            where_clause = " OR ".join(where_conditions) if where_conditions else "1=1"

            query_sql = f"""
                SELECT DISTINCT
                    cite,
                    title,
                    chunk_text as text,
                    source,
                    source_url,
                    0.5 as score
                FROM chunks
                WHERE ({where_clause}) {region_filter}
                ORDER BY cite
                LIMIT %s
            """
            params.append(limit)

            print(f"DEBUG: Executing text search with {len(words)} words, limit: {limit}")
            cur.execute(query_sql, params)

        results = cur.fetchall()

        print(f"DEBUG: Executed query, got {len(results)} raw results")

        # Format results
        formatted = []
        for row in results:
            cite, title, text, source, source_url, score = row
            formatted.append({
                'cite': cite or 'N/A',
                'title': title or 'Untitled',
                'text': (text or '')[:1500],
                'source': source or 'UNKNOWN',
                'score': round(float(score), 4),  # Convert Decimal to float
                'url': source_url or '',
            })

        cur.close()
        conn.close()

        return formatted

    except Exception as e:
        # Return empty list if search fails (db not ready, etc.)
        print(f"Search error: {e}")
        import traceback
        traceback.print_exc()
        return []


def format_search_context(results: List[Dict]) -> str:
    """Format search results as context for the LLM."""
    if not results:
        return ""
    
    parts = ["[Relevant Georgia Laws Found]\n"]
    
    for i, r in enumerate(results, 1):
        parts.append(f"""
### {i}. {r['cite']} - {r['title']}
**Source:** {r['source']} | **Relevance:** {r['score']}

{r['text']}

---""")
    
    return "\n".join(parts)
