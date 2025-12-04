# -*- coding: utf-8 -*-
"""
server.py - WebSocket server for clipboard synchronization
Handles client connections, message broadcasting, and sync coordination
"""

import asyncio
import json
import hashlib
import threading
from typing import Set, Optional, Callable, Dict, Any
from datetime import datetime
import websockets
from websockets.server import WebSocketServerProtocol

from .clipboard_monitor import ClipboardItem
from .config import config


class ClipboardServer:
    """
    WebSocket server for clipboard synchronization.
    Broadcasts clipboard changes to all connected clients.
    """
    
    def __init__(
        self,
        port: int = 2580,
        on_log: Optional[Callable[[str], None]] = None,
        on_client_change: Optional[Callable[[int], None]] = None,
        on_clipboard_received: Optional[Callable[[ClipboardItem], None]] = None
    ):
        self.port = port
        self.on_log = on_log or (lambda x: None)
        self.on_client_change = on_client_change or (lambda x: None)
        self.on_clipboard_received = on_clipboard_received or (lambda x: None)
        
        self._clients: Set[WebSocketServerProtocol] = set()
        self._server = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._last_hash = ""
    
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
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self._clients.discard(websocket)
            self._log(f"Client disconnected: {client_addr} (Total: {len(self._clients)})")
            self.on_client_change(len(self._clients))
    
    async def _handle_message(self, websocket: WebSocketServerProtocol, message: str):
        """Handle incoming message from client"""
        try:
            data = json.loads(message)
            msg_type = data.get('type')
            
            if msg_type == 'clipboard':
                content = data.get('content', '')
                content_hash = hashlib.md5(content.encode()).hexdigest()
                
                # Avoid echo
                if content_hash == self._last_hash:
                    return
                self._last_hash = content_hash
                
                # Create clipboard item
                item = ClipboardItem.from_content(content, "remote")
                self.on_clipboard_received(item)
                
                # Broadcast to other clients
                await self._broadcast(data, exclude=websocket)
                self._log(f"Synced: {content[:30]}..." if len(content) > 30 else f"Synced: {content}")
            
            elif msg_type == 'ping':
                await websocket.send(json.dumps({'type': 'pong'}))
        
        except json.JSONDecodeError:
            self._log("Invalid JSON received")
    
    async def _broadcast(self, data: Dict[str, Any], exclude: Optional[WebSocketServerProtocol] = None):
        """Broadcast message to all clients"""
        message = json.dumps(data)
        for client in self._clients.copy():
            if client != exclude:
                try:
                    await client.send(message)
                except Exception:
                    self._clients.discard(client)
    
    async def broadcast_clipboard(self, content: str):
        """Broadcast clipboard content to all clients"""
        content_hash = hashlib.md5(content.encode()).hexdigest()
        if content_hash == self._last_hash:
            return
        self._last_hash = content_hash
        
        await self._broadcast({
            'type': 'clipboard',
            'content': content,
            'timestamp': datetime.now().isoformat()
        })
    
    def send_clipboard(self, content: str):
        """Thread-safe method to send clipboard"""
        if self._loop and self._running:
            asyncio.run_coroutine_threadsafe(
                self.broadcast_clipboard(content),
                self._loop
            )
    
    async def _run_server(self):
        """Run the WebSocket server"""
        self._server = await websockets.serve(
            self._handler,
            "0.0.0.0",
            self.port,
            ping_interval=30,
            ping_timeout=10
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

