"""Apple Notes integration via AppleScript."""

import subprocess
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from rich.console import Console

console = Console()


@dataclass
class Note:
    """Represents an Apple Note."""
    id: str
    title: str
    body: str
    folder: str
    creation_date: Optional[datetime] = None
    modification_date: Optional[datetime] = None


def run_applescript(script: str, timeout: int = 600) -> Optional[str]:
    """Run AppleScript and return output."""
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        else:
            console.print(f"[red]AppleScript error: {result.stderr}[/red]")
            return None
    except subprocess.TimeoutExpired:
        console.print("[red]AppleScript timed out[/red]")
        return None
    except Exception as e:
        console.print(f"[red]Error running AppleScript: {e}[/red]")
        return None


def get_note_count() -> int:
    """Get total number of notes."""
    script = 'tell application "Notes" to return count of notes'
    result = run_applescript(script)
    return int(result) if result else 0


def get_all_note_titles() -> list[str]:
    """Get all note titles."""
    script = 'tell application "Notes" to return name of every note'
    result = run_applescript(script)
    if not result:
        return []
    return [t.strip() for t in result.split(", ")]


def get_note_by_title(title: str) -> Optional[Note]:
    """Get a specific note by title."""
    # Escape quotes in title
    escaped_title = title.replace('"', '\\"')

    script = f'''
    tell application "Notes"
        set theNote to first note whose name is "{escaped_title}"
        set noteId to id of theNote
        set noteTitle to name of theNote
        set noteBody to plaintext of theNote
        set noteFolder to name of container of theNote
        return noteId & "|||" & noteTitle & "|||" & noteBody & "|||" & noteFolder
    end tell
    '''

    result = run_applescript(script)
    if not result:
        return None

    parts = result.split("|||")
    if len(parts) >= 4:
        return Note(
            id=parts[0],
            title=parts[1],
            body=parts[2],
            folder=parts[3],
        )
    return None


def get_notes_batch(start: int, batch_size: int) -> list[Note]:
    """Get a batch of notes starting from index."""
    script = f'''
    tell application "Notes"
        set output to ""
        set noteList to notes
        set startIdx to {start + 1}
        set endIdx to {start + batch_size}
        set noteCount to count of noteList

        if endIdx > noteCount then set endIdx to noteCount
        if startIdx > noteCount then return ""

        repeat with i from startIdx to endIdx
            try
                set theNote to item i of noteList
                set noteId to id of theNote
                set noteTitle to name of theNote
                set noteBody to plaintext of theNote

                try
                    set noteFolder to name of container of theNote
                on error
                    set noteFolder to "Notes"
                end try

                set modDate to modification date of theNote
                set modDateStr to (year of modDate as string) & "-" & text -2 thru -1 of ("0" & ((month of modDate) as integer)) & "-" & text -2 thru -1 of ("0" & (day of modDate)) & "T" & text -2 thru -1 of ("0" & (hours of modDate)) & ":" & text -2 thru -1 of ("0" & (minutes of modDate)) & ":" & text -2 thru -1 of ("0" & (seconds of modDate))

                set output to output & noteId & "<<<SEP>>>" & noteTitle & "<<<SEP>>>" & noteBody & "<<<SEP>>>" & noteFolder & "<<<SEP>>>" & modDateStr & "<<<NOTE>>>"
            on error
                -- Skip notes that cause errors
            end try
        end repeat

        return output
    end tell
    '''

    result = run_applescript(script, timeout=120)
    if not result:
        return []

    notes_list = []
    note_strings = result.split("<<<NOTE>>>")

    for note_str in note_strings:
        if not note_str.strip():
            continue

        parts = note_str.split("<<<SEP>>>")
        if len(parts) >= 5:
            mod_date = None
            try:
                mod_date = datetime.fromisoformat(parts[4])
            except (ValueError, IndexError):
                pass

            notes_list.append(Note(
                id=parts[0],
                title=parts[1],
                body=parts[2],
                folder=parts[3],
                modification_date=mod_date,
            ))
        elif len(parts) >= 4:
            notes_list.append(Note(
                id=parts[0],
                title=parts[1],
                body=parts[2],
                folder=parts[3],
            ))

    return notes_list


def get_all_notes(limit: Optional[int] = None, show_progress: bool = True, batch_size: int = 50) -> list[Note]:
    """Get all notes with their content in batches.

    Args:
        limit: Max number of notes to fetch
        show_progress: Show progress messages
        batch_size: Number of notes per batch (default 50)
    """
    total = get_note_count()
    if limit:
        total = min(total, limit)

    if show_progress:
        console.print(f"[dim]Fetching {total} notes from Apple Notes (in batches of {batch_size})...[/dim]")

    all_notes = []
    fetched = 0

    while fetched < total:
        remaining = total - fetched
        current_batch = min(batch_size, remaining)

        if show_progress:
            console.print(f"[dim]  Batch {fetched + 1}-{fetched + current_batch} of {total}...[/dim]")

        batch_notes = get_notes_batch(fetched, current_batch)

        if not batch_notes:
            # No more notes or error
            break

        all_notes.extend(batch_notes)
        fetched += len(batch_notes)

        # If we got fewer than requested, we're done
        if len(batch_notes) < current_batch:
            break

    if show_progress:
        console.print(f"[green]Fetched {len(all_notes)} notes[/green]")

    return all_notes


def get_notes_by_folder(folder_name: str) -> list[Note]:
    """Get all notes from a specific folder."""
    escaped_folder = folder_name.replace('"', '\\"')

    script = f'''
    tell application "Notes"
        set output to ""
        set theFolder to folder "{escaped_folder}"
        set noteList to notes of theFolder

        repeat with theNote in noteList
            set noteId to id of theNote
            set noteTitle to name of theNote
            set noteBody to plaintext of theNote

            set output to output & noteId & "<<<SEP>>>" & noteTitle & "<<<SEP>>>" & noteBody & "<<<SEP>>>" & "{folder_name}" & "<<<NOTE>>>"
        end repeat

        return output
    end tell
    '''

    result = run_applescript(script)
    if not result:
        return []

    notes = []
    note_strings = result.split("<<<NOTE>>>")

    for note_str in note_strings:
        if not note_str.strip():
            continue

        parts = note_str.split("<<<SEP>>>")
        if len(parts) >= 4:
            notes.append(Note(
                id=parts[0],
                title=parts[1],
                body=parts[2],
                folder=parts[3],
            ))

    return notes


def get_folder_names() -> list[str]:
    """Get all folder names."""
    script = 'tell application "Notes" to return name of every folder'
    result = run_applescript(script)
    if not result:
        return []
    return [f.strip() for f in result.split(", ")]


def search_notes(query: str) -> list[str]:
    """Search notes by title (basic search via AppleScript).

    Note: For semantic search, use the RAG retriever instead.
    """
    escaped_query = query.replace('"', '\\"').lower()

    script = f'''
    tell application "Notes"
        set matchingTitles to {{}}
        repeat with theNote in notes
            if (name of theNote as text) contains "{escaped_query}" then
                set end of matchingTitles to name of theNote
            end if
        end repeat
        return matchingTitles
    end tell
    '''

    result = run_applescript(script)
    if not result:
        return []

    # Handle AppleScript list output
    if result.startswith("{") and result.endswith("}"):
        result = result[1:-1]

    return [t.strip() for t in result.split(", ") if t.strip()]
