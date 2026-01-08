"""Project documentation sync from ~/dev directories."""

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.console import Console

from .markdown import MarkdownNote

console = Console()

# Files to look for in each project
PROJECT_DOC_FILES = ["README.md", "CLAUDE.md"]


def get_file_id(filepath: str) -> str:
    """Generate a unique ID for a project doc based on its path."""
    return f"proj_{hashlib.md5(filepath.encode()).hexdigest()[:12]}"


def get_project_docs(
    dev_dir: Path,
    show_progress: bool = True,
) -> list[MarkdownNote]:
    """Get README.md and CLAUDE.md from all projects in ~/dev.

    Args:
        dev_dir: The dev directory to scan (e.g., ~/dev)
        show_progress: Whether to show progress messages

    Returns:
        List of MarkdownNote objects for project docs
    """
    dev_dir = Path(dev_dir).expanduser()

    if not dev_dir.exists():
        if show_progress:
            console.print(f"[yellow]Dev directory not found: {dev_dir}[/yellow]")
        return []

    notes = []
    projects_found = 0

    # Iterate through subdirectories (each is a project)
    for project_dir in sorted(dev_dir.iterdir()):
        if not project_dir.is_dir():
            continue
        if project_dir.name.startswith('.'):
            continue

        project_name = project_dir.name

        for doc_filename in PROJECT_DOC_FILES:
            doc_path = project_dir / doc_filename
            if not doc_path.exists():
                continue

            try:
                body = doc_path.read_text(encoding='utf-8')
                mod_time = datetime.fromtimestamp(doc_path.stat().st_mtime)

                # Title: "project-name/README" or "project-name/CLAUDE"
                title = f"{project_name}/{doc_filename.replace('.md', '')}"

                notes.append(MarkdownNote(
                    id=get_file_id(str(doc_path)),
                    title=title,
                    body=body,
                    folder=project_name,
                    filepath=str(doc_path),
                    modification_date=mod_time,
                ))
                projects_found += 1
            except Exception as e:
                if show_progress:
                    console.print(f"[dim]Skipping {doc_path}: {e}[/dim]")
                continue

    if show_progress:
        console.print(f"[dim]Found {len(notes)} project docs from {projects_found} projects[/dim]")

    return notes
