"""Dumbledore CLI - Personal AI advisor with RAG-powered context."""

from datetime import datetime, timedelta
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.markdown import Markdown

from . import ai, db, notes
from .config import PROFILE_NOTE_TITLE, AUTO_SYNC_HOURS
from .rag import chunker, embeddings, retriever, vectorstore

app = typer.Typer(
    name="dumbledore",
    help="Personal AI advisor with RAG-powered context from Apple Notes",
    no_args_is_help=True,
)
console = Console()


def needs_sync() -> bool:
    """Check if we need to sync (no data or stale)."""
    stats = db.get_sync_stats()

    # No notes synced
    if stats["note_count"] == 0:
        return True

    # Check if last sync is stale
    if stats["last_sync"]:
        try:
            last_sync = datetime.fromisoformat(stats["last_sync"])
            if datetime.now() - last_sync > timedelta(hours=AUTO_SYNC_HOURS):
                return True
        except (ValueError, TypeError):
            return True

    return False


def auto_sync_if_needed(limit: int = 200) -> bool:
    """Auto-sync if needed. Returns True if sync was performed."""
    if not needs_sync():
        return False

    stats = db.get_sync_stats()
    if stats["note_count"] == 0:
        console.print("[yellow]No notes synced yet. Running initial sync...[/yellow]\n")
    else:
        console.print("[dim]Notes are stale, syncing in background...[/dim]\n")

    # Run sync
    run_sync(limit=limit, clear=False, silent=True)
    return True


def run_sync(limit: Optional[int] = None, clear: bool = False, silent: bool = False):
    """Run the sync operation (smart incremental sync)."""
    if clear:
        if not silent:
            console.print("[yellow]Clearing existing data...[/yellow]")
        chunk_count = vectorstore.clear_all()
        db.clear_sync_records()
        if not silent:
            console.print(f"[dim]Cleared {chunk_count} chunks[/dim]")

    if not silent:
        console.print("[bold]Syncing notes from Apple Notes...[/bold]\n")

    # Get notes from Apple Notes
    all_notes = notes.get_all_notes(limit=limit, show_progress=not silent)

    if not all_notes:
        if not silent:
            console.print("[yellow]No notes found. Make sure Notes app has notes and permissions are granted.[/yellow]")
        return

    if not silent:
        console.print(f"[green]Found {len(all_notes)} notes[/green]")

    # Smart sync: only process new or modified notes
    notes_to_sync = []
    for note in all_notes:
        stored_mod = db.get_synced_note_modified_at(note.id)
        note_mod = note.modification_date.isoformat() if note.modification_date else None

        # Sync if: new note, no stored mod date, or modification date changed
        if stored_mod is None or note_mod is None or stored_mod != note_mod:
            notes_to_sync.append(note)

    if not notes_to_sync:
        if not silent:
            console.print("[dim]All notes up to date, nothing to sync.[/dim]")
        return

    if not silent:
        console.print(f"[dim]{len(notes_to_sync)} notes need updating...[/dim]\n")
        console.print("[dim]Chunking notes...[/dim]")

    all_chunks = chunker.chunk_notes(notes_to_sync)

    if not silent:
        console.print(f"[dim]Created {len(all_chunks)} chunks[/dim]\n")

    # Embed all chunks
    chunk_texts = [c.text for c in all_chunks]
    chunk_embeddings = embeddings.embed_texts(chunk_texts, show_progress=not silent)

    # Store in vector database
    if not silent:
        console.print("[dim]Storing in vector database...[/dim]")
    vectorstore.add_chunks(all_chunks, chunk_embeddings)

    # Record sync metadata with modification dates
    for note in notes_to_sync:
        note_chunks = [c for c in all_chunks if c.note_id == note.id]
        note_mod = note.modification_date.isoformat() if note.modification_date else None
        db.record_synced_note(note.id, note.title, len(note_chunks), note_mod)

    if not silent:
        console.print()
        console.print(Panel(
            f"[green]Synced {len(notes_to_sync)} notes ({len(all_chunks)} chunks)[/green]\n\n"
            f"Run [bold]dumbledore chat[/bold] to start talking!",
            title="Sync Complete",
            border_style="green",
        ))


@app.command()
def sync(
    limit: Optional[int] = typer.Option(None, "--limit", "-l", help="Limit number of notes to sync"),
    clear: bool = typer.Option(False, "--clear", "-c", help="Clear existing data before sync"),
):
    """Sync notes from Apple Notes into the knowledge base."""
    run_sync(limit=limit, clear=clear, silent=False)


@app.command()
def chat(
    continue_last: bool = typer.Option(False, "--continue", "-c", help="Continue last conversation"),
):
    """Start an interactive chat session with Dumbledore."""
    import questionary
    from questionary import Style

    custom_style = Style([
        ('qmark', 'fg:cyan bold'),
        ('question', 'fg:cyan bold'),
        ('answer', 'fg:white'),
    ])

    # Auto-sync if needed
    auto_sync_if_needed()

    # Check if we have any notes synced
    stats = db.get_sync_stats()
    if stats["note_count"] == 0:
        console.print(Panel(
            "[yellow]No notes synced yet![/yellow]\n\n"
            "Run [bold]dumbledore sync[/bold] first to import your Apple Notes.",
            title="Setup Required",
            border_style="yellow",
        ))
        return

    # Create or continue conversation
    if continue_last:
        last_conv = db.get_last_conversation()
        if last_conv:
            conversation_id = last_conv["id"]
            console.print(f"[dim]Continuing conversation: {last_conv.get('topic', 'Untitled')}[/dim]")
        else:
            conversation_id = db.create_conversation(topic="Chat session")
    else:
        conversation_id = db.create_conversation(topic="Chat session")

    console.print()
    console.print(Panel(
        "[bold green]Chat with Dumbledore[/bold green]\n\n"
        f"[dim]Knowledge base: {stats['note_count']} notes, {stats['chunk_count']} chunks[/dim]\n\n"
        "Ask me anything about your life, projects, or goals.\n"
        "I'll draw on your notes to give personalized advice.\n\n"
        "[dim]Type [bold]exit[/bold] to quit | [bold]/search <query>[/bold] to search notes[/dim]",
        border_style="green",
    ))

    # Load previous messages if continuing
    previous_messages = []
    if continue_last:
        previous_messages = db.get_conversation_messages(conversation_id, limit=20)
        if previous_messages:
            console.print("\n[dim]Previous messages loaded.[/dim]")

    while True:
        console.print()
        try:
            user_input = questionary.text(
                "You:",
                style=custom_style,
            ).ask()
        except (EOFError, KeyboardInterrupt):
            user_input = None

        if user_input is None:
            console.print("\n[dim]Goodbye![/dim]")
            break

        user_input = user_input.strip()

        if not user_input:
            continue

        if user_input.lower() in ("exit", "quit", "q", "bye"):
            console.print("[dim]Goodbye![/dim]")
            break

        # Handle /search command
        if user_input.startswith("/search "):
            query = user_input[8:].strip()
            if query:
                results = retriever.retrieve(query, top_k=5)
                console.print()
                console.print(Panel(
                    Markdown(retriever.format_search_results(results)),
                    title="[bold blue]Search Results[/bold blue]",
                    border_style="blue",
                ))
            continue

        # Handle /notes command
        if user_input == "/notes":
            show_notes_list()
            continue

        # Handle /stats command
        if user_input == "/stats":
            show_stats()
            continue

        # Save user message
        db.add_message(conversation_id, "user", user_input)

        # Build context from RAG
        context = retriever.build_context(user_input)

        # Add conversation history to context
        if previous_messages:
            history = "\n\n## Recent Conversation\n"
            for msg in previous_messages[-10:]:
                role = "User" if msg["role"] == "user" else "Dumbledore"
                content = msg["content"][:500] + "..." if len(msg["content"]) > 500 else msg["content"]
                history += f"**{role}:** {content}\n\n"
            context = f"{context}\n{history}" if context else history

        # Get response
        with ai.display_thinking():
            response = ai.run_claude(user_input, context)

        if response:
            db.add_message(conversation_id, "assistant", response)
            previous_messages.append({"role": "user", "content": user_input})
            previous_messages.append({"role": "assistant", "content": response})
            ai.display_response(response)
        else:
            console.print("[red]Failed to get response. Try again.[/red]")


@app.command()
def ask(
    question: str = typer.Argument(..., help="Your question for Dumbledore"),
):
    """Ask a single question (no interactive session)."""

    # Auto-sync if needed
    auto_sync_if_needed()

    # Check if we have notes
    stats = db.get_sync_stats()
    if stats["note_count"] == 0:
        console.print("[yellow]No notes synced. Run 'dumbledore sync' first.[/yellow]")
        console.print("[dim]Answering without personal context...[/dim]\n")
        context = None
    else:
        context = retriever.build_context(question)

    with ai.display_thinking():
        response = ai.run_claude(question, context)

    if response:
        ai.display_response(response)
    else:
        console.print("[red]Failed to get response.[/red]")


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query"),
    top_k: int = typer.Option(5, "--top", "-k", help="Number of results"),
):
    """Search your notes using semantic search."""

    stats = db.get_sync_stats()
    if stats["note_count"] == 0:
        console.print("[yellow]No notes synced. Run 'dumbledore sync' first.[/yellow]")
        return

    console.print(f"[dim]Searching for: {query}[/dim]\n")

    results = retriever.retrieve(query, top_k=top_k)

    console.print(Panel(
        Markdown(retriever.format_search_results(results)),
        title="[bold blue]Search Results[/bold blue]",
        border_style="blue",
    ))


@app.command("notes")
def list_notes():
    """List all synced notes."""
    show_notes_list()


def show_notes_list():
    """Display list of synced notes."""
    synced = db.get_synced_notes()

    if not synced:
        console.print("[yellow]No notes synced. Run 'dumbledore sync' first.[/yellow]")
        return

    table = Table(title="Synced Notes")
    table.add_column("Title", style="cyan")
    table.add_column("Chunks", justify="right")
    table.add_column("Synced At", style="dim")

    for note in synced[:50]:  # Limit display
        table.add_row(
            note["note_title"][:50] + ("..." if len(note["note_title"]) > 50 else ""),
            str(note["chunk_count"]),
            note["synced_at"][:16] if note["synced_at"] else "N/A",
        )

    if len(synced) > 50:
        table.add_row(f"... and {len(synced) - 50} more", "", "")

    console.print(table)


@app.command()
def stats():
    """Show knowledge base statistics."""
    show_stats()


def show_stats():
    """Display stats about the knowledge base."""
    sync_stats = db.get_sync_stats()
    chunk_count = vectorstore.get_chunk_count()
    conversations = db.get_recent_conversations(limit=5)

    console.print()
    console.print(Panel(
        f"[bold]Notes:[/bold] {sync_stats['note_count']}\n"
        f"[bold]Chunks:[/bold] {chunk_count}\n"
        f"[bold]Last Sync:[/bold] {sync_stats['last_sync'] or 'Never'}\n"
        f"[bold]Conversations:[/bold] {len(conversations)}",
        title="[bold blue]Knowledge Base Stats[/bold blue]",
        border_style="blue",
    ))


@app.command()
def profile():
    """View or set the profile note (who you are)."""

    console.print(f"[dim]Profile note title: \"{PROFILE_NOTE_TITLE}\"[/dim]\n")

    # Try to get profile from vector store
    profile_content = retriever.get_profile_context()

    if profile_content:
        console.print(Panel(
            Markdown(profile_content),
            title="[bold green]Your Profile[/bold green]",
            border_style="green",
        ))
    else:
        console.print(Panel(
            f"[yellow]No profile note found.[/yellow]\n\n"
            f"Create a note titled \"{PROFILE_NOTE_TITLE}\" in Apple Notes,\n"
            f"then run [bold]dumbledore sync[/bold] to import it.\n\n"
            f"This note should describe who you are, your goals,\n"
            f"values, and what matters to you.",
            title="Profile Setup",
            border_style="yellow",
        ))


@app.command()
def conversations():
    """List recent conversations."""

    convs = db.get_recent_conversations(limit=10)

    if not convs:
        console.print("[dim]No conversations yet. Run 'dumbledore chat' to start.[/dim]")
        return

    table = Table(title="Recent Conversations")
    table.add_column("ID", justify="right", style="dim")
    table.add_column("Topic", style="cyan")
    table.add_column("Messages", justify="right")
    table.add_column("Last Active", style="dim")

    for conv in convs:
        table.add_row(
            str(conv["id"]),
            conv.get("topic", "Untitled")[:40],
            str(conv["message_count"]),
            conv["last_message_at"][:16] if conv["last_message_at"] else "N/A",
        )

    console.print(table)
    console.print("\n[dim]Use 'dumbledore chat --continue' to continue the last conversation.[/dim]")


@app.command()
def clear(
    confirm: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    """Clear all synced data (keeps conversations)."""

    if not confirm:
        console.print("[yellow]This will delete all synced notes from the knowledge base.[/yellow]")
        console.print("[dim]Conversations will be kept.[/dim]\n")

        import questionary
        if not questionary.confirm("Are you sure?").ask():
            console.print("[dim]Cancelled.[/dim]")
            return

    chunk_count = vectorstore.clear_all()
    note_count = db.clear_sync_records()

    console.print(f"[green]Cleared {note_count} notes ({chunk_count} chunks)[/green]")


if __name__ == "__main__":
    app()
