# -*- coding: utf-8 -*-
"""
chunked_transfer.py - Large file chunked transfer module
Provides chunked transfer for files exceeding threshold (default 10MB)
Supports resumable transfers and transfer queue management
"""

import asyncio
import hashlib
import uuid
import time
import json
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Callable, Any, Set
from enum import Enum
from pathlib import Path
import threading

from .compression import compress_and_encode, decode_and_decompress
from .config import config, DATA_DIR


class TransferState(Enum):
    """Transfer state enumeration"""
    PENDING = "pending"
    TRANSFERRING = "transferring"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ChunkInfo:
    """Information about a single chunk"""
    chunk_index: int
    offset: int
    size: int
    checksum: str
    transferred: bool = False
    received: bool = False  # For sender: whether receiver has acknowledged this chunk


@dataclass
class TransferTask:
    """A file transfer task"""
    transfer_id: str
    filename: str
    file_size: int
    file_hash: str
    total_chunks: int
    chunk_size: int
    chunks: List[ChunkInfo] = field(default_factory=list)
    state: TransferState = TransferState.PENDING
    transferred_chunks: int = 0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    error_message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            'transfer_id': self.transfer_id,
            'filename': self.filename,
            'file_size': self.file_size,
            'file_hash': self.file_hash,
            'total_chunks': self.total_chunks,
            'chunk_size': self.chunk_size,
            'state': self.state.value,
            'transferred_chunks': self.transferred_chunks,
            'chunks': [
                {
                    'chunk_index': c.chunk_index,
                    'offset': c.offset,
                    'size': c.size,
                    'checksum': c.checksum,
                    'transferred': c.transferred
                }
                for c in self.chunks
            ]
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TransferTask':
        """Create from dictionary"""
        chunks = [
            ChunkInfo(
                chunk_index=c['chunk_index'],
                offset=c['offset'],
                size=c['size'],
                checksum=c['checksum'],
                transferred=c.get('transferred', False)
            )
            for c in data.get('chunks', [])
        ]
        return cls(
            transfer_id=data['transfer_id'],
            filename=data['filename'],
            file_size=data['file_size'],
            file_hash=data['file_hash'],
            total_chunks=data['total_chunks'],
            chunk_size=data['chunk_size'],
            chunks=chunks,
            state=TransferState(data.get('state', 'pending')),
            transferred_chunks=data.get('transferred_chunks', 0),
            created_at=data.get('created_at', time.time()),
            updated_at=data.get('updated_at', time.time()),
            error_message=data.get('error_message', '')
        )

    def get_pending_chunks(self) -> List[ChunkInfo]:
        """Get list of chunks that haven't been transferred yet"""
        return [c for c in self.chunks if not c.transferred]

    @property
    def progress(self) -> float:
        """Get transfer progress as percentage"""
        if self.total_chunks == 0:
            return 0.0
        return (self.transferred_chunks / self.total_chunks) * 100


# TEMP_DIR for storing incomplete transfers
TEMP_DIR = DATA_DIR / "transfers"
TEMP_DIR.mkdir(parents=True, exist_ok=True)


def calculate_file_hash(data: bytes) -> str:
    """Calculate MD5 hash for file data"""
    return hashlib.md5(data).hexdigest()



class TransferQueue:
    """Thread-safe transfer queue with priority support"""

    def __init__(self, max_concurrent: int = 3):
        self.max_concurrent = max_concurrent
        self._queue: List[TransferTask] = []
        self._active: Dict[str, TransferTask] = {}
        self._lock = threading.Lock()

    def add(self, task: TransferTask) -> bool:
        """Add task to queue"""
        with self._lock:
            # Check if already exists
            if any(t.transfer_id == task.transfer_id for t in self._queue):
                return False
            if task.transfer_id in self._active:
                return False
            self._queue.append(task)
            return True

    def get_next(self) -> Optional[TransferTask]:
        """Get next task to process if slots available"""
        with self._lock:
            if len(self._active) >= self.max_concurrent:
                return None
            if not self._queue:
                return None
            task = self._queue.pop(0)
            self._active[task.transfer_id] = task
            return task

    def complete(self, transfer_id: str):
        """Mark task as completed and remove from active"""
        with self._lock:
            self._active.pop(transfer_id, None)

    def get_active_count(self) -> int:
        """Get number of active transfers"""
        with self._lock:
            return len(self._active)

    def get_queue_length(self) -> int:
        """Get number of pending transfers"""
        with self._lock:
            return len(self._queue)

    def cancel(self, transfer_id: str) -> bool:
        """Cancel a transfer"""
        with self._lock:
            # Remove from queue
            self._queue = [t for t in self._queue if t.transfer_id != transfer_id]
            # Remove from active
            task = self._active.pop(transfer_id, None)
            if task:
                task.state = TransferState.CANCELLED
                return True
            return False


class ChunkedTransferManager:
    """
    Manages chunked file transfers with resume capability.
    Handles both sending and receiving of large files.
    """

    def __init__(
        self,
        on_log: Optional[Callable[[str], None]] = None,
        on_progress: Optional[Callable[[str, float], None]] = None,
        on_complete: Optional[Callable[[str, bytes], None]] = None,
        on_error: Optional[Callable[[str, str], None]] = None
    ):
        self.on_log = on_log or (lambda x: None)
        self.on_progress = on_progress or (lambda x, y: None)
        self.on_complete = on_complete or (lambda x, y: None)
        self.on_error = on_error or (lambda x, y: None)

        self._send_queue = TransferQueue(config.max_concurrent_transfers)
        self._receive_queue = TransferQueue(config.max_concurrent_transfers)

        # Outgoing transfers (sending)
        self._outgoing: Dict[str, TransferTask] = {}
        self._outgoing_data: Dict[str, bytes] = {}  # File data being sent

        # Incoming transfers (receiving)
        self._incoming: Dict[str, TransferTask] = {}
        self._incoming_data: Dict[str, bytearray] = {}  # Partial file data

        self._lock = threading.Lock()
        self._state_file = TEMP_DIR / "transfer_state.json"

        # Load saved state for resume
        self._load_state()

    def _log(self, message: str):
        """Log message"""
        self.on_log(f"[CHUNKED] {message}")

    def _save_state(self):
        """Save transfer state for resume capability"""
        if not config.resume_enabled:
            return
        try:
            state = {
                'incoming': {
                    tid: task.to_dict()
                    for tid, task in self._incoming.items()
                    if task.state in (TransferState.PENDING, TransferState.TRANSFERRING, TransferState.PAUSED)
                }
            }
            with open(self._state_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            self._log(f"Failed to save state: {e}")

    def _load_state(self):
        """Load saved transfer state"""
        if not config.resume_enabled:
            return
        if not self._state_file.exists():
            return
        try:
            with open(self._state_file, 'r', encoding='utf-8') as f:
                state = json.load(f)
            for tid, task_data in state.get('incoming', {}).items():
                task = TransferTask.from_dict(task_data)
                task.state = TransferState.PAUSED  # Mark as paused for resume
                self._incoming[tid] = task
                # Load partial data if exists
                partial_file = TEMP_DIR / f"{tid}.partial"
                if partial_file.exists():
                    with open(partial_file, 'rb') as f:
                        self._incoming_data[tid] = bytearray(f.read())
                else:
                    self._incoming_data[tid] = bytearray(task.file_size)
                self._log(f"Loaded paused transfer: {task.filename} ({task.progress:.1f}%)")
        except Exception as e:
            self._log(f"Failed to load state: {e}")

    def _save_partial_data(self, transfer_id: str):
        """Save partial received data to disk for resume"""
        if not config.resume_enabled:
            return
        if transfer_id not in self._incoming_data:
            return
        try:
            partial_file = TEMP_DIR / f"{transfer_id}.partial"
            with open(partial_file, 'wb') as f:
                f.write(self._incoming_data[transfer_id])
        except Exception as e:
            self._log(f"Failed to save partial data: {e}")

    def _cleanup_transfer(self, transfer_id: str):
        """Clean up completed or cancelled transfer"""
        with self._lock:
            self._outgoing.pop(transfer_id, None)
            self._outgoing_data.pop(transfer_id, None)
            self._incoming.pop(transfer_id, None)
            self._incoming_data.pop(transfer_id, None)

        # Remove partial file
        partial_file = TEMP_DIR / f"{transfer_id}.partial"
        if partial_file.exists():
            try:
                partial_file.unlink()
            except Exception:
                pass

    def cleanup_transfer(self, transfer_id: str):
        """Public method to clean up a transfer"""
        self._cleanup_transfer(transfer_id)

        self._save_state()

    # === SENDING METHODS ===

    def prepare_send(self, filename: str, data: bytes) -> Optional[TransferTask]:
        """
        Prepare a file for chunked transfer.
        Returns TransferTask if file needs chunked transfer, None otherwise.
        """
        if len(data) < config.chunk_threshold:
            return None  # Small file, use normal transfer

        transfer_id = str(uuid.uuid4())
        file_hash = calculate_file_hash(data)
        chunk_size = config.chunk_size

        # Create chunks info
        chunks = []
        offset = 0
        chunk_index = 0
        while offset < len(data):
            chunk_data = data[offset:offset + chunk_size]
            chunk_hash = hashlib.md5(chunk_data).hexdigest()
            chunks.append(ChunkInfo(
                chunk_index=chunk_index,
                offset=offset,
                size=len(chunk_data),
                checksum=chunk_hash
            ))
            offset += len(chunk_data)
            chunk_index += 1

        task = TransferTask(
            transfer_id=transfer_id,
            filename=filename,
            file_size=len(data),
            file_hash=file_hash,
            total_chunks=len(chunks),
            chunk_size=chunk_size,
            chunks=chunks,
            state=TransferState.PENDING
        )

        with self._lock:
            self._outgoing[transfer_id] = task
            self._outgoing_data[transfer_id] = data

        self._log(f"Prepared chunked transfer: {filename} ({len(data) / 1024 / 1024:.2f}MB, {len(chunks)} chunks)")

        # Trigger initial progress callback to show UI
        self.on_progress(transfer_id, 0)

        return task

    def get_chunk_data(self, transfer_id: str, chunk_index: int) -> Optional[Dict[str, Any]]:
        """Get data for a specific chunk to send"""
        with self._lock:
            task = self._outgoing.get(transfer_id)
            data = self._outgoing_data.get(transfer_id)

        if not task or not data:
            return None

        if chunk_index >= len(task.chunks):
            return None

        chunk_info = task.chunks[chunk_index]
        chunk_data = data[chunk_info.offset:chunk_info.offset + chunk_info.size]

        # Compress and encode the chunk
        encoded, is_compressed = compress_and_encode(chunk_data)

        return {
            'type': 'chunk_data',
            'transfer_id': transfer_id,
            'chunk_index': chunk_index,
            'offset': chunk_info.offset,
            'size': chunk_info.size,
            'checksum': chunk_info.checksum,
            'data': encoded,
            'compressed': is_compressed
        }

    def mark_chunk_sent(self, transfer_id: str, chunk_index: int):
        """Mark a chunk as successfully sent"""
        with self._lock:
            task = self._outgoing.get(transfer_id)
            if task and chunk_index < len(task.chunks):
                task.chunks[chunk_index].transferred = True
                task.transferred_chunks += 1
                task.updated_at = time.time()

                if task.transferred_chunks >= task.total_chunks:
                    task.state = TransferState.COMPLETED
                    self._log(f"Transfer complete: {task.filename}")
                else:
                    task.state = TransferState.TRANSFERRING
                    self.on_progress(transfer_id, task.progress)

    def get_transfer_init_message(self, task: TransferTask) -> Dict[str, Any]:
        """Get the initialization message for a chunked transfer"""
        return {
            'type': 'chunked_transfer_init',
            'transfer_id': task.transfer_id,
            'filename': task.filename,
            'file_size': task.file_size,
            'file_hash': task.file_hash,
            'total_chunks': task.total_chunks,
            'chunk_size': task.chunk_size,
            'chunks': [
                {
                    'chunk_index': c.chunk_index,
                    'offset': c.offset,
                    'size': c.size,
                    'checksum': c.checksum
                }
                for c in task.chunks
            ]
        }

    # === RECEIVING METHODS ===

    def handle_transfer_init(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle incoming chunked transfer initialization.
        Returns response with list of needed chunks (for resume support).
        """
        transfer_id = data['transfer_id']
        self._log(f"Processing transfer init: {transfer_id[:8]}")
        is_new_transfer = False

        try:
            with self._lock:
                # Check if we have a paused transfer for this file
                existing = self._incoming.get(transfer_id)
                if existing and existing.file_hash == data['file_hash']:
                    # Resume existing transfer
                    needed_chunks = [c.chunk_index for c in existing.get_pending_chunks()]
                    existing.state = TransferState.TRANSFERRING
                    self._log(f"Resuming transfer: {existing.filename} ({existing.progress:.1f}% done)")
                else:
                    # New transfer
                    is_new_transfer = True
                    self._log(f"Creating new transfer task...")
                    chunks = [
                        ChunkInfo(
                            chunk_index=c['chunk_index'],
                            offset=c['offset'],
                            size=c['size'],
                            checksum=c['checksum']
                        )
                        for c in data['chunks']
                    ]
                    task = TransferTask(
                        transfer_id=transfer_id,
                        filename=data['filename'],
                        file_size=data['file_size'],
                        file_hash=data['file_hash'],
                        total_chunks=data['total_chunks'],
                        chunk_size=data['chunk_size'],
                        chunks=chunks,
                        state=TransferState.TRANSFERRING
                    )
                    self._incoming[transfer_id] = task

                    # Allocate buffer for file data
                    file_size = data['file_size']
                    self._log(f"Allocating {file_size / 1024 / 1024:.2f}MB buffer...")
                    self._incoming_data[transfer_id] = bytearray(file_size)
                    self._log(f"Buffer allocated successfully")

                    needed_chunks = list(range(data['total_chunks']))
                    self._log(f"Starting chunked receive: {data['filename']} ({file_size / 1024 / 1024:.2f}MB)")

            # Trigger progress callback OUTSIDE the lock to avoid potential deadlock
            if is_new_transfer:
                self._log(f"Triggering initial progress callback...")
                try:
                    self.on_progress(transfer_id, 0)
                    self._log(f"Progress callback completed")
                except Exception as e:
                    self._log(f"Warning: Progress callback failed: {e}")

            self._log(f"Saving transfer state...")
            self._save_state()
            self._log(f"Transfer init complete, returning ACK with {len(needed_chunks)} chunks")

            return {
                'type': 'chunked_transfer_ack',
                'transfer_id': transfer_id,
                'needed_chunks': needed_chunks
            }
        except Exception as e:
            self._log(f"Error in handle_transfer_init: {e}")
            import traceback
            self._log(f"Traceback: {traceback.format_exc()}")
            raise

    def handle_chunk_data(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Handle incoming chunk data.
        Returns chunk_ack message or None on error.
        """
        transfer_id = data['transfer_id']
        chunk_index = data['chunk_index']

        with self._lock:
            task = self._incoming.get(transfer_id)
            buffer = self._incoming_data.get(transfer_id)

        if not task or buffer is None:
            self._log(f"Unknown transfer: {transfer_id}")
            return None

        if chunk_index >= len(task.chunks):
            self._log(f"Invalid chunk index: {chunk_index}")
            return None

        chunk_info = task.chunks[chunk_index]

        # Decode and decompress data
        try:
            is_compressed = data.get('compressed', False)
            chunk_data = decode_and_decompress(data['data'], is_compressed)
        except Exception as e:
            self._log(f"Failed to decode chunk: {e}")
            return {'type': 'chunk_nack', 'transfer_id': transfer_id, 'chunk_index': chunk_index, 'error': 'decode_error'}

        # Verify checksum
        received_hash = hashlib.md5(chunk_data).hexdigest()
        if received_hash != chunk_info.checksum:
            self._log(f"Checksum mismatch for chunk {chunk_index}")
            return {'type': 'chunk_nack', 'transfer_id': transfer_id, 'chunk_index': chunk_index, 'error': 'checksum_error'}

        # Write to buffer
        offset = chunk_info.offset
        buffer[offset:offset + len(chunk_data)] = chunk_data

        with self._lock:
            chunk_info.transferred = True
            task.transferred_chunks += 1
            task.updated_at = time.time()
            progress = task.progress
            is_complete = task.transferred_chunks >= task.total_chunks

        self.on_progress(transfer_id, progress)

        # Save partial data periodically (every 10 chunks)
        if task.transferred_chunks % 10 == 0:
            self._save_partial_data(transfer_id)
            self._save_state()

        # Check if transfer is complete
        if is_complete:
            return self._complete_transfer(transfer_id)

        return {'type': 'chunk_ack', 'transfer_id': transfer_id, 'chunk_index': chunk_index}

    def _complete_transfer(self, transfer_id: str) -> Dict[str, Any]:
        """Complete a transfer and verify file integrity"""
        with self._lock:
            task = self._incoming.get(transfer_id)
            buffer = self._incoming_data.get(transfer_id)

        if not task or buffer is None:
            return {'type': 'transfer_error', 'transfer_id': transfer_id, 'error': 'unknown_transfer'}

        # Verify complete file hash
        file_data = bytes(buffer)
        file_hash = calculate_file_hash(file_data)

        if file_hash != task.file_hash:
            self._log(f"File hash mismatch for {task.filename}")
            task.state = TransferState.FAILED
            task.error_message = "File hash mismatch"
            self.on_error(transfer_id, "File integrity check failed")
            return {'type': 'transfer_error', 'transfer_id': transfer_id, 'error': 'hash_mismatch'}

        task.state = TransferState.COMPLETED
        self._log(f"Transfer complete: {task.filename} ({task.file_size / 1024 / 1024:.2f}MB)")

        # Notify completion with file data
        self.on_complete(transfer_id, file_data)

        # Cleanup
        self._cleanup_transfer(transfer_id)

        return {
            'type': 'transfer_complete',
            'transfer_id': transfer_id,
            'filename': task.filename,
            'file_size': task.file_size
        }

    def get_pending_incoming(self) -> List[TransferTask]:
        """Get list of paused/pending incoming transfers for resume"""
        with self._lock:
            return [
                task for task in self._incoming.values()
                if task.state in (TransferState.PAUSED, TransferState.PENDING)
            ]

    def cancel_transfer(self, transfer_id: str) -> bool:
        """Cancel a transfer"""
        with self._lock:
            task = self._outgoing.get(transfer_id) or self._incoming.get(transfer_id)
            if task:
                task.state = TransferState.CANCELLED
        self._cleanup_transfer(transfer_id)
        return task is not None

    def get_transfer_status(self, transfer_id: str) -> Optional[Dict[str, Any]]:
        """Get status of a transfer"""
        with self._lock:
            task = self._outgoing.get(transfer_id) or self._incoming.get(transfer_id)
            if not task:
                return None
            return {
                'transfer_id': task.transfer_id,
                'filename': task.filename,
                'file_size': task.file_size,
                'state': task.state.value,
                'progress': task.progress,
                'transferred_chunks': task.transferred_chunks,
                'total_chunks': task.total_chunks
            }


def calculate_chunk_hash(data: bytes) -> str:
    """Calculate hash for a single chunk"""
    return hashlib.md5(data).hexdigest()


def split_into_chunks(data: bytes, chunk_size: int) -> List[tuple]:
    """Split data into chunks, returns list of (offset, chunk_data)"""
    chunks = []
    offset = 0
    while offset < len(data):
        chunk_data = data[offset:offset + chunk_size]
        chunks.append((offset, chunk_data))
        offset += len(chunk_data)
    return chunks


def needs_chunked_transfer(file_size: int) -> bool:
    """Check if a file needs chunked transfer based on size"""
    return file_size >= config.chunk_threshold

