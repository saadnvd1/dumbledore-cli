"""SQLite database for conversations and note sync metadata."""

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from .config import DB_PATH


def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Get a database connection."""
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Optional[Path] = None) -> None:
    """Initialize the database schema."""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    # Synced notes metadata (track what's been synced)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS synced_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            note_id TEXT UNIQUE NOT NULL,
            note_title TEXT NOT NULL,
            chunk_count INTEGER DEFAULT 0,
            note_modified_at TIMESTAMP,
            synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Conversations
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT,
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_message_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Messages
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id)
        )
    """)

    # Settings (key-value store for config)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Create indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_synced_notes_title ON synced_notes(note_title)")

    conn.commit()
    conn.close()


# ============ Synced Notes ============

def record_synced_note(note_id: str, note_title: str, chunk_count: int, note_modified_at: Optional[str] = None) -> None:
    """Record that a note has been synced."""
    init_db()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO synced_notes (note_id, note_title, chunk_count, note_modified_at, synced_at)
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(note_id) DO UPDATE SET
            note_title = ?,
            chunk_count = ?,
            note_modified_at = ?,
            synced_at = CURRENT_TIMESTAMP
    """, (note_id, note_title, chunk_count, note_modified_at, note_title, chunk_count, note_modified_at))
    conn.commit()
    conn.close()


def get_synced_note_modified_at(note_id: str) -> Optional[str]:
    """Get the stored modification date for a synced note."""
    init_db()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT note_modified_at FROM synced_notes WHERE note_id = ?", (note_id,))
    row = cursor.fetchone()
    conn.close()
    return row["note_modified_at"] if row else None


def get_all_synced_note_ids() -> set[str]:
    """Get all synced note IDs."""
    init_db()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT note_id FROM synced_notes")
    rows = cursor.fetchall()
    conn.close()
    return {row["note_id"] for row in rows}


def get_synced_notes() -> list[dict]:
    """Get all synced notes."""
    init_db()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM synced_notes ORDER BY synced_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_sync_stats() -> dict:
    """Get sync statistics."""
    init_db()
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) as note_count, SUM(chunk_count) as chunk_count FROM synced_notes")
    row = cursor.fetchone()

    cursor.execute("SELECT MAX(synced_at) as last_sync FROM synced_notes")
    last_sync = cursor.fetchone()

    conn.close()

    return {
        "note_count": row["note_count"] or 0,
        "chunk_count": row["chunk_count"] or 0,
        "last_sync": last_sync["last_sync"] if last_sync else None,
    }


def clear_sync_records() -> int:
    """Clear all sync records."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM synced_notes")
    count = cursor.fetchone()[0]
    cursor.execute("DELETE FROM synced_notes")
    conn.commit()
    conn.close()
    return count


# ============ Conversations ============

def create_conversation(topic: str = "") -> int:
    """Create a new conversation."""
    init_db()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO conversations (topic)
        VALUES (?)
    """, (topic,))
    conn.commit()
    conv_id = cursor.lastrowid
    conn.close()
    return conv_id


def add_message(conversation_id: int, role: str, content: str) -> int:
    """Add a message to a conversation."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO messages (conversation_id, role, content)
        VALUES (?, ?, ?)
    """, (conversation_id, role, content))

    # Update last message timestamp
    cursor.execute("""
        UPDATE conversations SET last_message_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (conversation_id,))

    conn.commit()
    msg_id = cursor.lastrowid
    conn.close()
    return msg_id


def get_conversation_messages(conversation_id: int, limit: Optional[int] = None) -> list[dict]:
    """Get messages for a conversation."""
    conn = get_connection()
    cursor = conn.cursor()

    query = """
        SELECT * FROM messages
        WHERE conversation_id = ?
        ORDER BY created_at ASC
    """
    if limit:
        query += f" LIMIT {limit}"

    cursor.execute(query, (conversation_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_recent_conversations(limit: int = 10) -> list[dict]:
    """Get recent conversations with message counts."""
    init_db()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.*, COUNT(m.id) as message_count
        FROM conversations c
        LEFT JOIN messages m ON m.conversation_id = c.id
        GROUP BY c.id
        ORDER BY c.last_message_at DESC
        LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_last_conversation() -> Optional[dict]:
    """Get the most recent conversation."""
    conversations = get_recent_conversations(limit=1)
    return conversations[0] if conversations else None


# ============ Settings ============

def set_setting(key: str, value: str) -> None:
    """Set a setting value."""
    init_db()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO settings (key, value, updated_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(key) DO UPDATE SET value = ?, updated_at = CURRENT_TIMESTAMP
    """, (key, value, value))
    conn.commit()
    conn.close()


def get_setting(key: str, default: Optional[str] = None) -> Optional[str]:
    """Get a setting value."""
    init_db()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row["value"] if row else default


def get_all_settings() -> dict:
    """Get all settings."""
    init_db()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM settings")
    rows = cursor.fetchall()
    conn.close()
    return {row["key"]: row["value"] for row in rows}
