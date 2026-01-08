# dumbledore-cli

Personal AI advisor with RAG-powered context from your Apple Notes. Dumbledore knows your goals, projects, values, and life context to give personalized advice.

## Features

- **Apple Notes Integration** - Syncs directly from Notes.app (works with iPhone via iCloud)
- **Local RAG Pipeline** - Semantic search using local embeddings (no API calls for search)
- **Scalable Context** - Handles hundreds of notes efficiently via chunking + vector search
- **Conversation Memory** - Maintains context across chat sessions
- **Profile-Aware** - Always considers your "Who am I?" note for personalized responses

## Quick Start

```bash
# Install
cd ~/dev/dumbledore-cli
pip install -e .

# Sync your notes
dumbledore sync

# Start chatting
dumbledore chat
```

## Usage

### Sync Notes from Apple Notes

```bash
dumbledore sync              # Sync all notes
dumbledore sync --limit 100  # Sync first 100 notes
dumbledore sync --clear      # Clear and re-sync
```

### Chat with Dumbledore

```bash
dumbledore chat              # Start interactive session
dumbledore chat --continue   # Continue last conversation
```

In chat, you can use:
- `/search <query>` - Search your notes
- `/notes` - List synced notes
- `/stats` - Show stats
- `exit` - End session

### Quick Questions

```bash
dumbledore ask "Should I keep working on this project?"
dumbledore ask "What are my main goals right now?"
```

### Search Notes

```bash
dumbledore search "business ideas"
dumbledore search "workout routine" --top 10
```

### Other Commands

```bash
dumbledore notes          # List all synced notes
dumbledore stats          # Knowledge base statistics
dumbledore profile        # View your profile note
dumbledore conversations  # List past conversations
dumbledore clear          # Clear synced data
```

## Profile Note

Create a note in Apple Notes titled **"Who am I?"** with information about yourself:

- Who you are
- Your goals and values
- Current projects
- What matters to you

This note is always included in Dumbledore's context for personalized responses.

## How It Works

```
iPhone Notes → iCloud → macOS Notes.app → AppleScript → Dumbledore

[Sync]
Notes → Chunk by structure → Embed locally → Store in ChromaDB

[Query]
Question → Embed → Vector similarity search → Top-k relevant chunks
         → Build context (profile + chunks + history) → Claude CLI
```

## Tech Stack

- **Embeddings**: sentence-transformers `all-MiniLM-L6-v2` (22MB, local)
- **Vector DB**: ChromaDB (local, persistent)
- **LLM**: Claude CLI
- **CLI**: Typer + Rich

## Requirements

- macOS (for Apple Notes integration)
- Python 3.11+
- Claude CLI (`npm install -g @anthropic-ai/claude-code`)

## Dependencies

```
typer>=0.9.0
rich>=13.0.0
chromadb>=0.4.0
sentence-transformers>=2.2.0
questionary>=2.0.0
```
