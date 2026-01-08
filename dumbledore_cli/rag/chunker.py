"""Smart chunking for notes content."""

import re
from dataclasses import dataclass
from typing import Optional

from ..config import CHUNK_SIZE, CHUNK_OVERLAP


@dataclass
class Chunk:
    """A chunk of text from a note."""
    text: str
    note_id: str
    note_title: str
    chunk_index: int
    metadata: Optional[dict] = None


def estimate_tokens(text: str) -> int:
    """Rough token estimation (words * 1.3)."""
    return int(len(text.split()) * 1.3)


def chunk_by_structure(text: str, note_id: str, note_title: str) -> list[Chunk]:
    """Chunk text by structure (headers, paragraphs) first, then by size.

    This preserves semantic boundaries better than fixed-size chunking.
    """
    chunks = []

    # Split by double newlines (paragraphs) or headers
    # This regex splits on blank lines or lines starting with # or bullet points
    sections = re.split(r'\n\s*\n|\n(?=#)', text)

    current_chunk = ""
    chunk_index = 0

    for section in sections:
        section = section.strip()
        if not section:
            continue

        # Check if adding this section would exceed chunk size
        combined = f"{current_chunk}\n\n{section}".strip() if current_chunk else section

        if estimate_tokens(combined) <= CHUNK_SIZE:
            current_chunk = combined
        else:
            # Save current chunk if it has content
            if current_chunk:
                chunks.append(Chunk(
                    text=current_chunk,
                    note_id=note_id,
                    note_title=note_title,
                    chunk_index=chunk_index,
                ))
                chunk_index += 1

            # Start new chunk with this section
            # If section itself is too large, split it further
            if estimate_tokens(section) > CHUNK_SIZE:
                sub_chunks = chunk_by_sentences(section, note_id, note_title, chunk_index)
                chunks.extend(sub_chunks)
                chunk_index += len(sub_chunks)
                current_chunk = ""
            else:
                current_chunk = section

    # Don't forget the last chunk
    if current_chunk:
        chunks.append(Chunk(
            text=current_chunk,
            note_id=note_id,
            note_title=note_title,
            chunk_index=chunk_index,
        ))

    return chunks


def chunk_by_sentences(text: str, note_id: str, note_title: str, start_index: int = 0) -> list[Chunk]:
    """Chunk text by sentences when paragraphs are too large."""
    chunks = []

    # Split by sentence endings
    sentences = re.split(r'(?<=[.!?])\s+', text)

    current_chunk = ""
    chunk_index = start_index

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        combined = f"{current_chunk} {sentence}".strip() if current_chunk else sentence

        if estimate_tokens(combined) <= CHUNK_SIZE:
            current_chunk = combined
        else:
            if current_chunk:
                chunks.append(Chunk(
                    text=current_chunk,
                    note_id=note_id,
                    note_title=note_title,
                    chunk_index=chunk_index,
                ))
                chunk_index += 1

            # If single sentence is too long, just include it (edge case)
            current_chunk = sentence

    if current_chunk:
        chunks.append(Chunk(
            text=current_chunk,
            note_id=note_id,
            note_title=note_title,
            chunk_index=chunk_index,
        ))

    return chunks


def chunk_note(note_id: str, note_title: str, note_body: str) -> list[Chunk]:
    """Chunk a single note into searchable pieces.

    Strategy:
    1. If note is small enough, keep it as one chunk
    2. Otherwise, split by structure (paragraphs, headers)
    3. Add note title as context prefix to each chunk
    """
    # Clean the body
    body = note_body.strip()

    if not body:
        return []

    # If small enough, return as single chunk
    if estimate_tokens(body) <= CHUNK_SIZE:
        return [Chunk(
            text=f"[Note: {note_title}]\n\n{body}",
            note_id=note_id,
            note_title=note_title,
            chunk_index=0,
        )]

    # Otherwise, chunk by structure
    raw_chunks = chunk_by_structure(body, note_id, note_title)

    # Add title context to each chunk
    for chunk in raw_chunks:
        chunk.text = f"[Note: {note_title}]\n\n{chunk.text}"

    return raw_chunks


def chunk_notes(notes: list) -> list[Chunk]:
    """Chunk multiple notes.

    Args:
        notes: List of Note objects with id, title, body attributes

    Returns:
        List of all chunks from all notes
    """
    all_chunks = []

    for note in notes:
        chunks = chunk_note(note.id, note.title, note.body)
        all_chunks.extend(chunks)

    return all_chunks
