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

# Style profile title (generated writing style guide)
STYLE_PROFILE_TITLE = "Writing Style Profile"

# Auto-sync settings
AUTO_SYNC_HOURS = 2  # Auto-sync if last sync was more than this many hours ago

# Additional markdown sources (local directories)
MARKDOWN_SOURCES = [
    Path.home() / ".lumifyhub" / "pages",
]

# Project docs directory (scans for README.md and CLAUDE.md)
DEV_DIR = Path.home() / "dev"

# Ensure directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
