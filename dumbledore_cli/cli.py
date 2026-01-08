"""Dumbledore CLI - Personal AI advisor with RAG-powered context."""

from datetime import datetime, timedelta
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.markdown import Markdown

from . import ai, db, notes, markdown, projects, style
from .config import PROFILE_NOTE_TITLE, AUTO_SYNC_HOURS, MARKDOWN_SOURCES, DEV_DIR
from .rag import chunker, embeddings, retriever, vectorstore, memory

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

    all_items_to_sync = []
    total_found = 0
    ids_to_fetch = []

    # 1. Sync Apple Notes (two-phase: metadata first, then content for changed notes)
    if not silent:
        console.print("[bold]Syncing from Apple Notes...[/bold]")

    # Phase 1: Get lightweight metadata to check what changed
    apple_metadata = notes.get_all_note_metadata(show_progress=not silent)
    if limit:
        apple_metadata = apple_metadata[:limit]
    total_found += len(apple_metadata)

    for meta in apple_metadata:
        stored_mod = db.get_synced_note_modified_at(meta.id)
        note_mod = meta.modification_date.isoformat() if meta.modification_date else None
        if stored_mod is None or note_mod is None or stored_mod != note_mod:
            ids_to_fetch.append(meta.id)

    # Phase 2: Fetch full content only for changed notes
    if ids_to_fetch:
        apple_notes = notes.get_notes_by_ids(ids_to_fetch, show_progress=not silent)
        all_items_to_sync.extend(apple_notes)
    elif not silent:
        console.print("[dim]All Apple Notes up to date[/dim]")

    # 2. Sync markdown files from configured sources
    for md_source in MARKDOWN_SOURCES:
        if md_source.exists():
            if not silent:
                console.print(f"\n[bold]Syncing from {md_source}...[/bold]")

            md_notes = markdown.get_markdown_files(md_source, show_progress=not silent)
            total_found += len(md_notes)

            for note in md_notes:
                stored_mod = db.get_synced_note_modified_at(note.id)
                note_mod = note.modification_date.isoformat() if note.modification_date else None
                if stored_mod is None or note_mod is None or stored_mod != note_mod:
                    all_items_to_sync.append(note)

    # 3. Sync project docs (README.md, CLAUDE.md from ~/dev/*)
    if DEV_DIR.exists():
        if not silent:
            console.print(f"\n[bold]Syncing project docs from {DEV_DIR}...[/bold]")

        project_docs = projects.get_project_docs(DEV_DIR, show_progress=not silent)
        total_found += len(project_docs)

        for note in project_docs:
            stored_mod = db.get_synced_note_modified_at(note.id)
            note_mod = note.modification_date.isoformat() if note.modification_date else None
            if stored_mod is None or note_mod is None or stored_mod != note_mod:
                all_items_to_sync.append(note)

    if not all_items_to_sync:
        if not silent:
            console.print(f"\n[dim]All {total_found} items up to date, nothing to sync.[/dim]")
        return

    if not silent:
        console.print(f"\n[dim]{len(all_items_to_sync)} items need updating...[/dim]")
        console.print("[dim]Chunking...[/dim]")

    all_chunks = chunker.chunk_notes(all_items_to_sync)

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
    for item in all_items_to_sync:
        item_chunks = [c for c in all_chunks if c.note_id == item.id]
        item_mod = item.modification_date.isoformat() if item.modification_date else None
        db.record_synced_note(item.id, item.title, len(item_chunks), item_mod)

    if not silent:
        console.print()
        console.print(Panel(
            f"[green]Synced {len(all_items_to_sync)} items ({len(all_chunks)} chunks)[/green]\n\n"
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
    import subprocess
    from datetime import datetime as dt
    from prompt_toolkit import prompt as pt_prompt
    from prompt_toolkit.styles import Style as PTStyle
    from prompt_toolkit.formatted_text import HTML
    from prompt_toolkit.history import InMemoryHistory
    from prompt_toolkit.completion import Completer, Completion
    from prompt_toolkit.key_binding import KeyBindings

    # Command completer for slash commands
    class SlashCommandCompleter(Completer):
        commands = [
            ("/search <query>", "Search your notes"),
            ("/last", "Last conversation"),
            ("/notes", "List notes"),
            ("/stats", "Stats"),
            ("/clear", "Clear screen"),
            ("/topic <name>", "Rename conversation"),
            ("/context", "Show last context"),
            ("/redo", "Regenerate response"),
            ("/copy", "Copy last response"),
            ("/help", "Commands"),
        ]

        def get_completions(self, document, complete_event):
            text = document.text_before_cursor
            if text.startswith("/"):
                for cmd, desc in self.commands:
                    cmd_name = cmd.split()[0]
                    if cmd_name.startswith(text):
                        yield Completion(
                            cmd_name,
                            start_position=-len(text),
                            display=cmd,
                            display_meta=desc,
                            style="fg:ansicyan",
                            selected_style="fg:ansiwhite bg:ansicyan",
                        )

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
    conversation_topic = "Chat session"
    if continue_last:
        last_conv = db.get_last_conversation()
        if last_conv:
            conversation_id = last_conv["id"]
            conversation_topic = last_conv.get('topic', 'Chat session')
            console.print(f"[dim]Continuing: {conversation_topic}[/dim]")
        else:
            conversation_id = db.create_conversation(topic=conversation_topic)
    else:
        conversation_id = db.create_conversation(topic=conversation_topic)

    console.print()
    console.print("[bold blue]Dumbledore[/bold blue] [dim]· Your personal AI advisor[/dim]")
    console.print(f"[dim]{stats['note_count']} notes · {stats['chunk_count']} chunks · /help for commands[/dim]")
    console.print()

    # Load previous messages if continuing
    previous_messages = []
    if continue_last:
        previous_messages = db.get_conversation_messages(conversation_id, limit=20)
        if previous_messages:
            console.print("[dim]Previous messages loaded.[/dim]\n")

    # State for redo/context/copy
    last_user_input = None
    last_context = None
    last_response = None
    last_response_time = None

    # Prompt styling
    pt_style = PTStyle.from_dict({
        'prompt': 'fg:ansibrightblack',
        'bottom-toolbar': 'bg:#1a1a1a fg:#666666',
        'completion-menu': 'bg:#1a1a1a',
        'completion-menu.completion': 'bg:#1a1a1a fg:#888888',
        'completion-menu.completion.current': 'bg:#3a3a3a fg:ansiwhite',
        'completion-menu.meta.completion': 'bg:#1a1a1a fg:#555555',
        'completion-menu.meta.completion.current': 'bg:#3a3a3a fg:#888888',
    })
    completer = SlashCommandCompleter()
    history = InMemoryHistory()

    # Key bindings for multiline
    bindings = KeyBindings()

    @bindings.add('escape', 'enter')
    def _(event):
        """Alt+Enter for newline."""
        event.current_buffer.insert_text('\n')

    def get_toolbar():
        time_str = f" · {last_response_time}" if last_response_time else ""
        return HTML(f'<b>{conversation_topic}</b>{time_str}')

    while True:
        try:
            user_input = pt_prompt(
                HTML('<prompt>></prompt> '),
                completer=completer,
                style=pt_style,
                complete_while_typing=True,
                history=history,
                bottom_toolbar=get_toolbar,
                key_bindings=bindings,
                multiline=False,
            )
        except KeyboardInterrupt:
            console.print()
            continue  # Ctrl+C just clears current input
        except EOFError:
            user_input = None

        if user_input is None:
            chunks_saved = memory.embed_conversation(conversation_id)
            console.print()
            if chunks_saved:
                console.print("[dim]Conversation saved.[/dim]")
            break

        user_input = user_input.strip()

        if not user_input:
            continue

        # Check for multiline trigger
        if user_input == '"""':
            console.print("[dim]Multiline mode (Ctrl+D to finish):[/dim]")
            lines = []
            try:
                while True:
                    line = pt_prompt("  ", style=pt_style)
                    if line.strip() == '"""':
                        break
                    lines.append(line)
            except EOFError:
                pass
            user_input = "\n".join(lines)
            if not user_input.strip():
                continue

        if user_input.lower() in ("exit", "quit", "q", "bye"):
            chunks_saved = memory.embed_conversation(conversation_id)
            console.print()
            if chunks_saved:
                console.print("[dim]Conversation saved.[/dim]")
            break

        # Handle /clear command
        if user_input == "/clear":
            console.clear()
            console.print("[bold blue]Dumbledore[/bold blue] [dim]· Your personal AI advisor[/dim]")
            console.print(f"[dim]{stats['note_count']} notes · {stats['chunk_count']} chunks · /help for commands[/dim]")
            console.print()
            continue

        # Handle /search command
        if user_input.startswith("/search "):
            query = user_input[8:].strip()
            if query:
                results = retriever.retrieve(query, top_k=5)
                console.print()
                console.print(Markdown(retriever.format_search_results(results)))
                console.print()
            continue

        # Handle /notes command
        if user_input == "/notes":
            show_notes_list()
            continue

        # Handle /stats command
        if user_input == "/stats":
            show_stats()
            continue

        # Handle /help command
        if user_input == "/help":
            console.print()
            console.print("[dim]/search <query>[/dim]  Search notes")
            console.print("[dim]/last[/dim]           Last conversation")
            console.print("[dim]/clear[/dim]          Clear screen")
            console.print("[dim]/topic <name>[/dim]   Rename conversation")
            console.print("[dim]/context[/dim]        Show last context used")
            console.print("[dim]/redo[/dim]           Regenerate last response")
            console.print("[dim]/copy[/dim]           Copy last response")
            console.print("[dim]/notes[/dim]          List notes")
            console.print("[dim]/stats[/dim]          Stats")
            console.print("[dim]exit[/dim]            Quit")
            console.print()
            console.print("[dim]Alt+Enter for newline · \"\"\" for multiline mode[/dim]")
            console.print()
            continue

        # Handle /last command
        if user_input == "/last":
            last_conv = retriever.get_last_conversation_context(exclude_id=conversation_id)
            console.print()
            if last_conv:
                console.print(f"[dim]{last_conv}[/dim]")
            else:
                console.print("[dim]No previous conversations.[/dim]")
            console.print()
            continue

        # Handle /topic command
        if user_input.startswith("/topic "):
            new_topic = user_input[7:].strip()
            if new_topic:
                conversation_topic = new_topic
                db.update_conversation_topic(conversation_id, new_topic)
                console.print(f"[dim]Topic set to: {new_topic}[/dim]")
            continue

        # Handle /context command
        if user_input == "/context":
            console.print()
            if last_context:
                console.print("[dim]Last context used:[/dim]")
                console.print(f"[dim]{last_context[:2000]}{'...' if len(last_context) > 2000 else ''}[/dim]")
            else:
                console.print("[dim]No context yet.[/dim]")
            console.print()
            continue

        # Handle /redo command
        if user_input == "/redo":
            if last_user_input and last_context is not None:
                console.print("[dim]Regenerating...[/dim]")
                response = ai.run_claude_stream(last_user_input, last_context)
                if response:
                    last_response = response
                    last_response_time = dt.now().strftime("%H:%M")
                    db.add_message(conversation_id, "assistant", response)
                    previous_messages.append({"role": "assistant", "content": response})
            else:
                console.print("[dim]Nothing to redo.[/dim]")
            continue

        # Handle /copy command
        if user_input == "/copy":
            if last_response:
                try:
                    subprocess.run(["pbcopy"], input=last_response.encode(), check=True)
                    console.print("[dim]Copied to clipboard.[/dim]")
                except Exception:
                    console.print("[dim]Copy failed. Response:[/dim]")
                    console.print(last_response)
            else:
                console.print("[dim]Nothing to copy.[/dim]")
            continue

        # Save user message
        db.add_message(conversation_id, "user", user_input)
        last_user_input = user_input

        # Build context from RAG
        context = retriever.build_context(user_input, current_conversation_id=conversation_id)

        # Add conversation history to context
        if previous_messages:
            history_text = "\n\n## Recent Conversation\n"
            for msg in previous_messages[-10:]:
                role = "User" if msg["role"] == "user" else "Dumbledore"
                content = msg["content"][:500] + "..." if len(msg["content"]) > 500 else msg["content"]
                history_text += f"**{role}:** {content}\n\n"
            context = f"{context}\n{history_text}" if context else history_text

        last_context = context

        # Get response with streaming
        response = ai.run_claude_stream(user_input, context)

        if response:
            last_response = response
            last_response_time = dt.now().strftime("%H:%M")
            db.add_message(conversation_id, "assistant", response)
            previous_messages.append({"role": "user", "content": user_input})
            previous_messages.append({"role": "assistant", "content": response})
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


@app.command("style")
def style_cmd(
    show: bool = typer.Option(False, "--show", "-s", help="Show current style profile"),
    clear: bool = typer.Option(False, "--clear", "-c", help="Clear the style profile"),
):
    """Analyze your notes to generate a writing style profile."""

    if clear:
        if style.clear_style_profile():
            console.print("[green]Style profile cleared.[/green]")
        else:
            console.print("[dim]No style profile to clear.[/dim]")
        return

    if show:
        profile = style.get_style_profile()
        if profile:
            console.print(Panel(
                Markdown(profile),
                title="[bold cyan]Your Writing Style[/bold cyan]",
                border_style="cyan",
            ))
        else:
            console.print("[dim]No style profile generated yet. Run 'dumbledore style' to create one.[/dim]")
        return

    # Generate new style profile
    stats = db.get_sync_stats()
    if stats["note_count"] == 0:
        console.print("[yellow]No notes synced. Run 'dumbledore sync' first.[/yellow]")
        return

    console.print("[dim]Analyzing your writing style from synced notes...[/dim]")

    # Get samples
    samples = style.get_note_samples()
    if not samples:
        console.print("[yellow]No note samples found to analyze.[/yellow]")
        return

    console.print(f"[dim]Analyzing {len(samples)} note samples...[/dim]")

    # Analyze with Claude
    with ai.display_thinking():
        style_text = style.analyze_style(samples)

    if not style_text:
        console.print("[red]Failed to analyze writing style.[/red]")
        return

    # Save to vector store
    style.save_style_profile(style_text)

    console.print()
    console.print(Panel(
        Markdown(style_text),
        title="[bold green]Writing Style Profile Generated[/bold green]",
        border_style="green",
    ))
    console.print("\n[dim]This style will be used in future conversations.[/dim]")


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
