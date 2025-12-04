# -*- coding: utf-8 -*-
"""
history.py - Clipboard history management using SQLite
Provides lightweight, persistent storage for clipboard history
"""

import sqlite3
import threading
from pathlib import Path
from typing import List, Optional
from datetime import datetime
from contextlib import contextmanager

from .config import DATA_DIR
from .clipboard_monitor import ClipboardItem

DB_FILE = DATA_DIR / "clipboard_history.db"


class HistoryManager:
    """
    Manages clipboard history using SQLite database.
    Thread-safe with connection pooling.
    """
    
    def __init__(self, max_items: int = 100):
        self.max_items = max_items
        self._lock = threading.Lock()
        self._init_db()
    
    def _init_db(self):
        """Initialize database schema"""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS clipboard_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT NOT NULL,
                    content_hash TEXT NOT NULL UNIQUE,
                    timestamp TEXT NOT NULL,
                    source TEXT DEFAULT 'local'
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_timestamp 
                ON clipboard_history(timestamp DESC)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_hash 
                ON clipboard_history(content_hash)
            """)
            conn.commit()
    
    @contextmanager
    def _get_connection(self):
        """Get database connection with context manager"""
        conn = sqlite3.connect(str(DB_FILE), timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    def add(self, item: ClipboardItem) -> bool:
        """
        Add item to history. Returns True if added, False if duplicate.
        Automatically trims old entries to maintain max_items limit.
        """
        with self._lock:
            try:
                with self._get_connection() as conn:
                    # Try to insert, ignore if hash exists
                    cursor = conn.execute("""
                        INSERT OR REPLACE INTO clipboard_history 
                        (content, content_hash, timestamp, source)
                        VALUES (?, ?, ?, ?)
                    """, (item.content, item.content_hash, 
                          item.timestamp.isoformat(), item.source))
                    
                    # Trim old entries
                    conn.execute("""
                        DELETE FROM clipboard_history 
                        WHERE id NOT IN (
                            SELECT id FROM clipboard_history 
                            ORDER BY timestamp DESC 
                            LIMIT ?
                        )
                    """, (self.max_items,))
                    
                    conn.commit()
                    return cursor.rowcount > 0
            except Exception:
                return False
    
    def get_all(self, limit: int = 50) -> List[ClipboardItem]:
        """Get recent history items"""
        with self._get_connection() as conn:
            rows = conn.execute("""
                SELECT content, content_hash, timestamp, source 
                FROM clipboard_history 
                ORDER BY timestamp DESC 
                LIMIT ?
            """, (limit,)).fetchall()
            
            return [ClipboardItem(
                content=row['content'],
                content_hash=row['content_hash'],
                timestamp=datetime.fromisoformat(row['timestamp']),
                source=row['source']
            ) for row in rows]
    
    def search(self, query: str, limit: int = 20) -> List[ClipboardItem]:
        """Search history by content"""
        with self._get_connection() as conn:
            rows = conn.execute("""
                SELECT content, content_hash, timestamp, source 
                FROM clipboard_history 
                WHERE content LIKE ? 
                ORDER BY timestamp DESC 
                LIMIT ?
            """, (f'%{query}%', limit)).fetchall()
            
            return [ClipboardItem(
                content=row['content'],
                content_hash=row['content_hash'],
                timestamp=datetime.fromisoformat(row['timestamp']),
                source=row['source']
            ) for row in rows]
    
    def clear(self):
        """Clear all history"""
        with self._lock:
            with self._get_connection() as conn:
                conn.execute("DELETE FROM clipboard_history")
                conn.commit()
    
    def delete(self, content_hash: str):
        """Delete specific item by hash"""
        with self._lock:
            with self._get_connection() as conn:
                conn.execute(
                    "DELETE FROM clipboard_history WHERE content_hash = ?",
                    (content_hash,)
                )
                conn.commit()

