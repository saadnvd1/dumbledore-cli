"""RAG retriever - combines embedding and search for context retrieval."""

from typing import Optional

from rich.console import Console

from ..config import TOP_K_RESULTS, PROFILE_NOTE_TITLE, STYLE_PROFILE_TITLE
from .. import db
from . import embeddings, vectorstore

console = Console()


def retrieve(query: str, top_k: int = TOP_K_RESULTS) -> list[dict]:
    """Retrieve relevant chunks for a query.

    Args:
        query: The user's question or topic
        top_k: Number of chunks to retrieve

    Returns:
        List of relevant chunks with metadata
    """
    # Embed the query
    query_embedding = embeddings.embed_text(query)

    # Search vector store
    results = vectorstore.search(query_embedding, top_k=top_k)

    return results


def get_profile_context() -> Optional[str]:
    """Get the profile note content (who you are).

    This is always included in context for personalized responses.
    """
    chunks = vectorstore.get_chunks_by_note(PROFILE_NOTE_TITLE)

    if not chunks:
        return None

    # Combine all chunks from profile note
    profile_text = "\n\n".join([c["document"] for c in chunks])

    return profile_text


def get_style_context() -> Optional[str]:
    """Get the writing style profile.

    This is included to help match the user's writing style.
    """
    chunks = vectorstore.get_chunks_by_note(STYLE_PROFILE_TITLE)

    if not chunks:
        return None

    # Get the style text (strip the note title prefix if present)
    text = chunks[0]["document"]
    prefix = f"[Note: {STYLE_PROFILE_TITLE}]\n\n"
    if text.startswith(prefix):
        text = text[len(prefix):]

    return text


def get_last_conversation_context(exclude_id: Optional[int] = None) -> Optional[str]:
    """Get a summary of the last conversation for context.

    Args:
        exclude_id: Conversation ID to exclude (the current conversation)
    """
    conversations = db.get_recent_conversations(limit=5)

    # Find the last conversation that's not the current one
    last_conv = None
    for conv in conversations:
        if exclude_id and conv["id"] == exclude_id:
            continue
        if conv["message_count"] >= 2:  # At least one exchange
            last_conv = conv
            break

    if not last_conv:
        return None

    messages = db.get_conversation_messages(last_conv["id"], limit=10)
    if not messages:
        return None

    # Format as brief summary
    lines = [f"Last conversation ({last_conv.get('last_message_at', '')[:10]}):"]
    for msg in messages[-6:]:  # Last 3 exchanges
        role = "User" if msg["role"] == "user" else "Dumbledore"
        content = msg["content"]
        if len(content) > 150:
            content = content[:150] + "..."
        lines.append(f"  {role}: {content}")

    return "\n".join(lines)


def build_context(query: str, top_k: int = TOP_K_RESULTS, include_conversations: bool = True, current_conversation_id: Optional[int] = None) -> str:
    """Build full context for a query.

    Includes:
    1. Profile note (who you are) - always included
    2. Writing style profile (if generated)
    3. Relevant chunks from semantic search (notes)
    4. Relevant past conversations (if enabled)

    Args:
        query: The user's question
        top_k: Number of chunks to retrieve
        include_conversations: Whether to include past conversation context

    Returns:
        Formatted context string for the LLM prompt
    """
    context_parts = []

    # 1. Profile context
    profile = get_profile_context()
    if profile:
        context_parts.append(f"## About the User\n{profile}")

    # 2. Writing style
    style = get_style_context()
    if style:
        context_parts.append(f"## Writing Style to Match\n{style}")

    # 3. Last conversation (explicit recall)
    if include_conversations:
        last_conv = get_last_conversation_context(exclude_id=current_conversation_id)
        if last_conv:
            context_parts.append(f"## {last_conv}")

    # 4. Relevant chunks from notes
    results = retrieve(query, top_k=top_k)

    note_chunks = []
    conversation_chunks = []
    seen_titles = set()

    for r in results:
        title = r["metadata"].get("note_title", "Unknown")
        doc = r["document"]
        source = r["metadata"].get("source", "note")

        seen_titles.add(title)

        if source == "conversation":
            conversation_chunks.append(doc)
        else:
            note_chunks.append(doc)

    if note_chunks:
        context_parts.append("## Relevant Notes\n" + "\n\n---\n\n".join(note_chunks))

    # 3. Past conversations (from RAG results or separate query)
    if include_conversations and conversation_chunks:
        context_parts.append("## Relevant Past Conversations\n" + "\n\n---\n\n".join(conversation_chunks))

    # Add source summary
    if seen_titles:
        context_parts.append(f"[Sources: {', '.join(sorted(seen_titles))}]")

    if not context_parts:
        return ""

    return "\n\n".join(context_parts)


def format_search_results(results: list[dict]) -> str:
    """Format search results for display."""
    if not results:
        return "No results found."

    output = []
    for i, r in enumerate(results, 1):
        title = r["metadata"].get("note_title", "Unknown")
        distance = r.get("distance", 0)

        # Convert distance to similarity score (0-100%)
        # ChromaDB uses L2 distance by default, smaller = more similar
        # Use exponential decay for more intuitive scoring
        if distance is not None:
            similarity = max(0, 100 * (1 / (1 + distance)))
            relevance = f"{similarity:.0f}%"
        else:
            relevance = "N/A"

        # Truncate document for display
        doc = r["document"]
        if len(doc) > 200:
            doc = doc[:200] + "..."

        output.append(f"**{i}. {title}** (relevance: {relevance})\n{doc}")

    return "\n\n".join(output)
