"""Writing style analysis and profile generation."""

import subprocess
from typing import Optional

from rich.console import Console

from .rag import embeddings, vectorstore
from .rag.chunker import Chunk
from .config import STYLE_PROFILE_TITLE

console = Console()

STYLE_ANALYSIS_PROMPT = """Analyze these writing samples and extract a concise style guide for mimicking this person's writing style.

Focus on:
- Tone and voice (casual, formal, conversational, etc.)
- Common phrases, expressions, or slang they use
- Sentence structure (short/long, fragments, complex)
- Punctuation habits (lowercase, minimal punctuation, etc.)
- Unique quirks or patterns

Output ONLY the style guide - a list of specific, actionable instructions for writing like this person.
Keep it under 300 words. Be specific, not generic.

Writing samples:
---
{samples}
---

Style guide:"""


def get_note_samples(max_chars: int = 15000) -> list[str]:
    """Get text samples from synced notes for style analysis.

    Returns a list of note text samples, prioritizing variety.
    """
    collection = vectorstore.get_collection()

    # Get all chunks
    results = collection.get(
        include=["documents", "metadatas"],
    )

    if not results["documents"]:
        return []

    # Group by note, take first chunk from each for variety
    note_samples = {}
    for i, doc in enumerate(results["documents"]):
        metadata = results["metadatas"][i] if results["metadatas"] else {}
        note_title = metadata.get("note_title", "")
        source = metadata.get("source", "note")

        # Skip conversation chunks and style profile itself
        if source == "conversation" or note_title == STYLE_PROFILE_TITLE:
            continue

        if note_title not in note_samples:
            note_samples[note_title] = doc

    # Collect samples up to max_chars
    samples = []
    total_chars = 0

    for title, text in note_samples.items():
        if total_chars + len(text) > max_chars:
            break
        samples.append(text)
        total_chars += len(text)

    return samples


def analyze_style(samples: list[str]) -> Optional[str]:
    """Use Claude to analyze writing style from samples.

    Returns the generated style guide text.
    """
    if not samples:
        console.print("[yellow]No note samples found to analyze.[/yellow]")
        return None

    combined = "\n\n---\n\n".join(samples)
    prompt = STYLE_ANALYSIS_PROMPT.format(samples=combined)

    try:
        result = subprocess.run(
            ["claude", "-p", prompt],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        else:
            console.print(f"[red]Claude error: {result.stderr}[/red]")
            return None
    except subprocess.TimeoutExpired:
        console.print("[red]Style analysis timed out[/red]")
        return None
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        return None


def save_style_profile(style_text: str) -> bool:
    """Save the style profile to the vector store.

    Stores as a special note that can be retrieved by title.
    """
    # Create a chunk for the style profile
    chunk = Chunk(
        text=f"[Note: {STYLE_PROFILE_TITLE}]\n\n{style_text}",
        note_id="style_profile",
        note_title=STYLE_PROFILE_TITLE,
        chunk_index=0,
        metadata={"source": "style"},
    )

    # Embed and store
    embedding = embeddings.embed_text(chunk.text)
    vectorstore.add_chunks([chunk], [embedding], source="style")

    return True


def get_style_profile() -> Optional[str]:
    """Get the current style profile if it exists."""
    chunks = vectorstore.get_chunks_by_note(STYLE_PROFILE_TITLE)

    if not chunks:
        return None

    # Return the text (strip the note title prefix if present)
    text = chunks[0]["document"]
    prefix = f"[Note: {STYLE_PROFILE_TITLE}]\n\n"
    if text.startswith(prefix):
        text = text[len(prefix):]

    return text


def clear_style_profile() -> bool:
    """Remove the style profile from the vector store."""
    deleted = vectorstore.delete_note("style_profile")
    return deleted > 0
