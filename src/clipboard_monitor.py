# -*- coding: utf-8 -*-
"""
clipboard_monitor.py - Clipboard monitoring module
Monitors Windows clipboard for changes including text, images, and files
Triggers callbacks when clipboard content changes
"""

import threading
import time
import hashlib
import io
from typing import Callable, Optional, List
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

import pyperclip
from PIL import Image

# Windows clipboard support
try:
    import win32clipboard
    import win32con
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False


class ContentType(Enum):
    """Clipboard content type enumeration"""
    TEXT = "text"
    IMAGE = "image"
    FILES = "files"


@dataclass
class FileData:
    """Represents a file with its name and content for transfer"""
    filename: str
    content: bytes
    original_path: str = ""  # Original path on source machine


@dataclass
class ClipboardItem:
    """
    Represents a clipboard item with support for multiple content types.

    Attributes:
        content_type: Type of content (text, image, files)
        content: Text content (for TEXT type)
        image_data: Binary image data in PNG format (for IMAGE type)
        file_paths: List of file paths (for FILES type, local only)
        file_contents: List of FileData for actual file transfer
        content_hash: MD5 hash for deduplication
        timestamp: When the item was captured
        source: Origin of the item (local or remote)
    """
    content_type: ContentType
    content_hash: str
    timestamp: datetime
    source: str = "local"
    content: str = ""
    image_data: bytes = field(default_factory=bytes)
    file_paths: List[str] = field(default_factory=list)
    file_contents: List[FileData] = field(default_factory=list)  # For file transfer

    @classmethod
    def from_text(cls, text: str, source: str = "local") -> 'ClipboardItem':
        """Create ClipboardItem from text content"""
        content_hash = hashlib.md5(text.encode('utf-8')).hexdigest()
        return cls(
            content_type=ContentType.TEXT,
            content=text,
            content_hash=content_hash,
            timestamp=datetime.now(),
            source=source
        )

    @classmethod
    def from_image(cls, image_data: bytes, source: str = "local") -> 'ClipboardItem':
        """Create ClipboardItem from image binary data (PNG format)"""
        content_hash = hashlib.md5(image_data).hexdigest()
        return cls(
            content_type=ContentType.IMAGE,
            image_data=image_data,
            content_hash=content_hash,
            timestamp=datetime.now(),
            source=source
        )

    @classmethod
    def from_files(cls, file_paths: List[str], source: str = "local",
                   read_content: bool = False, max_file_size: int = 50 * 1024 * 1024,
                   max_total_size: int = 100 * 1024 * 1024) -> 'ClipboardItem':
        """
        Create ClipboardItem from file paths.

        Args:
            file_paths: List of file paths
            source: Origin of the item
            read_content: Whether to read file contents for transfer
            max_file_size: Maximum size per file (default 50MB)
            max_total_size: Maximum total size (default 100MB)
        """
        import os

        file_contents = []
        total_size = 0
        skipped_files = []

        if read_content and source == "local":
            for path in file_paths:
                try:
                    if not os.path.isfile(path):
                        skipped_files.append((path, "not a file"))
                        continue

                    file_size = os.path.getsize(path)
                    if file_size > max_file_size:
                        skipped_files.append((path, f"too large: {file_size / 1024 / 1024:.1f}MB"))
                        continue

                    if total_size + file_size > max_total_size:
                        skipped_files.append((path, "total size exceeded"))
                        continue

                    with open(path, 'rb') as f:
                        content = f.read()

                    filename = os.path.basename(path)
                    file_contents.append(FileData(
                        filename=filename,
                        content=content,
                        original_path=path
                    ))
                    total_size += file_size

                except Exception as e:
                    skipped_files.append((path, str(e)))

        # Generate hash from file contents if available, else from paths
        if file_contents:
            hash_data = b''.join(f.content for f in file_contents)
            content_hash = hashlib.md5(hash_data).hexdigest()
        else:
            paths_str = '\n'.join(sorted(file_paths))
            content_hash = hashlib.md5(paths_str.encode('utf-8')).hexdigest()

        return cls(
            content_type=ContentType.FILES,
            file_paths=file_paths,
            file_contents=file_contents,
            content_hash=content_hash,
            timestamp=datetime.now(),
            source=source
        )

    @classmethod
    def from_file_contents(cls, file_contents: List[FileData], source: str = "remote") -> 'ClipboardItem':
        """Create ClipboardItem from received file contents (for remote files)"""
        if file_contents:
            hash_data = b''.join(f.content for f in file_contents)
            content_hash = hashlib.md5(hash_data).hexdigest()
        else:
            content_hash = hashlib.md5(b'').hexdigest()

        return cls(
            content_type=ContentType.FILES,
            file_paths=[],  # No local paths for remote files
            file_contents=file_contents,
            content_hash=content_hash,
            timestamp=datetime.now(),
            source=source
        )

    @classmethod
    def from_content(cls, content: str, source: str = "local") -> 'ClipboardItem':
        """Legacy method for backward compatibility - creates TEXT item"""
        return cls.from_text(content, source)

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization"""
        data = {
            'content_type': self.content_type.value,
            'content_hash': self.content_hash,
            'timestamp': self.timestamp.isoformat(),
            'source': self.source
        }

        if self.content_type == ContentType.TEXT:
            data['content'] = self.content
        elif self.content_type == ContentType.IMAGE:
            # Image data will be handled separately with compression
            data['has_image'] = True
        elif self.content_type == ContentType.FILES:
            data['file_paths'] = self.file_paths

        return data

    @classmethod
    def from_dict(cls, data: dict) -> 'ClipboardItem':
        """Create from dictionary"""
        content_type = ContentType(data.get('content_type', 'text'))

        return cls(
            content_type=content_type,
            content=data.get('content', ''),
            image_data=b'',  # Image data handled separately
            file_paths=data.get('file_paths', []),
            content_hash=data['content_hash'],
            timestamp=datetime.fromisoformat(data['timestamp']),
            source=data.get('source', 'remote')
        )

    def get_display_text(self) -> str:
        """Get display text for UI"""
        if self.content_type == ContentType.TEXT:
            return self.content[:100] + ('...' if len(self.content) > 100 else '')
        elif self.content_type == ContentType.IMAGE:
            return f"[Image: {len(self.image_data)} bytes]"
        elif self.content_type == ContentType.FILES:
            return f"[Files: {', '.join(self.file_paths[:3])}{'...' if len(self.file_paths) > 3 else ''}]"
        return "[Unknown]"


class ClipboardMonitor:
    """
    Monitors clipboard for changes in a background thread.
    Supports text, images, and files detection.
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
        """Set text clipboard content (pauses monitoring briefly to avoid loop)"""
        with self._lock:
            self._paused = True
            try:
                pyperclip.copy(content)
                self._last_hash = hashlib.md5(content.encode('utf-8')).hexdigest()
            finally:
                self._paused = False

    def set_image(self, image_data: bytes):
        """Set image to clipboard from PNG binary data"""
        if not HAS_WIN32:
            return

        with self._lock:
            self._paused = True
            try:
                # Convert PNG to BMP for clipboard
                image = Image.open(io.BytesIO(image_data))
                output = io.BytesIO()
                image.convert('RGB').save(output, 'BMP')
                bmp_data = output.getvalue()[14:]  # Skip BMP header

                win32clipboard.OpenClipboard()
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardData(win32con.CF_DIB, bmp_data)
                win32clipboard.CloseClipboard()

                self._last_hash = hashlib.md5(image_data).hexdigest()
            except Exception:
                pass
            finally:
                self._paused = False

    def set_files(self, file_paths: List[str]):
        """Set files to clipboard using proper HDROP format"""
        if not HAS_WIN32 or not file_paths:
            print(f"[ClipboardMonitor] set_files skipped: HAS_WIN32={HAS_WIN32}, paths={file_paths}")
            return

        with self._lock:
            self._paused = True
            try:
                import struct
                import ctypes

                print(f"[ClipboardMonitor] Setting files to clipboard: {file_paths}")

                # DROPFILES structure for CF_HDROP
                # struct DROPFILES { DWORD pFiles; POINT pt; BOOL fNC; BOOL fWide; }
                # pFiles = offset to file list (20 bytes for header)
                # pt.x, pt.y = 0, 0
                # fNC = 0 (not used)
                # fWide = 1 (Unicode)

                # Build file list: each path followed by null, double null at end
                files_str = '\0'.join(file_paths) + '\0\0'
                files_bytes = files_str.encode('utf-16-le')

                # DROPFILES header (20 bytes) + file list
                header = struct.pack('IIIII', 20, 0, 0, 0, 1)  # pFiles, pt.x, pt.y, fNC, fWide
                data = header + files_bytes

                # Allocate global memory
                GMEM_MOVEABLE = 0x0002
                GMEM_ZEROINIT = 0x0040
                kernel32 = ctypes.windll.kernel32

                hGlobal = kernel32.GlobalAlloc(GMEM_MOVEABLE | GMEM_ZEROINIT, len(data))
                if hGlobal:
                    pGlobal = kernel32.GlobalLock(hGlobal)
                    if pGlobal:
                        ctypes.memmove(pGlobal, data, len(data))
                        kernel32.GlobalUnlock(hGlobal)

                        win32clipboard.OpenClipboard()
                        win32clipboard.EmptyClipboard()
                        # Use SetClipboardData with the handle
                        result = ctypes.windll.user32.SetClipboardData(win32con.CF_HDROP, hGlobal)
                        win32clipboard.CloseClipboard()
                        print(f"[ClipboardMonitor] SetClipboardData result: {result}")
                    else:
                        kernel32.GlobalFree(hGlobal)
                        print("[ClipboardMonitor] GlobalLock failed")
                else:
                    print("[ClipboardMonitor] GlobalAlloc failed")

                paths_str = '\n'.join(sorted(file_paths))
                self._last_hash = hashlib.md5(paths_str.encode('utf-8')).hexdigest()
            except Exception as e:
                print(f"[ClipboardMonitor] set_files error: {e}")
                try:
                    win32clipboard.CloseClipboard()
                except Exception:
                    pass
            finally:
                self._paused = False

    def set_item(self, item: ClipboardItem):
        """Set clipboard from ClipboardItem (auto-detect type)"""
        if item.content_type == ContentType.TEXT:
            self.set_content(item.content)
        elif item.content_type == ContentType.IMAGE:
            self.set_image(item.image_data)
        elif item.content_type == ContentType.FILES:
            # If we have file contents, save them first
            if item.file_contents:
                saved_paths = self._save_received_files(item.file_contents)
                if saved_paths:
                    self.set_files(saved_paths)
            elif item.file_paths:
                self.set_files(item.file_paths)

    def _save_received_files(self, file_contents: List[FileData]) -> List[str]:
        """Save received file contents to temp directory and return local paths"""
        import os
        import tempfile

        saved_paths = []

        # Create a temp directory for received files
        temp_base = os.path.join(tempfile.gettempdir(), 'CopyPasteEverything')
        os.makedirs(temp_base, exist_ok=True)

        # Create a unique subdirectory for this batch
        batch_dir = os.path.join(temp_base, datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
        os.makedirs(batch_dir, exist_ok=True)

        for file_data in file_contents:
            try:
                # Sanitize filename
                safe_filename = self._sanitize_filename(file_data.filename)
                file_path = os.path.join(batch_dir, safe_filename)

                # Handle duplicate filenames
                counter = 1
                base_name, ext = os.path.splitext(safe_filename)
                while os.path.exists(file_path):
                    file_path = os.path.join(batch_dir, f"{base_name}_{counter}{ext}")
                    counter += 1

                with open(file_path, 'wb') as f:
                    f.write(file_data.content)

                saved_paths.append(file_path)
                print(f"[ClipboardMonitor] Saved file: {file_path}")
            except Exception as e:
                print(f"[ClipboardMonitor] Failed to save {file_data.filename}: {e}")

        return saved_paths

    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename to remove unsafe characters"""
        import re
        # Remove path separators and other unsafe characters
        unsafe_chars = r'[<>:"/\\|?*\x00-\x1f]'
        safe_name = re.sub(unsafe_chars, '_', filename)
        # Ensure not empty
        return safe_name or "unnamed_file"

    def _get_clipboard_image(self) -> Optional[bytes]:
        """Get image from clipboard as PNG bytes"""
        if not HAS_WIN32:
            return None

        try:
            win32clipboard.OpenClipboard()

            if win32clipboard.IsClipboardFormatAvailable(win32con.CF_DIB):
                data = win32clipboard.GetClipboardData(win32con.CF_DIB)
                win32clipboard.CloseClipboard()

                # Convert DIB to PNG
                # DIB format: BITMAPINFOHEADER + pixel data
                # Create BMP file header + DIB data
                bmp_header = b'BM' + len(data).to_bytes(4, 'little') + b'\x00\x00\x00\x00\x36\x00\x00\x00'
                bmp_data = bmp_header + data

                image = Image.open(io.BytesIO(bmp_data))
                output = io.BytesIO()
                image.save(output, 'PNG')
                return output.getvalue()

            win32clipboard.CloseClipboard()
        except Exception:
            try:
                win32clipboard.CloseClipboard()
            except Exception:
                pass

        return None

    def _get_clipboard_files(self) -> Optional[List[str]]:
        """Get file paths from clipboard"""
        if not HAS_WIN32:
            return None

        try:
            win32clipboard.OpenClipboard()

            if win32clipboard.IsClipboardFormatAvailable(win32con.CF_HDROP):
                data = win32clipboard.GetClipboardData(win32con.CF_HDROP)
                win32clipboard.CloseClipboard()

                # data is a tuple of file paths
                if isinstance(data, tuple):
                    file_list = list(data)
                    print(f"[ClipboardMonitor] Got clipboard files: {file_list}")
                    return file_list

            win32clipboard.CloseClipboard()
        except Exception as e:
            print(f"[ClipboardMonitor] Error getting clipboard files: {e}")
            try:
                win32clipboard.CloseClipboard()
            except Exception:
                pass

        return None

    def _monitor_loop(self):
        """Main monitoring loop - checks text, images, and files"""
        while self._running:
            try:
                with self._lock:
                    if self._paused:
                        time.sleep(self.interval)
                        continue

                item = None

                # Priority: Files > Image > Text
                # Check for files first
                file_paths = self._get_clipboard_files()
                if file_paths:
                    paths_str = '\n'.join(sorted(file_paths))
                    content_hash = hashlib.md5(paths_str.encode('utf-8')).hexdigest()
                    if content_hash != self._last_hash:
                        self._last_hash = content_hash
                        # Read file contents for transfer, use config limits
                        from .config import config
                        item = ClipboardItem.from_files(
                            file_paths, "local",
                            read_content=True,
                            max_file_size=config.max_file_size,
                            max_total_size=config.max_total_file_size
                        )

                # Check for image if no files
                if not item:
                    image_data = self._get_clipboard_image()
                    if image_data:
                        content_hash = hashlib.md5(image_data).hexdigest()
                        if content_hash != self._last_hash:
                            self._last_hash = content_hash
                            item = ClipboardItem.from_image(image_data, "local")

                # Fallback to text
                if not item:
                    content = pyperclip.paste()
                    if content:
                        content_hash = hashlib.md5(content.encode('utf-8')).hexdigest()
                        if content_hash != self._last_hash:
                            self._last_hash = content_hash
                            item = ClipboardItem.from_text(content, "local")

                if item:
                    # Log what we're sending
                    if item.content_type == ContentType.FILES:
                        print(f"[ClipboardMonitor] Detected files: {len(item.file_paths)} paths, {len(item.file_contents)} contents")
                        if item.file_contents:
                            for fc in item.file_contents:
                                print(f"[ClipboardMonitor]   - {fc.filename}: {len(fc.content)} bytes")
                    self.on_change(item)

            except Exception as e:
                import traceback
                print(f"[ClipboardMonitor] Error in monitor loop: {e}")
                print(f"[ClipboardMonitor] Traceback: {traceback.format_exc()}")

            time.sleep(self.interval)

