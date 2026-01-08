"""ChromaDB vector store for storing and searching note embeddings."""

from typing import Optional

import chromadb
from chromadb.config import Settings
from rich.console import Console

from ..config import CHROMA_PATH
from .chunker import Chunk

console = Console()

# Collection name
COLLECTION_NAME = "dumbledore_notes"

# Lazy load client
_client = None
_collection = None


def get_client() -> chromadb.PersistentClient:
    """Get or create ChromaDB client."""
    global _client
    if _client is None:
        CHROMA_PATH.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(
            path=str(CHROMA_PATH),
            settings=Settings(anonymized_telemetry=False),
        )
    return _client


def get_collection() -> chromadb.Collection:
    """Get or create the notes collection."""
    global _collection
    if _collection is None:
        client = get_client()
        _collection = client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"description": "Personal notes from Apple Notes"},
        )
    return _collection


def add_chunks(chunks: list[Chunk], embeddings: list[list[float]]) -> int:
    """Add chunks with their embeddings to the vector store.

    Returns number of chunks added.
    """
    if not chunks or not embeddings:
        return 0

    if len(chunks) != len(embeddings):
        raise ValueError(f"Mismatch: {len(chunks)} chunks but {len(embeddings)} embeddings")

    collection = get_collection()

    # Prepare data for ChromaDB
    ids = [f"{chunk.note_id}_{chunk.chunk_index}" for chunk in chunks]
    documents = [chunk.text for chunk in chunks]
    metadatas = [
        {
            "note_id": chunk.note_id,
            "note_title": chunk.note_title,
            "chunk_index": chunk.chunk_index,
        }
        for chunk in chunks
    ]

    # Upsert to handle updates
    collection.upsert(
        ids=ids,
        embeddings=embeddings,
        documents=documents,
        metadatas=metadatas,
    )

    return len(chunks)


def search(
    query_embedding: list[float],
    top_k: int = 5,
    where: Optional[dict] = None,
) -> list[dict]:
    """Search for similar chunks.

    Args:
        query_embedding: The embedding of the query
        top_k: Number of results to return
        where: Optional filter (e.g., {"note_title": "My Note"})

    Returns:
        List of results with document, metadata, and distance
    """
    collection = get_collection()

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        where=where,
        include=["documents", "metadatas", "distances"],
    )

    # Flatten results into list of dicts
    output = []
    if results["documents"] and results["documents"][0]:
        for i in range(len(results["documents"][0])):
            output.append({
                "document": results["documents"][0][i],
                "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                "distance": results["distances"][0][i] if results["distances"] else 0,
            })

    return output


def get_chunk_count() -> int:
    """Get total number of chunks in the store."""
    collection = get_collection()
    return collection.count()


def get_unique_notes() -> list[str]:
    """Get list of unique note titles in the store."""
    collection = get_collection()

    # Get all metadatas
    results = collection.get(include=["metadatas"])

    if not results["metadatas"]:
        return []

    titles = set()
    for metadata in results["metadatas"]:
        if metadata and "note_title" in metadata:
            titles.add(metadata["note_title"])

    return sorted(titles)


def delete_note(note_id: str) -> int:
    """Delete all chunks for a note.

    Returns number of chunks deleted.
    """
    collection = get_collection()

    # Find all chunks for this note
    results = collection.get(
        where={"note_id": note_id},
        include=["metadatas"],
    )

    if not results["ids"]:
        return 0

    # Delete them
    collection.delete(ids=results["ids"])

    return len(results["ids"])


def clear_all() -> int:
    """Clear all chunks from the store.

    Returns number of chunks deleted.
    """
    global _collection

    client = get_client()
    count = get_chunk_count()

    # Delete and recreate collection
    client.delete_collection(COLLECTION_NAME)
    _collection = None  # Reset cached collection

    return count


def get_chunks_by_note(note_title: str) -> list[dict]:
    """Get all chunks for a specific note."""
    collection = get_collection()

    results = collection.get(
        where={"note_title": note_title},
        include=["documents", "metadatas"],
    )

    output = []
    if results["documents"]:
        for i in range(len(results["documents"])):
            output.append({
                "document": results["documents"][i],
                "metadata": results["metadatas"][i] if results["metadatas"] else {},
            })

    return output
