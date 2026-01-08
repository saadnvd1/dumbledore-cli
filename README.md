# Dumbledore

Your personal AI advisor that actually knows you. Dumbledore uses RAG to pull context from your notes, giving you personalized advice grounded in your goals, projects, and life context.

> If you find this helpful, please consider giving the repo a star!

## Why Dumbledore?

Generic AI assistants don't know anything about you. Dumbledore changes that by:

- **Knowing your context** - Syncs from your personal notes (Apple Notes, markdown files, or [LumifyHub](https://www.lumifyhub.io/cli))
- **Local-first** - Embeddings run locally, your data stays on your machine
- **Learning over time** - Conversations are remembered and become part of your knowledge base
- **Profile-aware** - Your "Who am I?" note is always included for personalized responses

## Data Sources

Dumbledore supports multiple knowledge sources:

| Source | Best For | Setup |
|--------|----------|-------|
| **Apple Notes** | iPhone/Mac users with iCloud sync | Just works on macOS |
| **Markdown files** | Obsidian, Logseq, or any local notes | Point to your folder |
| **[LumifyHub](https://www.lumifyhub.io/cli)** | Structured knowledge management | Export to markdown, sync that folder |

## Quick Start

```bash
# Install
pip install dumbledore-cli

# Or install from source
git clone https://github.com/saadnvd1/dumbledore-cli
cd dumbledore-cli
pip install -e .

# Sync your knowledge
dumbledore sync                           # Apple Notes (macOS)
dumbledore sync --markdown ~/notes        # Markdown folder
dumbledore sync --markdown ~/LumifyHub    # LumifyHub export

# Start chatting
dumbledore chat
```

## Usage

### Syncing Your Notes

```bash
# Apple Notes (macOS only)
dumbledore sync                    # Sync all notes
dumbledore sync --limit 100        # Sync first 100 notes

# Markdown files (works everywhere)
dumbledore sync --markdown ~/path/to/notes
dumbledore sync --markdown ~/Obsidian/vault
dumbledore sync --markdown ~/LumifyHub

# Combine sources
dumbledore sync --markdown ~/notes  # Then run:
dumbledore sync                     # Adds Apple Notes too

# Fresh start
dumbledore sync --clear             # Clear and re-sync
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
dumbledore ask "Based on my notes, what should I focus on?"
```

### Search Your Knowledge

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

Create a note titled **"Who am I?"** with information about yourself:

- Who you are
- Your goals and values
- Current projects
- What matters to you

This note is always included in context, so Dumbledore knows who it's talking to.

## How It Works

```
[Your Notes] → Sync → Chunk → Embed locally → ChromaDB

[You ask a question]
    ↓
Question → Embed → Vector similarity search → Top-k relevant chunks
    ↓
Profile + Relevant context + Conversation history → Claude → Response
    ↓
Conversation saved → Embedded for future context
```

## Using with LumifyHub

[LumifyHub](https://www.lumifyhub.io) is a modern workspace for docs, chat, and boards with AI built-in. Use the [LumifyHub CLI](https://www.lumifyhub.io/cli) to sync your pages locally as markdown:

```bash
npm install -g lumifyhub-cli
```

LumifyHub is ideal for:

- Team knowledge bases and documentation
- Structured note organization
- Clean markdown export for local AI use

To use with Dumbledore:

```bash
# Pull your LumifyHub pages locally
lh login
lh pull

# Sync with Dumbledore (pages are stored in ~/.lumifyhub/pages/)
dumbledore sync --markdown ~/.lumifyhub/pages
```

This gives you the best of both worlds: LumifyHub for collaborative knowledge management, Dumbledore for personal AI-powered retrieval.

## Tech Stack

- **Embeddings**: sentence-transformers `all-MiniLM-L6-v2` (22MB, runs locally)
- **Vector DB**: ChromaDB (local, persistent)
- **LLM**: Claude (via Claude CLI)
- **CLI**: Typer + Rich

## Requirements

- Python 3.11+
- Claude CLI (`npm install -g @anthropic-ai/claude-code`)
- macOS (only for Apple Notes integration - markdown works everywhere)

## Installation

```bash
# From PyPI (coming soon)
pip install dumbledore-cli

# From source
git clone https://github.com/saadnvd1/dumbledore-cli
cd dumbledore-cli
pip install -e .
```

## Contributing

Contributions welcome! Please open an issue or PR.

## License

MIT

