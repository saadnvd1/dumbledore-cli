"""Local markdown file integration."""

import hashlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.console import Console

console = Console()


@dataclass
class MarkdownNote:
    """Represents a local markdown file."""
    id: str  # hash of filepath
    title: str
    body: str
    folder: str
    filepath: str
    modification_date: Optional[datetime] = None


def get_file_id(filepath: str) -> str:
    """Generate a unique ID for a file based on its path."""
    return f"md_{hashlib.md5(filepath.encode()).hexdigest()[:12]}"


def get_markdown_files(
    directory: Path,
    show_progress: bool = True,
) -> list[MarkdownNote]:
    """Get all markdown files from a directory recursively.

    Args:
        directory: Root directory to scan
        show_progress: Whether to show progress messages

    Returns:
        List of MarkdownNote objects
    """
    directory = Path(directory).expanduser()

    if not directory.exists():
        if show_progress:
            console.print(f"[yellow]Directory not found: {directory}[/yellow]")
        return []

    md_files = list(directory.rglob("*.md"))

    if show_progress:
        console.print(f"[dim]Found {len(md_files)} markdown files in {directory}[/dim]")

    notes = []
    for filepath in md_files:
        try:
            # Read file content
            body = filepath.read_text(encoding='utf-8')

            # Get title from filename (remove hash suffix if present)
            filename = filepath.stem
            # Remove common hash suffixes like "-2499e585"
            if len(filename) > 9 and filename[-9] == '-' and filename[-8:].isalnum():
                title = filename[:-9].replace('-', ' ').title()
            else:
                title = filename.replace('-', ' ').title()

            # Get folder (parent directory name relative to root)
            try:
                folder = filepath.parent.relative_to(directory).parts[0] if filepath.parent != directory else "root"
            except ValueError:
                folder = filepath.parent.name

            # Get modification time
            mod_time = datetime.fromtimestamp(filepath.stat().st_mtime)

            notes.append(MarkdownNote(
                id=get_file_id(str(filepath)),
                title=title,
                body=body,
                folder=folder,
                filepath=str(filepath),
                modification_date=mod_time,
            ))
        except Exception as e:
            if show_progress:
                console.print(f"[dim]Skipping {filepath}: {e}[/dim]")
            continue

    if show_progress:
        console.print(f"[green]Loaded {len(notes)} markdown files[/green]")

    return notes
