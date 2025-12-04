# -*- coding: utf-8 -*-
"""
clipboard_monitor.py - Clipboard monitoring module
Monitors Windows clipboard for changes and triggers callbacks
"""

import threading
import time
import hashlib
from typing import Callable, Optional
from dataclasses import dataclass
from datetime import datetime
import pyperclip


@dataclass
class ClipboardItem:
    """Represents a clipboard item"""
    content: str
    content_hash: str
    timestamp: datetime
    source: str = "local"  # local or remote
    
    @classmethod
    def from_content(cls, content: str, source: str = "local") -> 'ClipboardItem':
        """Create ClipboardItem from content string"""
        content_hash = hashlib.md5(content.encode('utf-8')).hexdigest()
        return cls(
            content=content,
            content_hash=content_hash,
            timestamp=datetime.now(),
            source=source
        )
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization"""
        return {
            'content': self.content,
            'content_hash': self.content_hash,
            'timestamp': self.timestamp.isoformat(),
            'source': self.source
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'ClipboardItem':
        """Create from dictionary"""
        return cls(
            content=data['content'],
            content_hash=data['content_hash'],
            timestamp=datetime.fromisoformat(data['timestamp']),
            source=data.get('source', 'remote')
        )


class ClipboardMonitor:
    """
    Monitors clipboard for changes in a background thread.
    Triggers callback when clipboard content changes.
    """
    
    def __init__(self, on_change: Callable[[ClipboardItem], None], interval_ms: int = 500):
        self.on_change = on_change
        self.interval = interval_ms / 1000.0
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_hash: str = ""
        self._paused = False
        self._lock = threading.Lock()
    
    def start(self):
        """Start monitoring clipboard"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
    
    def stop(self):
        """Stop monitoring clipboard"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None
    
    def pause(self):
        """Temporarily pause monitoring"""
        with self._lock:
            self._paused = True
    
    def resume(self):
        """Resume monitoring"""
        with self._lock:
            self._paused = False
    
    def set_content(self, content: str):
        """Set clipboard content (pauses monitoring briefly to avoid loop)"""
        with self._lock:
            self._paused = True
            try:
                pyperclip.copy(content)
                self._last_hash = hashlib.md5(content.encode('utf-8')).hexdigest()
            finally:
                self._paused = False
    
    def _monitor_loop(self):
        """Main monitoring loop"""
        while self._running:
            try:
                with self._lock:
                    if self._paused:
                        time.sleep(self.interval)
                        continue
                
                content = pyperclip.paste()
                if content:
                    content_hash = hashlib.md5(content.encode('utf-8')).hexdigest()
                    if content_hash != self._last_hash:
                        self._last_hash = content_hash
                        item = ClipboardItem.from_content(content, "local")
                        self.on_change(item)
            except Exception:
                pass  # Silently handle clipboard access errors
            
            time.sleep(self.interval)

