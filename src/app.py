# -*- coding: utf-8 -*-
"""
app.py - Main application controller for CopyPasteEverything
Coordinates all components: UI, clipboard monitor, server/client, history
"""

import threading
from typing import Optional

from .config import config
from .clipboard_monitor import ClipboardMonitor, ClipboardItem
from .history import HistoryManager
from .server import ClipboardServer
from .client import ClipboardClient
from .tunnel import TunnelManager
from .ui.main_window import MainWindow


class ClipboardSyncApp:
    """
    Main application controller.
    Manages all components and their interactions.
    """
    
    def __init__(self):
        # Components
        self._history = HistoryManager(max_items=config.max_history_items)
        self._server: Optional[ClipboardServer] = None
        self._client: Optional[ClipboardClient] = None
        self._tunnel: Optional[TunnelManager] = None
        self._monitor: Optional[ClipboardMonitor] = None
        
        # Create UI with callbacks
        self._window = MainWindow(
            on_start_server=self._start_server,
            on_stop_server=self._stop_server,
            on_connect=self._connect_to_server,
            on_disconnect=self._disconnect,
            on_copy_item=self._copy_from_history,
            on_delete_item=self._delete_history_item,
            on_clear_history=self._clear_history
        )
        
        # Initialize clipboard monitor
        self._monitor = ClipboardMonitor(
            on_change=self._on_local_clipboard_change,
            interval_ms=config.sync_interval_ms
        )
        
        # Load initial history
        self._refresh_history()
        self._log("System initialized")
    
    def _log(self, message: str):
        """Thread-safe logging to UI"""
        self._window.after(0, lambda: self._window.log(message))
    
    def _start_server(self):
        """Start server mode"""
        if self._server:
            return
        
        self._log("Starting server...")
        
        # Create and start server
        self._server = ClipboardServer(
            port=config.server_port,
            on_log=self._log,
            on_client_change=self._on_client_count_change,
            on_clipboard_received=self._on_remote_clipboard
        )
        self._server.start()
        
        # Start tunnel if enabled
        url = f"ws://localhost:{config.server_port}"
        if config.tunnel_enabled:
            self._tunnel = TunnelManager(
                local_port=config.server_port,
                on_status=self._log
            )
            tunnel_info = self._tunnel.start()
            if tunnel_info:
                url = tunnel_info.public_url
        
        # Start clipboard monitor
        self._monitor.start()
        
        # Update UI
        self._window.after(0, lambda: self._window.set_server_running(True, url))
        self._log(f"Server running at {url}")
    
    def _stop_server(self):
        """Stop server mode"""
        if self._server:
            self._server.stop()
            self._server = None
        
        if self._tunnel:
            self._tunnel.stop()
            self._tunnel = None
        
        self._monitor.stop()
        
        self._window.after(0, lambda: self._window.set_server_running(False))
        self._log("Server stopped")
    
    def _connect_to_server(self, url: str):
        """Connect to remote server"""
        if self._client:
            return
        
        self._log(f"Connecting to {url}...")
        
        self._client = ClipboardClient(
            server_url=url,
            on_log=self._log,
            on_clipboard_received=self._on_remote_clipboard,
            on_connected=self._on_client_connection_change
        )
        self._client.start()
        
        # Start clipboard monitor
        self._monitor.start()
    
    def _disconnect(self):
        """Disconnect from server"""
        if self._client:
            self._client.stop()
            self._client = None
        
        self._monitor.stop()
        
        self._window.after(0, lambda: self._window.set_client_connected(False))
        self._log("Disconnected")
    
    def _on_local_clipboard_change(self, item: ClipboardItem):
        """Handle local clipboard change"""
        # Add to history
        if config.history_enabled:
            self._history.add(item)
            self._refresh_history()
        
        # Send to server/clients
        if self._server:
            self._server.send_clipboard(item.content)
        elif self._client and self._client.is_connected:
            self._client.send_clipboard(item.content)
    
    def _on_remote_clipboard(self, item: ClipboardItem):
        """Handle remote clipboard received"""
        # Update local clipboard
        self._monitor.set_content(item.content)
        
        # Add to history
        if config.history_enabled:
            self._history.add(item)
            self._refresh_history()
    
    def _on_client_count_change(self, count: int):
        """Handle client count change"""
        self._window.after(0, lambda: self._window.set_client_count(count))
    
    def _on_client_connection_change(self, connected: bool):
        """Handle client connection state change"""
        self._window.after(0, lambda: self._window.set_client_connected(connected))

    def _copy_from_history(self, content: str):
        """Copy item from history to clipboard"""
        self._monitor.set_content(content)

    def _delete_history_item(self, content_hash: str):
        """Delete item from history"""
        self._history.delete(content_hash)
        self._refresh_history()

    def _clear_history(self):
        """Clear all history"""
        self._history.clear()
        self._refresh_history()
        self._log("History cleared")

    def _refresh_history(self):
        """Refresh history display"""
        items = self._history.get_all(limit=50)
        self._window.after(0, lambda: self._window.update_history(items))

    def run(self):
        """Run the application"""
        self._log("CopyPasteEverything ready")
        self._window.mainloop()

        # Cleanup on exit
        self._stop_server()
        self._disconnect()


def main():
    """Application entry point"""
    app = ClipboardSyncApp()
    app.run()


if __name__ == "__main__":
    main()
