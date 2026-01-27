"""Session management for chat history."""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

from .config import get_history_dir

SYSTEM_PROMPT = """You are a knowledgeable legal research assistant specializing in Georgia law.

## Your Expertise
- Georgia statutes (O.C.G.A. - Official Code of Georgia Annotated)
- Georgia case law from the Supreme Court and Court of Appeals
- Local ordinances (county and municipal codes)

## Guidelines
1. **Always cite sources** - Reference specific statutes as O.C.G.A. § XX-XX-XX
2. **Be precise** - Legal matters require accuracy; distinguish between similar concepts
3. **Acknowledge limitations** - You provide legal information, not legal advice
4. **Use search results** - When provided, incorporate the relevant laws into your response
5. **Be thorough but concise** - Cover key points without unnecessary verbosity

## Formatting
- Use **bold** for statute citations and key terms
- Use bullet points for lists of elements or requirements
- Quote relevant statutory language when helpful

## Disclaimer
Always remind users that this is legal information for educational purposes and they should consult a licensed Georgia attorney for specific legal advice."""


class Message:
    """A single chat message."""
    
    def __init__(
        self,
        role: str,
        content: str,
        timestamp: Optional[datetime] = None,
        search_results: Optional[List[Dict]] = None,
    ):
        self.role = role
        self.content = content
        self.timestamp = timestamp or datetime.now()
        self.search_results = search_results or []
    
    def to_dict(self) -> Dict:
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "search_results": self.search_results,
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "Message":
        return cls(
            role=data["role"],
            content=data["content"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            search_results=data.get("search_results", []),
        )
    
    def to_api_format(self) -> Dict[str, str]:
        """Convert to format expected by LLM APIs."""
        return {"role": self.role, "content": self.content}


class Session:
    """A chat session with history."""
    
    def __init__(
        self,
        session_id: Optional[str] = None,
        title: Optional[str] = None,
    ):
        self.session_id = session_id or str(uuid.uuid4())[:8]
        self.title = title
        self.created_at = datetime.now()
        self.updated_at = datetime.now()
        self.messages: List[Message] = []
    
    @property
    def file_path(self) -> Path:
        return get_history_dir() / f"{self.session_id}.json"
    
    def add_message(
        self,
        role: str,
        content: str,
        search_results: Optional[List[Dict]] = None,
    ) -> Message:
        """Add a message to the session."""
        msg = Message(role, content, search_results=search_results)
        self.messages.append(msg)
        self.updated_at = datetime.now()
        
        # Auto-set title from first user message
        if not self.title and role == "user":
            self.title = content[:50] + ("..." if len(content) > 50 else "")
        
        return msg
    
    def get_api_messages(self, include_context: bool = True) -> List[Dict[str, str]]:
        """Get messages in API format with system prompt."""
        api_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        
        for msg in self.messages:
            if msg.role == "user" and include_context and msg.search_results:
                # Inject search context
                from .search import format_search_context
                context = format_search_context(msg.search_results)
                content = f"{context}\n\n**User Question:** {msg.content}"
                api_messages.append({"role": "user", "content": content})
            else:
                api_messages.append(msg.to_api_format())
        
        return api_messages
    
    def save(self) -> None:
        """Save session to disk."""
        data = {
            "session_id": self.session_id,
            "title": self.title,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "messages": [m.to_dict() for m in self.messages],
        }
        
        with open(self.file_path, "w") as f:
            json.dump(data, f, indent=2)
    
    @classmethod
    def load(cls, session_id: str) -> Optional["Session"]:
        """Load a session from disk."""
        path = get_history_dir() / f"{session_id}.json"
        
        if not path.exists():
            return None
        
        with open(path) as f:
            data = json.load(f)
        
        session = cls(
            session_id=data["session_id"],
            title=data.get("title"),
        )
        session.created_at = datetime.fromisoformat(data["created_at"])
        session.updated_at = datetime.fromisoformat(data["updated_at"])
        session.messages = [Message.from_dict(m) for m in data["messages"]]
        
        return session
    
    def clear(self) -> None:
        """Clear all messages."""
        self.messages = []
        self.title = None
        self.updated_at = datetime.now()


def list_sessions(limit: int = 20) -> List[Dict]:
    """List recent sessions."""
    history_dir = get_history_dir()
    sessions = []
    
    for path in sorted(history_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        if len(sessions) >= limit:
            break
        
        try:
            with open(path) as f:
                data = json.load(f)
            
            sessions.append({
                "session_id": data["session_id"],
                "title": data.get("title", "Untitled"),
                "created_at": data["created_at"],
                "updated_at": data["updated_at"],
                "message_count": len(data.get("messages", [])),
            })
        except:
            continue
    
    return sessions


def delete_session(session_id: str) -> bool:
    """Delete a session."""
    path = get_history_dir() / f"{session_id}.json"
    if path.exists():
        path.unlink()
        return True
    return False
