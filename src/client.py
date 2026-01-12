# -*- coding: utf-8 -*-
"""
client.py - WebSocket client for clipboard synchronization
Connects to server and syncs clipboard content bidirectionally
Supports text, image, and file sync with zstd compression
Supports chunked transfer for large files (>10MB) with resume capability
"""

import asyncio
import json
import threading
import hashlib
from typing import Optional, Callable, Dict, Any, List
from datetime import datetime
import websockets
from websockets.client import WebSocketClientProtocol

from .clipboard_monitor import ClipboardItem, ContentType, FileData
from .compression import compress_and_encode, decode_and_decompress, get_compression_stats
from .config import config
from .chunked_transfer import (
    ChunkedTransferManager, TransferTask, TransferState,
    needs_chunked_transfer, calculate_file_hash
)


class ClipboardClient:
    """
    WebSocket client for clipboard synchronization.
    Connects to a server and syncs clipboard in real-time.
    Supports chunked transfer for large files (>10MB).
    """

    def __init__(
        self,
        server_url: str,
        on_log: Optional[Callable[[str], None]] = None,
        on_clipboard_received: Optional[Callable[[ClipboardItem], None]] = None,
        on_connected: Optional[Callable[[bool], None]] = None,
        on_reconnecting: Optional[Callable[[], None]] = None,
        on_transfer_progress: Optional[Callable[[str, float], None]] = None
    ):
        self.server_url = server_url
        self.on_log = on_log or (lambda x: None)
        self.on_clipboard_received = on_clipboard_received or (lambda x: None)
        self.on_connected = on_connected or (lambda x: None)
        self.on_reconnecting = on_reconnecting or (lambda: None)
        self.on_transfer_progress = on_transfer_progress or (lambda x, y: None)

        self._websocket: Optional[WebSocketClientProtocol] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._connected = False
        self._last_hash = ""
        self._reconnect_delay = 1

        # Chunked transfer manager for large files
        self._transfer_manager = ChunkedTransferManager(
            on_log=self.on_log,
            on_progress=self._on_transfer_progress,
            on_complete=self._on_transfer_complete,
            on_error=self._on_transfer_error
        )

        # Pending chunked transfers (transfer_id -> filename)
        self._pending_transfers: Dict[str, str] = {}

    def _on_transfer_progress(self, transfer_id: str, progress: float):
        """Handle transfer progress update"""
        self.on_transfer_progress(transfer_id, progress)
        filename = self._pending_transfers.get(transfer_id, "unknown")
        if int(progress) % 20 == 0:  # Log every 20%
            self._log(f"Transfer {filename}: {progress:.1f}%")

    def _on_transfer_complete(self, transfer_id: str, data: bytes):
        """Handle completed chunked transfer"""
        filename = self._pending_transfers.pop(transfer_id, "received_file")
        self._log(f"Chunked transfer complete: {filename} ({len(data) / 1024 / 1024:.2f}MB)")

        # Create clipboard item from received file
        file_data = FileData(filename=filename, content=data)
        item = ClipboardItem.from_file_contents([file_data], "remote")
        self.on_clipboard_received(item)

    def _on_transfer_error(self, transfer_id: str, error: str):
        """Handle transfer error"""
        filename = self._pending_transfers.pop(transfer_id, "unknown")
        self._log(f"Transfer failed for {filename}: {error}")

    def _log(self, message: str):
        """Thread-safe logging"""
        self.on_log(f"[CLIENT] {message}")
    
    async def _connect(self):
        """Establish connection to server"""
        while self._running:
            try:
                self._log(f"Connecting to {self.server_url}...")
                
                async with websockets.connect(
                    self.server_url,
                    ping_interval=30,
                    ping_timeout=10
                ) as websocket:
                    self._websocket = websocket
                    
                    # Authenticate if password is set
                    if config.connection_password:
                        await websocket.send(json.dumps({
                            'type': 'auth',
                            'password': config.connection_password
                        }))
                        response = await asyncio.wait_for(websocket.recv(), timeout=10)
                        auth_result = json.loads(response)
                        if not auth_result.get('success'):
                            self._log("Authentication failed!")
                            self.on_connected(False)
                            return
                    
                    self._connected = True
                    self._reconnect_delay = 1
                    self._log("Connected successfully!")
                    self.on_connected(True)
                    
                    # Message receive loop
                    async for message in websocket:
                        await self._handle_message(message)
            
            except websockets.exceptions.ConnectionClosed:
                self._log("Connection closed")
            except Exception as e:
                self._log(f"Connection error: {e}")
            
            self._connected = False
            self._websocket = None
            self.on_connected(False)

            if self._running:
                self._log(f"Reconnecting in {self._reconnect_delay}s...")
                self.on_reconnecting()  # Notify UI that we're reconnecting
                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(self._reconnect_delay * 2, 30)
    
    async def _handle_message(self, message: str):
        """Handle incoming message from server"""
        try:
            data = json.loads(message)
            msg_type = data.get('type')

            if msg_type == 'clipboard':
                content_type = ContentType(data.get('content_type', 'text'))
                content_hash = data.get('content_hash', '')
                is_compressed = data.get('compressed', False)

                # Avoid echo
                if content_hash == self._last_hash:
                    return
                self._last_hash = content_hash

                # Create clipboard item based on content type
                if content_type == ContentType.TEXT:
                    content = data.get('content', '')
                    if is_compressed and content:
                        content = decode_and_decompress(content, True).decode('utf-8')
                    item = ClipboardItem.from_text(content, "remote")
                    self._log(f"Received text: {content[:30]}..." if len(content) > 30 else f"Received text: {content}")

                elif content_type == ContentType.IMAGE:
                    image_data_str = data.get('image_data', '')
                    if image_data_str:
                        image_data = decode_and_decompress(image_data_str, is_compressed)
                        item = ClipboardItem.from_image(image_data, "remote")
                        self._log(f"Received image: {len(image_data)} bytes")
                    else:
                        return

                elif content_type == ContentType.FILES:
                    # Check if we have actual file contents
                    files_data = data.get('files', [])
                    if files_data:
                        file_contents = []
                        total_size = 0
                        for fd in files_data:
                            is_file_compressed = fd.get('compressed', False)
                            content = decode_and_decompress(fd['content'], is_file_compressed)
                            file_contents.append(FileData(
                                filename=fd['filename'],
                                content=content
                            ))
                            total_size += len(content)
                        item = ClipboardItem.from_file_contents(file_contents, "remote")
                        self._log(f"Received {len(file_contents)} file(s), total: {total_size / 1024:.1f}KB")
                    else:
                        # Fallback: just file paths (no content)
                        file_paths = data.get('file_paths', [])
                        item = ClipboardItem.from_files(file_paths, "remote")
                        self._log(f"Received file paths: {len(file_paths)} files")
                else:
                    return

                self.on_clipboard_received(item)

            elif msg_type == 'pong':
                pass  # Heartbeat response

            # === Chunked transfer messages ===
            elif msg_type == 'chunked_transfer_init':
                # Incoming chunked transfer initialization
                await self._handle_chunked_init(data)

            elif msg_type == 'chunked_transfer_ack':
                # Response to our transfer init - start sending chunks
                await self._handle_chunked_ack(data)

            elif msg_type == 'chunk_data':
                # Incoming chunk data
                await self._handle_chunk_data(data)

            elif msg_type == 'chunk_ack':
                # Chunk received successfully, send next
                await self._handle_chunk_ack(data)

            elif msg_type == 'chunk_nack':
                # Chunk failed, resend
                await self._handle_chunk_nack(data)

            elif msg_type == 'transfer_complete':
                # Transfer finished
                self._log(f"Transfer {data.get('transfer_id')} confirmed complete")

        except json.JSONDecodeError:
            self._log("Invalid JSON received")
        except Exception as e:
            self._log(f"Message handling error: {e}")

    async def _handle_chunked_init(self, data: Dict[str, Any]):
        """Handle incoming chunked transfer initialization"""
        transfer_id = data['transfer_id']
        filename = data['filename']
        file_size = data['file_size']

        self._pending_transfers[transfer_id] = filename
        self._log(f"Incoming chunked transfer: {filename} ({file_size / 1024 / 1024:.2f}MB)")

        # Acknowledge and request chunks (or specify which chunks we need for resume)
        response = self._transfer_manager.handle_transfer_init(data)
        await self._websocket.send(json.dumps(response))

    async def _handle_chunked_ack(self, data: Dict[str, Any]):
        """Handle acknowledgment of our transfer init - start sending chunks"""
        transfer_id = data['transfer_id']
        needed_chunks = data.get('needed_chunks', [])

        self._log(f"Transfer {transfer_id} acknowledged, sending {len(needed_chunks)} chunks")

        # Send all needed chunks
        for chunk_index in needed_chunks:
            chunk_data = self._transfer_manager.get_chunk_data(transfer_id, chunk_index)
            if chunk_data:
                await self._websocket.send(json.dumps(chunk_data))
                # Small delay to prevent overwhelming the connection
                await asyncio.sleep(0.01)

    async def _handle_chunk_data(self, data: Dict[str, Any]):
        """Handle incoming chunk data"""
        response = self._transfer_manager.handle_chunk_data(data)
        if response:
            await self._websocket.send(json.dumps(response))

    async def _handle_chunk_ack(self, data: Dict[str, Any]):
        """Handle chunk acknowledgment"""
        transfer_id = data['transfer_id']
        chunk_index = data['chunk_index']
        self._transfer_manager.mark_chunk_sent(transfer_id, chunk_index)

    async def _handle_chunk_nack(self, data: Dict[str, Any]):
        """Handle chunk negative acknowledgment - resend chunk"""
        transfer_id = data['transfer_id']
        chunk_index = data['chunk_index']
        error = data.get('error', 'unknown')

        self._log(f"Chunk {chunk_index} failed ({error}), resending...")

        chunk_data = self._transfer_manager.get_chunk_data(transfer_id, chunk_index)
        if chunk_data:
            await self._websocket.send(json.dumps(chunk_data))
    
    async def _send_clipboard_item(self, item: ClipboardItem):
        """Send clipboard item to server with compression"""
        if not self._websocket or not self._connected:
            return

        if item.content_hash == self._last_hash:
            return
        self._last_hash = item.content_hash

        try:
            data = {
                'type': 'clipboard',
                'content_type': item.content_type.value,
                'content_hash': item.content_hash,
                'timestamp': datetime.now().isoformat(),
                'compressed': False
            }

            if item.content_type == ContentType.TEXT:
                content_bytes = item.content.encode('utf-8')
                if len(content_bytes) > 512:
                    encoded, is_compressed = compress_and_encode(content_bytes)
                    data['content'] = encoded
                    data['compressed'] = is_compressed
                    if is_compressed:
                        stats = get_compression_stats(len(content_bytes), len(encoded))
                        self._log(f"Compressed text: saved {stats['saved_percent']:.1f}%")
                else:
                    data['content'] = item.content

            elif item.content_type == ContentType.IMAGE:
                encoded, is_compressed = compress_and_encode(item.image_data)
                data['image_data'] = encoded
                data['compressed'] = is_compressed
                stats = get_compression_stats(len(item.image_data), len(encoded))
                self._log(f"Sending image: {len(item.image_data)} bytes, saved: {stats['saved_percent']:.1f}%")

            elif item.content_type == ContentType.FILES:
                if item.file_contents:
                    # Check for large files that need chunked transfer
                    small_files = []
                    large_files = []

                    for file_data in item.file_contents:
                        if needs_chunked_transfer(len(file_data.content)):
                            large_files.append(file_data)
                        else:
                            small_files.append(file_data)

                    # Send small files normally
                    if small_files:
                        files_data = []
                        total_size = 0
                        for file_data in small_files:
                            encoded, is_compressed = compress_and_encode(file_data.content)
                            files_data.append({
                                'filename': file_data.filename,
                                'content': encoded,
                                'compressed': is_compressed,
                                'size': len(file_data.content)
                            })
                            total_size += len(file_data.content)
                        data['files'] = files_data
                        data['file_count'] = len(files_data)
                        self._log(f"Sending {len(files_data)} small file(s), total: {total_size / 1024:.1f}KB")
                        await self._websocket.send(json.dumps(data))

                    # Send large files via chunked transfer
                    for file_data in large_files:
                        await self._send_large_file(file_data)

                    return  # Already sent above
                else:
                    # Fallback to just paths (for local-only use)
                    data['file_paths'] = item.file_paths

            await self._websocket.send(json.dumps(data))
        except Exception as e:
            self._log(f"Send error: {e}")

    async def _send_large_file(self, file_data: FileData):
        """Send a large file using chunked transfer"""
        task = self._transfer_manager.prepare_send(file_data.filename, file_data.content)
        if not task:
            self._log(f"Failed to prepare chunked transfer for {file_data.filename}")
            return

        self._pending_transfers[task.transfer_id] = file_data.filename

        # Send transfer init message
        init_msg = self._transfer_manager.get_transfer_init_message(task)
        await self._websocket.send(json.dumps(init_msg))
        self._log(f"Started chunked transfer: {file_data.filename} ({len(file_data.content) / 1024 / 1024:.2f}MB)")

    async def _send_clipboard(self, content: str):
        """Legacy method for sending text clipboard"""
        item = ClipboardItem.from_text(content, "local")
        await self._send_clipboard_item(item)

    def send_clipboard_item(self, item: ClipboardItem):
        """Thread-safe method to send clipboard item"""
        if self._loop and self._connected:
            asyncio.run_coroutine_threadsafe(
                self._send_clipboard_item(item),
                self._loop
            )

    def send_clipboard(self, content: str):
        """Thread-safe method to send text clipboard (legacy compatibility)"""
        item = ClipboardItem.from_text(content, "local")
        self.send_clipboard_item(item)
    
    def start(self):
        """Start client in background thread"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_in_thread, daemon=True)
        self._thread.start()
    
    def _run_in_thread(self):
        """Run asyncio event loop in thread"""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._connect())
        except Exception as e:
            self._log(f"Client error: {e}")
        finally:
            self._loop.close()
    
    def stop(self):
        """Stop the client"""
        self._running = False
        if self._websocket and self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self._websocket.close(),
                self._loop
            )
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
    
    @property
    def is_connected(self) -> bool:
        return self._connected

