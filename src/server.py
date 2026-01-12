# -*- coding: utf-8 -*-
"""
server.py - WebSocket server for clipboard synchronization
Handles client connections, message broadcasting, and sync coordination
Supports text, image, and file sync with zstd compression
Supports chunked transfer for large files (>10MB) with resume capability
"""

import asyncio
import json
import hashlib
import threading
from typing import Set, Optional, Callable, Dict, Any, List
from datetime import datetime
import websockets
from websockets.server import WebSocketServerProtocol

from .clipboard_monitor import ClipboardItem, ContentType, FileData
from .compression import compress_and_encode, decode_and_decompress, get_compression_stats
from .config import config
from .chunked_transfer import (
    ChunkedTransferManager, TransferTask, TransferState,
    needs_chunked_transfer, calculate_file_hash
)


class ClipboardServer:
    """
    WebSocket server for clipboard synchronization.
    Broadcasts clipboard changes to all connected clients.
    Supports chunked transfer for large files (>10MB).
    """

    def __init__(
        self,
        port: int = 2580,
        on_log: Optional[Callable[[str], None]] = None,
        on_client_change: Optional[Callable[[int], None]] = None,
        on_clipboard_received: Optional[Callable[[ClipboardItem], None]] = None,
        on_transfer_progress: Optional[Callable[[str, float], None]] = None
    ):
        self.port = port
        self.on_log = on_log or (lambda x: None)
        self.on_client_change = on_client_change or (lambda x: None)
        self.on_clipboard_received = on_clipboard_received or (lambda x: None)
        self.on_transfer_progress = on_transfer_progress or (lambda x, y: None)

        self._clients: Set[WebSocketServerProtocol] = set()
        self._server = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._last_hash = ""

        # Chunked transfer manager for large files
        self._transfer_manager = ChunkedTransferManager(
            on_log=self.on_log,
            on_progress=self._on_transfer_progress,
            on_complete=self._on_transfer_complete,
            on_error=self._on_transfer_error
        )

        # Track chunked transfers: transfer_id -> (source_websocket, filename)
        self._chunked_transfers: Dict[str, tuple] = {}

    def _on_transfer_progress(self, transfer_id: str, progress: float):
        """Handle transfer progress update"""
        self.on_transfer_progress(transfer_id, progress)

    def _on_transfer_complete(self, transfer_id: str, data: bytes):
        """Handle completed chunked transfer - notify local clipboard"""
        info = self._chunked_transfers.pop(transfer_id, None)
        if info:
            filename = info[1]
            self._log(f"Chunked transfer complete: {filename} ({len(data) / 1024 / 1024:.2f}MB)")
            file_data = FileData(filename=filename, content=data)
            item = ClipboardItem.from_file_contents([file_data], "remote")
            self.on_clipboard_received(item)

    def _on_transfer_error(self, transfer_id: str, error: str):
        """Handle transfer error"""
        info = self._chunked_transfers.pop(transfer_id, None)
        if info:
            self._log(f"Transfer failed for {info[1]}: {error}")

    def _log(self, message: str):
        """Thread-safe logging"""
        self.on_log(f"[SERVER] {message}")
    
    async def _handler(self, websocket: WebSocketServerProtocol):
        """Handle client connection"""
        # Authenticate if password is set
        if config.connection_password:
            try:
                auth_msg = await asyncio.wait_for(websocket.recv(), timeout=10)
                auth_data = json.loads(auth_msg)
                if auth_data.get('password') != config.connection_password:
                    await websocket.send(json.dumps({'type': 'auth', 'success': False}))
                    await websocket.close()
                    return
                await websocket.send(json.dumps({'type': 'auth', 'success': True}))
            except Exception:
                await websocket.close()
                return
        
        # Register client
        self._clients.add(websocket)
        client_addr = websocket.remote_address
        self._log(f"Client connected: {client_addr} (Total: {len(self._clients)})")
        self.on_client_change(len(self._clients))
        
        try:
            async for message in websocket:
                await self._handle_message(websocket, message)
        except websockets.exceptions.ConnectionClosed as e:
            self._log(f"Connection closed: {e.code} {e.reason}")
        except Exception as e:
            self._log(f"Handler error: {e}")
        finally:
            self._clients.discard(websocket)
            self._log(f"Client disconnected: {client_addr} (Total: {len(self._clients)})")
            self.on_client_change(len(self._clients))
    
    async def _handle_message(self, websocket: WebSocketServerProtocol, message: str):
        """Handle incoming message from client"""
        try:
            data = json.loads(message)
            msg_type = data.get('type')

            # Log message type for debugging (except frequent ping messages)
            if msg_type not in ('ping', 'pong'):
                self._log(f"Received message type: {msg_type}")

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
                    self._log(f"Synced text: {content[:30]}..." if len(content) > 30 else f"Synced text: {content}")

                elif content_type == ContentType.IMAGE:
                    image_data_str = data.get('image_data', '')
                    if image_data_str:
                        image_data = decode_and_decompress(image_data_str, is_compressed)
                        item = ClipboardItem.from_image(image_data, "remote")
                        stats = get_compression_stats(len(image_data), len(image_data_str))
                        self._log(f"Synced image: {len(image_data)} bytes (saved {stats['saved_percent']:.1f}%)")
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

                # Broadcast to other clients
                await self._broadcast(data, exclude=websocket)

            elif msg_type == 'ping':
                await websocket.send(json.dumps({'type': 'pong'}))

            # === Chunked transfer messages - relay between clients ===
            elif msg_type == 'chunked_transfer_init':
                # Store transfer info and relay to other clients
                transfer_id = data['transfer_id']
                filename = data['filename']
                self._chunked_transfers[transfer_id] = (websocket, filename)
                self._log(f"Relaying chunked transfer init: {filename}")
                await self._broadcast(data, exclude=websocket)

            elif msg_type == 'chunked_transfer_ack':
                # Handle acknowledgment - either relay to sender or handle server-initiated
                transfer_id = data['transfer_id']
                self._log(f"Received chunked_transfer_ack for transfer {transfer_id[:8]}")
                info = self._chunked_transfers.get(transfer_id)
                if info:
                    if info[0] is None:
                        # Server-initiated transfer - handle locally
                        self._log(f"Processing server-initiated ACK for {info[1]}")
                        await self._handle_server_chunked_ack(data, websocket)
                    elif info[0] != websocket:
                        # Relay to original sender
                        self._log(f"Relaying ACK to original sender for {info[1]}")
                        try:
                            await info[0].send(message)
                        except Exception:
                            pass
                else:
                    self._log(f"Warning: ACK received for unknown transfer {transfer_id[:8]}")

            elif msg_type == 'chunk_data':
                # Relay chunk data to other clients
                await self._broadcast(data, exclude=websocket)

            elif msg_type == 'chunk_ack':
                # Handle chunk acknowledgment
                transfer_id = data['transfer_id']
                info = self._chunked_transfers.get(transfer_id)
                if info:
                    if info[0] is None:
                        # Server-initiated transfer - update progress based on acks
                        chunk_index = data.get('chunk_index', 0)
                        task = self._transfer_manager._outgoing.get(transfer_id)
                        if task:
                            # Mark chunk as received and update progress
                            if chunk_index < len(task.chunks):
                                task.chunks[chunk_index].received = True
                            received = sum(1 for c in task.chunks if c.received)
                            # Progress: 50-100% for receiving acknowledgments
                            progress = 50 + (received / task.total_chunks) * 50
                            self._on_transfer_progress(transfer_id, progress)

                            if received >= task.total_chunks:
                                # All chunks received, cleanup
                                self._transfer_manager.cleanup_transfer(transfer_id)
                                self._chunked_transfers.pop(transfer_id, None)
                                self._log(f"Chunked transfer complete: {info[1]}")
                    elif info[0] != websocket:
                        # Relay to original sender
                        try:
                            await info[0].send(message)
                        except Exception:
                            pass

            elif msg_type == 'chunk_nack':
                # Relay negative acknowledgment back to sender
                transfer_id = data['transfer_id']
                info = self._chunked_transfers.get(transfer_id)
                if info:
                    if info[0] is None:
                        # Server-initiated transfer - resend chunk
                        chunk_index = data.get('chunk_index', 0)
                        chunk_data = self._transfer_manager.get_chunk_data(transfer_id, chunk_index)
                        if chunk_data:
                            try:
                                await websocket.send(json.dumps(chunk_data))
                            except Exception as e:
                                self._log(f"Failed to resend chunk {chunk_index}: {e}")
                    elif info[0] != websocket:
                        try:
                            await info[0].send(message)
                        except Exception:
                            pass

            elif msg_type == 'transfer_complete':
                # Cleanup and relay completion
                transfer_id = data['transfer_id']
                self._chunked_transfers.pop(transfer_id, None)
                await self._broadcast(data, exclude=websocket)

        except json.JSONDecodeError as e:
            self._log(f"Invalid JSON received: {e}")
        except Exception as e:
            import traceback
            self._log(f"Message handling error: {e}")
            self._log(f"Traceback: {traceback.format_exc()}")
    
    async def _broadcast(self, data: Dict[str, Any], exclude: Optional[WebSocketServerProtocol] = None):
        """Broadcast message to all clients"""
        message = json.dumps(data)
        for client in self._clients.copy():
            if client != exclude:
                try:
                    await client.send(message)
                except Exception:
                    self._clients.discard(client)
    
    async def broadcast_clipboard_item(self, item: ClipboardItem):
        """Broadcast clipboard item to all clients with compression"""
        if item.content_hash == self._last_hash:
            return
        self._last_hash = item.content_hash

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
            self._log(f"Sending image: {len(item.image_data)} bytes, compressed: {is_compressed}, saved: {stats['saved_percent']:.1f}%")

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
                    await self._broadcast(data)

                # Send large files via chunked transfer
                for file_data in large_files:
                    await self._broadcast_large_file(file_data)

                return  # Already sent above
            else:
                # Fallback to just paths (for local-only use)
                data['file_paths'] = item.file_paths

        await self._broadcast(data)

    async def _broadcast_large_file(self, file_data: FileData):
        """Broadcast a large file using chunked transfer"""
        self._log(f"Preparing chunked transfer for {file_data.filename}...")
        task = self._transfer_manager.prepare_send(file_data.filename, file_data.content)
        if not task:
            self._log(f"Failed to prepare chunked transfer for {file_data.filename}")
            return

        self._chunked_transfers[task.transfer_id] = (None, file_data.filename)  # None = from server
        self._log(f"Transfer ID: {task.transfer_id[:8]}, registered in _chunked_transfers")

        # Broadcast transfer init message
        init_msg = self._transfer_manager.get_transfer_init_message(task)
        self._log(f"Broadcasting init message to {len(self._clients)} clients...")
        await self._broadcast(init_msg)
        self._log(f"Started chunked broadcast: {file_data.filename} ({len(file_data.content) / 1024 / 1024:.2f}MB)")
        self._log(f"Waiting for client ACK for transfer {task.transfer_id[:8]}...")

        # Wait for acknowledgments and send chunks
        # Note: The actual chunk sending will be triggered by _handle_chunked_ack

    async def _handle_server_chunked_ack(self, data: Dict[str, Any], websocket: WebSocketServerProtocol):
        """Handle acknowledgment for server-initiated chunked transfer"""
        transfer_id = data['transfer_id']
        needed_chunks = data.get('needed_chunks', [])

        info = self._chunked_transfers.get(transfer_id)
        filename = info[1] if info else transfer_id[:8]

        self._log(f"Client requested {len(needed_chunks)} chunks for {filename}")

        if not needed_chunks:
            self._log(f"Warning: No chunks requested for {filename}")
            return

        # Store pending chunks for this transfer - will be sent in batches
        if not hasattr(self, '_pending_chunks'):
            self._pending_chunks = {}

        self._pending_chunks[transfer_id] = {
            'chunks': list(needed_chunks),
            'current_index': 0,
            'websocket': websocket,
            'filename': filename
        }

        # Start sending first batch of chunks
        await self._send_chunk_batch(transfer_id)

    async def _send_chunk_batch(self, transfer_id: str, batch_size: int = 3):
        """Send a batch of chunks with flow control"""
        if not hasattr(self, '_pending_chunks'):
            return

        pending = self._pending_chunks.get(transfer_id)
        if not pending:
            return

        chunks = pending['chunks']
        current = pending['current_index']
        websocket = pending['websocket']
        filename = pending['filename']
        total_chunks = len(chunks)

        if current >= total_chunks:
            # All chunks sent
            self._pending_chunks.pop(transfer_id, None)
            self._log(f"All chunks sent for {filename}")
            return

        loop = asyncio.get_event_loop()

        # Send a batch of chunks
        end_idx = min(current + batch_size, total_chunks)
        for idx in range(current, end_idx):
            chunk_index = chunks[idx]

            # Get chunk data in thread pool to avoid blocking event loop
            chunk_data = await loop.run_in_executor(
                None,
                self._transfer_manager.get_chunk_data,
                transfer_id,
                chunk_index
            )
            if chunk_data:
                try:
                    chunk_json = json.dumps(chunk_data)
                    await websocket.send(chunk_json)
                    # Update sending progress
                    send_progress = ((idx + 1) / total_chunks) * 50  # 0-50% for sending
                    self._on_transfer_progress(transfer_id, send_progress)
                    # Log progress
                    if (idx + 1) % 5 == 0 or idx == 0:
                        self._log(f"Sent chunk {idx + 1}/{total_chunks} for {filename}")
                except Exception as e:
                    self._log(f"Failed to send chunk {chunk_index}: {e}")
                    self._pending_chunks.pop(transfer_id, None)
                    return
                # Delay between chunks within batch
                await asyncio.sleep(0.05)
            else:
                self._log(f"Warning: Could not get data for chunk {chunk_index}")

        # Update current index
        pending['current_index'] = end_idx

        # If more chunks to send, schedule next batch after a delay
        if end_idx < total_chunks:
            await asyncio.sleep(0.1)  # Wait before next batch
            await self._send_chunk_batch(transfer_id)

    async def broadcast_clipboard(self, content: str):
        """Legacy method for backward compatibility - broadcasts text content"""
        item = ClipboardItem.from_text(content, "local")
        await self.broadcast_clipboard_item(item)

    def send_clipboard_item(self, item: ClipboardItem):
        """Thread-safe method to send clipboard item"""
        if self._loop and self._running:
            asyncio.run_coroutine_threadsafe(
                self.broadcast_clipboard_item(item),
                self._loop
            )

    def send_clipboard(self, content: str):
        """Thread-safe method to send text clipboard (legacy compatibility)"""
        item = ClipboardItem.from_text(content, "local")
        self.send_clipboard_item(item)
    
    async def _run_server(self):
        """Run the WebSocket server"""
        # max_size: Set to 10MB to accommodate large chunks
        # ping_interval/ping_timeout: Increased for slow networks and large transfers
        self._server = await websockets.serve(
            self._handler,
            "0.0.0.0",
            self.port,
            ping_interval=60,  # Ping every 60 seconds (was 30)
            ping_timeout=30,   # Wait 30 seconds for pong (was 10)
            max_size=10 * 1024 * 1024  # 10MB to handle chunked transfer messages
        )
        self._log(f"Server started on port {self.port}")
        await self._server.wait_closed()
    
    def start(self):
        """Start server in background thread"""
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
            self._loop.run_until_complete(self._run_server())
        except Exception as e:
            self._log(f"Server error: {e}")
        finally:
            self._loop.close()
    
    def stop(self):
        """Stop the server"""
        self._running = False
        if self._server:
            self._server.close()
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
    
    @property
    def client_count(self) -> int:
        return len(self._clients)

