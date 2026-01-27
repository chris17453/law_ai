"""Vector search integration."""

from typing import List, Dict, Optional
from .config import Config


def search_laws(
    query: str,
    config: Config,
    limit: Optional[int] = None,
) -> List[Dict]:
    """
    Search for relevant laws using vector similarity.
    
    Args:
        query: Search query
        config: Configuration object
        limit: Max results (uses config default if not specified)
    
    Returns:
        List of search results with cite, title, text, source, score
    """
    try:
        from qdrant_client import QdrantClient
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        from sentence_transformers import SentenceTransformer
        
        limit = limit or config.search_limit
        
        # Load model and connect
        model = SentenceTransformer('all-mpnet-base-v2')
        client = QdrantClient(config.qdrant_host, port=config.qdrant_port)
        
        # Generate query embedding
        query_vector = model.encode(query, convert_to_numpy=True).tolist()
        
        # Build filter for region
        conditions = []
        region = config.region
        if region:
            if len(region) == 2:  # State code
                conditions.append(
                    FieldCondition(key="applies_to_state", match=MatchValue(value=region))
                )
            elif "-" in region:  # County/city
                conditions.append(
                    FieldCondition(key="region_id", match=MatchValue(value=region))
                )
        
        search_filter = Filter(must=conditions) if conditions else None
        
        # Search
        results = client.search(
            collection_name="georgia_law",
            query_vector=query_vector,
            limit=limit,
            query_filter=search_filter,
            with_payload=True
        )
        
        # Format results
        formatted = []
        for hit in results:
            payload = hit.payload
            formatted.append({
                'cite': payload.get('cite', 'N/A'),
                'title': payload.get('title', 'Untitled'),
                'text': payload.get('text', '')[:1500],
                'source': payload.get('source', 'UNKNOWN'),
                'score': round(hit.score, 4),
                'url': payload.get('source_url', ''),
            })
        
        return formatted
        
    except Exception as e:
        # Return empty list if search fails (db not ready, etc.)
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
