"""Configuration and paths for Dumbledore CLI."""

from pathlib import Path

# Data directories - use ~/.dumbledore for user-global storage
DATA_DIR = Path.home() / ".dumbledore"
DB_PATH = DATA_DIR / "dumbledore.db"
CHROMA_PATH = DATA_DIR / "chroma"

# Embedding model
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

# RAG settings
CHUNK_SIZE = 512  # tokens
CHUNK_OVERLAP = 50  # tokens
TOP_K_RESULTS = 5  # number of chunks to retrieve

# Profile note title (the note that defines who you are)
PROFILE_NOTE_TITLE = "Who am I?"

# Auto-sync settings
AUTO_SYNC_HOURS = 24  # Auto-sync if last sync was more than this many hours ago

# Ensure directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
