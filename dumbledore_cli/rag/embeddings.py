"""Embedding model wrapper using sentence-transformers."""

from typing import Optional

from rich.console import Console

from ..config import EMBEDDING_MODEL

console = Console()

# Lazy load the model to avoid slow imports
_model = None


def get_model():
    """Get or initialize the embedding model."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        console.print(f"[dim]Loading embedding model: {EMBEDDING_MODEL}...[/dim]")
        _model = SentenceTransformer(EMBEDDING_MODEL)
        console.print("[dim]Model loaded.[/dim]")
    return _model


def embed_text(text: str) -> list[float]:
    """Embed a single text string."""
    model = get_model()
    embedding = model.encode(text, convert_to_numpy=True)
    return embedding.tolist()


def embed_texts(texts: list[str], show_progress: bool = True) -> list[list[float]]:
    """Embed multiple texts."""
    if not texts:
        return []

    model = get_model()

    if show_progress:
        console.print(f"[dim]Embedding {len(texts)} texts...[/dim]")

    embeddings = model.encode(
        texts,
        convert_to_numpy=True,
        show_progress_bar=show_progress and len(texts) > 10,
    )

    return embeddings.tolist()


def get_embedding_dimension() -> int:
    """Get the dimension of embeddings from the model."""
    model = get_model()
    return model.get_sentence_embedding_dimension()
