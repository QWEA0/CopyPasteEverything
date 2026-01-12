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
            on_clear_history=self._clear_history,
            on_cancel_transfer=self._cancel_transfer
        )

        # Track active transfers for UI updates
        self._active_transfers: dict = {}  # transfer_id -> filename
        
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
            on_clipboard_received=self._on_remote_clipboard,
            on_transfer_progress=self._on_transfer_progress
        )
        self._server.start()

        # Start clipboard monitor
        self._monitor.start()

        # Show local URL immediately
        local_url = f"ws://localhost:{config.server_port}"
        self._window.after(0, lambda: self._window.set_server_running(True, local_url))
        self._log(f"Server running at {local_url}")

        # Start tunnel in background if enabled
        if config.tunnel_enabled:
            import threading
            threading.Thread(target=self._start_tunnel_async, daemon=True).start()

    def _start_tunnel_async(self):
        """Start tunnel in background and update UI when ready"""
        import time
        self._log("[TUNNEL] Establishing public tunnel...")
        self._tunnel = TunnelManager(
            local_port=config.server_port,
            on_status=self._log
        )

        # Start tunnel (non-blocking)
        self._tunnel.start()

        # Poll for tunnel info
        for _ in range(60):  # Wait up to 30 seconds
            if not self._server:  # Server stopped
                return
            tunnel_info = self._tunnel.info
            if tunnel_info and "trycloudflare.com" in tunnel_info.public_url:
                # Update UI with tunnel URL
                url = tunnel_info.public_url
                self._window.after(0, lambda u=url: self._window.set_server_running(True, u))
                self._log(f"✓ Public URL: {url}")
                return
            time.sleep(0.5)

        self._log("[TUNNEL] Tunnel not ready, using local address only")

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
        # If client exists but stopped, clean it up first
        if self._client:
            if not self._client._running:
                self._client = None
            else:
                # Client is still running, don't create another
                return

        self._log(f"Connecting to {url}...")

        # Show connecting state
        self._window.after(0, lambda: self._window.set_client_connecting())

        self._client = ClipboardClient(
            server_url=url,
            on_log=self._log,
            on_clipboard_received=self._on_remote_clipboard,
            on_connected=self._on_client_connection_change,
            on_reconnecting=self._on_client_reconnecting,
            on_transfer_progress=self._on_transfer_progress
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
        """Handle local clipboard change (supports text, image, files)"""
        # Add to history
        if config.history_enabled:
            self._history.add(item)
            self._refresh_history()

        # Send to server/clients using new item-based methods
        if self._server:
            self._server.send_clipboard_item(item)
            self._window.after(0, lambda: self._window.show_sync_activity())
        elif self._client and self._client.is_connected:
            self._client.send_clipboard_item(item)
            self._window.after(0, lambda: self._window.show_sync_activity())

    def _on_remote_clipboard(self, item: ClipboardItem):
        """Handle remote clipboard received (supports text, image, files)"""
        from .clipboard_monitor import ContentType

        # Log what we received
        if item.content_type == ContentType.FILES:
            self._log(f"Received files: {item.file_paths}")
        elif item.content_type == ContentType.IMAGE:
            self._log(f"Received image: {len(item.image_data)} bytes")

        # Update local clipboard using new set_item method
        try:
            self._log(f"Setting clipboard for type: {item.content_type.value}")
            self._monitor.set_item(item)
            self._log("Clipboard set successfully")
        except Exception as e:
            self._log(f"Failed to set clipboard: {e}")

        # Show sync activity
        self._window.after(0, lambda: self._window.show_sync_activity())

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

        # If disconnected and client stopped, clean up so user can reconnect
        if not connected and self._client and not self._client._running:
            self._client = None
            self._monitor.stop()

    def _on_client_reconnecting(self):
        """Handle client reconnecting state"""
        self._window.after(0, lambda: self._window.set_client_reconnecting())

    def _on_transfer_progress(self, transfer_id: str, progress: float):
        """Handle transfer progress update"""
        # Add transfer to UI if not exists
        if transfer_id not in self._active_transfers:
            # Get filename from server or client transfer manager
            filename = "File transfer"
            if self._server and hasattr(self._server, '_transfer_manager'):
                status = self._server._transfer_manager.get_transfer_status(transfer_id)
                if status:
                    filename = status.get('filename', 'File transfer')
            elif self._client and hasattr(self._client, '_transfer_manager'):
                status = self._client._transfer_manager.get_transfer_status(transfer_id)
                if status:
                    filename = status.get('filename', 'File transfer')

            self._active_transfers[transfer_id] = filename
            self._window.after(0, lambda: self._window.add_transfer(transfer_id, filename))

        # Update progress
        self._window.after(0, lambda: self._window.update_transfer_progress(transfer_id, progress))

        # Check if complete
        if progress >= 100:
            self._active_transfers.pop(transfer_id, None)
            self._window.after(0, lambda: self._window.complete_transfer(transfer_id))

    def _cancel_transfer(self, transfer_id: str):
        """Cancel a file transfer"""
        cancelled = False
        if self._server and hasattr(self._server, '_transfer_manager'):
            cancelled = self._server._transfer_manager.cancel_transfer(transfer_id)
        elif self._client and hasattr(self._client, '_transfer_manager'):
            cancelled = self._client._transfer_manager.cancel_transfer(transfer_id)

        if cancelled:
            self._active_transfers.pop(transfer_id, None)
            self._window.after(0, lambda: self._window.fail_transfer(transfer_id, "Cancelled"))
            self._log(f"Transfer cancelled: {transfer_id[:8]}...")

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
