# -*- coding: utf-8 -*-
"""
client.py - WebSocket client for clipboard synchronization
Connects to server and syncs clipboard content bidirectionally
"""

import asyncio
import json
import threading
import hashlib
from typing import Optional, Callable
from datetime import datetime
import websockets
from websockets.client import WebSocketClientProtocol

from .clipboard_monitor import ClipboardItem
from .config import config


class ClipboardClient:
    """
    WebSocket client for clipboard synchronization.
    Connects to a server and syncs clipboard in real-time.
    """
    
    def __init__(
        self,
        server_url: str,
        on_log: Optional[Callable[[str], None]] = None,
        on_clipboard_received: Optional[Callable[[ClipboardItem], None]] = None,
        on_connected: Optional[Callable[[bool], None]] = None
    ):
        self.server_url = server_url
        self.on_log = on_log or (lambda x: None)
        self.on_clipboard_received = on_clipboard_received or (lambda x: None)
        self.on_connected = on_connected or (lambda x: None)
        
        self._websocket: Optional[WebSocketClientProtocol] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._connected = False
        self._last_hash = ""
        self._reconnect_delay = 1
    
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
                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(self._reconnect_delay * 2, 30)
    
    async def _handle_message(self, message: str):
        """Handle incoming message from server"""
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
                
                # Create clipboard item and notify
                item = ClipboardItem.from_content(content, "remote")
                self.on_clipboard_received(item)
                self._log(f"Received: {content[:30]}..." if len(content) > 30 else f"Received: {content}")
            
            elif msg_type == 'pong':
                pass  # Heartbeat response
        
        except json.JSONDecodeError:
            self._log("Invalid JSON received")
    
    async def _send_clipboard(self, content: str):
        """Send clipboard content to server"""
        if not self._websocket or not self._connected:
            return
        
        content_hash = hashlib.md5(content.encode()).hexdigest()
        if content_hash == self._last_hash:
            return
        self._last_hash = content_hash
        
        try:
            await self._websocket.send(json.dumps({
                'type': 'clipboard',
                'content': content,
                'timestamp': datetime.now().isoformat()
            }))
        except Exception as e:
            self._log(f"Send error: {e}")
    
    def send_clipboard(self, content: str):
        """Thread-safe method to send clipboard"""
        if self._loop and self._connected:
            asyncio.run_coroutine_threadsafe(
                self._send_clipboard(content),
                self._loop
            )
    
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

