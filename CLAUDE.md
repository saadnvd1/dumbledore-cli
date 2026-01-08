# dumbledore-cli

Personal AI advisor with RAG-powered context from Apple Notes. Uses local embeddings and vector search for scalable context retrieval.

## Architecture

```
dumbledore_cli/
├── cli.py              # Typer CLI commands
├── ai.py               # Claude CLI integration
├── db.py               # SQLite for conversations/metadata
├── notes.py            # AppleScript bridge to Apple Notes
├── config.py           # Settings and paths
└── rag/
    ├── embeddings.py   # sentence-transformers wrapper
    ├── vectorstore.py  # ChromaDB operations
    ├── chunker.py      # Smart note chunking
    └── retriever.py    # RAG context retrieval

data/
├── dumbledore.db       # SQLite (conversations, sync metadata)
└── chroma/             # ChromaDB vector storage
```

## Key Components

- **Apple Notes Integration**: Uses AppleScript to pull notes directly from Notes.app (syncs with iPhone via iCloud)
- **Local Embeddings**: sentence-transformers `all-MiniLM-L6-v2` (22MB, no API calls)
- **Vector Store**: ChromaDB for persistent local vector storage
- **Smart Chunking**: Structure-aware chunking that preserves semantic boundaries
- **Profile Note**: Special note titled "Who am I?" always included in context

## Commands

```bash
dumbledore sync              # Pull notes from Apple Notes
dumbledore chat              # Interactive session
dumbledore ask "question"    # One-off question
dumbledore search "query"    # Semantic search
dumbledore notes             # List synced notes
dumbledore stats             # Knowledge base stats
dumbledore profile           # View profile note
dumbledore conversations     # List past conversations
dumbledore clear             # Clear synced data
```

## RAG Pipeline

1. **Sync**: Notes → AppleScript → Chunk → Embed → ChromaDB
2. **Query**: Question → Embed → Similarity search → Top-k chunks → Context
3. **Response**: Profile + Relevant chunks + Conversation history → Claude CLI

## Setup

```bash
pip install -e .
dumbledore sync
dumbledore chat
```

## Standards

- Conventional commits (feat, fix, docs, etc.)
- Keep code simple and readable
- Python 3.11+, Typer, Rich, ChromaDB, sentence-transformers
