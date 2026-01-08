"""Conversation memory - embed past conversations for RAG retrieval."""

from datetime import datetime
from typing import Optional

from rich.console import Console

from .. import db
from . import embeddings, vectorstore
from .chunker import Chunk

console = Console()

# Minimum exchanges to consider a conversation worth remembering
MIN_EXCHANGES = 3


def format_conversation(messages: list[dict], topic: str = "") -> str:
    """Format a conversation as text for embedding."""
    lines = []

    if topic:
        lines.append(f"Topic: {topic}")
        lines.append("")

    for msg in messages:
        role = "User" if msg["role"] == "user" else "Dumbledore"
        content = msg["content"]
        lines.append(f"{role}: {content}")
        lines.append("")

    return "\n".join(lines)


def chunk_conversation(
    conversation_id: int,
    messages: list[dict],
    topic: str = "",
) -> list[Chunk]:
    """Chunk a conversation into pieces for embedding.

    Conversations are treated as single chunks unless very long.
    """
    text = format_conversation(messages, topic)

    if not text.strip():
        return []

    # Create conversation ID for vector store
    conv_id = f"conv_{conversation_id}"
    conv_title = f"Conversation: {topic}" if topic else f"Conversation {conversation_id}"

    # Add timestamp context
    timestamp = datetime.now().strftime("%Y-%m-%d")
    text = f"[Conversation from {timestamp}]\n\n{text}"

    # For now, keep conversation as single chunk (most are small)
    # Could add splitting logic for very long conversations
    return [Chunk(
        text=text,
        note_id=conv_id,
        note_title=conv_title,
        chunk_index=0,
        metadata={"source": "conversation"},
    )]


def embed_conversation(conversation_id: int) -> int:
    """Embed a conversation into the vector store.

    Args:
        conversation_id: The conversation to embed

    Returns:
        Number of chunks embedded (0 if conversation too short)
    """
    # Get conversation messages
    messages = db.get_conversation_messages(conversation_id)

    if not messages:
        return 0

    # Count exchanges (user messages)
    user_messages = [m for m in messages if m["role"] == "user"]
    if len(user_messages) < MIN_EXCHANGES:
        return 0

    # Get conversation metadata
    conversations = db.get_recent_conversations(limit=100)
    conv = next((c for c in conversations if c["id"] == conversation_id), None)
    topic = conv.get("topic", "") if conv else ""

    # Chunk the conversation
    chunks = chunk_conversation(conversation_id, messages, topic)

    if not chunks:
        return 0

    # Embed chunks
    chunk_texts = [c.text for c in chunks]
    chunk_embeddings = embeddings.embed_texts(chunk_texts, show_progress=False)

    # Store in vector database with conversation metadata
    vectorstore.add_conversation_chunks(chunks, chunk_embeddings)

    return len(chunks)


def get_conversation_context(query: str, top_k: int = 3) -> list[dict]:
    """Retrieve relevant past conversations.

    Args:
        query: The current query
        top_k: Number of conversation chunks to retrieve

    Returns:
        List of relevant conversation chunks
    """
    query_embedding = embeddings.embed_text(query)

    # Search with source filter
    results = vectorstore.search(
        query_embedding,
        top_k=top_k,
        where={"source": "conversation"},
    )

    return results
