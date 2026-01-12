# -*- coding: utf-8 -*-
"""
main_window.py - Main application window with geek/terminal styling
Provides the primary UI for clipboard synchronization
"""

import customtkinter as ctk
from typing import Callable, Optional
import pyperclip

from .theme import theme
from .components import TerminalLog, StatusIndicator, GlowButton, ClipboardCard


class MainWindow(ctk.CTk):
    """Main application window with tabbed interface"""
    
    def __init__(
        self,
        on_start_server: Callable[[], None] = None,
        on_stop_server: Callable[[], None] = None,
        on_connect: Callable[[str], None] = None,
        on_disconnect: Callable[[], None] = None,
        on_copy_item: Callable[[str], None] = None,
        on_delete_item: Callable[[str], None] = None,
        on_clear_history: Callable[[], None] = None
    ):
        super().__init__()
        
        # Callbacks
        self._on_start_server = on_start_server or (lambda: None)
        self._on_stop_server = on_stop_server or (lambda: None)
        self._on_connect = on_connect or (lambda x: None)
        self._on_disconnect = on_disconnect or (lambda: None)
        self._on_copy_item = on_copy_item or (lambda x: None)
        self._on_delete_item = on_delete_item or (lambda x: None)
        self._on_clear_history = on_clear_history or (lambda: None)
        
        # Window setup
        self.title("CopyPasteEverything")
        self.geometry("700x550")
        self.minsize(600, 450)
        
        # Configure appearance
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")
        self.configure(fg_color=theme.bg_dark)
        
        # Build UI
        self._create_header()
        self._create_tabs()
        self._create_footer()
        
        # State
        self._server_running = False
        self._client_connected = False
        self._client_connecting = False  # True when connecting or reconnecting
    
    def _create_header(self):
        """Create header with title and status"""
        header = ctk.CTkFrame(self, fg_color=theme.bg_medium, height=60)
        header.pack(fill="x", padx=0, pady=0)
        header.pack_propagate(False)
        
        # ASCII art title
        title = ctk.CTkLabel(
            header,
            text="⚡ COPY.PASTE.EVERYTHING",
            font=(theme.font_mono, theme.font_size_title, "bold"),
            text_color=theme.accent_green
        )
        title.pack(side="left", padx=20, pady=15)
        
        # Status indicators
        status_frame = ctk.CTkFrame(header, fg_color="transparent")
        status_frame.pack(side="right", padx=20)

        self._tunnel_status = StatusIndicator(status_frame, "Tunnel: -")
        self._tunnel_status.pack(side="left", padx=(0, 15))

        self._server_status = StatusIndicator(status_frame, "Server: OFF")
        self._server_status.pack(side="left", padx=(0, 15))

        self._client_status = StatusIndicator(status_frame, "Client: OFF")
        self._client_status.pack(side="left")
    
    def _create_tabs(self):
        """Create tabbed interface"""
        self._tabview = ctk.CTkTabview(
            self,
            fg_color=theme.bg_medium,
            segmented_button_fg_color=theme.bg_dark,
            segmented_button_selected_color=theme.accent_green,
            segmented_button_selected_hover_color=theme.accent_green,
            segmented_button_unselected_color=theme.bg_light,
            segmented_button_unselected_hover_color=theme.bg_hover,
            text_color=theme.bg_dark,
            corner_radius=theme.corner_radius
        )
        self._tabview.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Create tabs
        self._tabview.add("  SERVER  ")
        self._tabview.add("  CLIENT  ")
        self._tabview.add("  HISTORY  ")
        self._tabview.add("  LOGS  ")
        
        self._create_server_tab()
        self._create_client_tab()
        self._create_history_tab()
        self._create_logs_tab()
    
    def _create_server_tab(self):
        """Create server control tab"""
        tab = self._tabview.tab("  SERVER  ")
        
        # Server info frame
        info_frame = ctk.CTkFrame(tab, fg_color=theme.bg_light)
        info_frame.pack(fill="x", padx=10, pady=10)
        
        ctk.CTkLabel(
            info_frame,
            text="// SERVER MODE",
            font=(theme.font_mono, theme.font_size_large, "bold"),
            text_color=theme.accent_cyan
        ).pack(anchor="w", padx=15, pady=(15, 5))
        
        ctk.CTkLabel(
            info_frame,
            text="Start a server to sync clipboard with connected clients",
            font=(theme.font_mono, theme.font_size_small),
            text_color=theme.text_secondary
        ).pack(anchor="w", padx=15, pady=(0, 15))
        
        # Connection URL display
        url_frame = ctk.CTkFrame(tab, fg_color=theme.bg_light)
        url_frame.pack(fill="x", padx=10, pady=5)
        
        ctk.CTkLabel(
            url_frame,
            text="CONNECTION URL:",
            font=(theme.font_mono, theme.font_size_small),
            text_color=theme.text_muted
        ).pack(anchor="w", padx=15, pady=(10, 5))
        
        self._server_url_var = ctk.StringVar(value="Not running")
        self._server_url_entry = ctk.CTkEntry(
            url_frame,
            textvariable=self._server_url_var,
            font=(theme.font_mono, theme.font_size_normal),
            fg_color=theme.bg_dark,
            text_color=theme.accent_green,
            border_color=theme.border_default,
            state="readonly",
            width=400
        )
        self._server_url_entry.pack(anchor="w", padx=15, pady=(0, 5))
        
        GlowButton(
            url_frame, text="📋 COPY URL", width=120,
            command=self._copy_server_url
        ).pack(anchor="w", padx=15, pady=(0, 15))
        
        # Status panel
        status_panel = ctk.CTkFrame(tab, fg_color=theme.bg_light)
        status_panel.pack(fill="x", padx=10, pady=5)

        ctk.CTkLabel(
            status_panel,
            text="STATUS:",
            font=(theme.font_mono, theme.font_size_small),
            text_color=theme.text_muted
        ).pack(anchor="w", padx=15, pady=(10, 5))

        status_row = ctk.CTkFrame(status_panel, fg_color="transparent")
        status_row.pack(fill="x", padx=15, pady=(0, 10))

        self._server_detail_status = StatusIndicator(status_row, "Server: Stopped")
        self._server_detail_status.pack(side="left", padx=(0, 20))

        self._tunnel_detail_status = StatusIndicator(status_row, "Tunnel: Not active")
        self._tunnel_detail_status.pack(side="left", padx=(0, 20))

        self._clients_label = ctk.CTkLabel(
            status_row,
            text="👥 0 clients",
            font=(theme.font_mono, theme.font_size_normal),
            text_color=theme.text_secondary
        )
        self._clients_label.pack(side="left")

        # Controls
        controls = ctk.CTkFrame(tab, fg_color="transparent")
        controls.pack(fill="x", padx=10, pady=15)

        self._start_server_btn = GlowButton(
            controls, text="▶ START SERVER", width=160, height=40,
            command=self._toggle_server
        )
        self._start_server_btn.pack(side="left", padx=5)

    def _create_client_tab(self):
        """Create client control tab"""
        tab = self._tabview.tab("  CLIENT  ")

        # Client info
        info_frame = ctk.CTkFrame(tab, fg_color=theme.bg_light)
        info_frame.pack(fill="x", padx=10, pady=10)

        ctk.CTkLabel(
            info_frame,
            text="// CLIENT MODE",
            font=(theme.font_mono, theme.font_size_large, "bold"),
            text_color=theme.accent_purple
        ).pack(anchor="w", padx=15, pady=(15, 5))

        ctk.CTkLabel(
            info_frame,
            text="Connect to a server to sync clipboard",
            font=(theme.font_mono, theme.font_size_small),
            text_color=theme.text_secondary
        ).pack(anchor="w", padx=15, pady=(0, 15))

        # Server URL input
        url_frame = ctk.CTkFrame(tab, fg_color=theme.bg_light)
        url_frame.pack(fill="x", padx=10, pady=5)

        ctk.CTkLabel(
            url_frame,
            text="SERVER URL:",
            font=(theme.font_mono, theme.font_size_small),
            text_color=theme.text_muted
        ).pack(anchor="w", padx=15, pady=(10, 5))

        self._client_url_var = ctk.StringVar(value="ws://")
        self._client_url_entry = ctk.CTkEntry(
            url_frame,
            textvariable=self._client_url_var,
            font=(theme.font_mono, theme.font_size_normal),
            fg_color=theme.bg_dark,
            text_color=theme.accent_green,
            border_color=theme.border_default,
            width=400,
            placeholder_text="ws://hostname:2580"
        )
        self._client_url_entry.pack(anchor="w", padx=15, pady=(0, 15))

        # Status panel
        status_panel = ctk.CTkFrame(tab, fg_color=theme.bg_light)
        status_panel.pack(fill="x", padx=10, pady=5)

        ctk.CTkLabel(
            status_panel,
            text="STATUS:",
            font=(theme.font_mono, theme.font_size_small),
            text_color=theme.text_muted
        ).pack(anchor="w", padx=15, pady=(10, 5))

        status_row = ctk.CTkFrame(status_panel, fg_color="transparent")
        status_row.pack(fill="x", padx=15, pady=(0, 10))

        self._client_detail_status = StatusIndicator(status_row, "Connection: Not connected")
        self._client_detail_status.pack(side="left", padx=(0, 20))

        self._sync_status = StatusIndicator(status_row, "Sync: Idle")
        self._sync_status.pack(side="left")

        # Controls
        controls = ctk.CTkFrame(tab, fg_color="transparent")
        controls.pack(fill="x", padx=10, pady=15)

        self._connect_btn = GlowButton(
            controls, text="🔗 CONNECT", width=160, height=40,
            accent=theme.accent_purple,
            command=self._toggle_client
        )
        self._connect_btn.pack(side="left", padx=5)

    def _create_history_tab(self):
        """Create history tab"""
        tab = self._tabview.tab("  HISTORY  ")

        # Header
        header = ctk.CTkFrame(tab, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=10)

        ctk.CTkLabel(
            header,
            text="// CLIPBOARD HISTORY",
            font=(theme.font_mono, theme.font_size_large, "bold"),
            text_color=theme.accent_orange
        ).pack(side="left")

        GlowButton(
            header, text="🗑 CLEAR ALL", width=100,
            accent=theme.accent_red,
            command=self._on_clear_history
        ).pack(side="right")

        # Scrollable history list
        self._history_frame = ctk.CTkScrollableFrame(
            tab,
            fg_color=theme.bg_dark,
            corner_radius=theme.corner_radius
        )
        self._history_frame.pack(fill="both", expand=True, padx=10, pady=5)

        self._history_cards = []

    def _create_logs_tab(self):
        """Create logs tab"""
        tab = self._tabview.tab("  LOGS  ")

        # Header
        header = ctk.CTkFrame(tab, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=10)

        ctk.CTkLabel(
            header,
            text="// SYSTEM LOGS",
            font=(theme.font_mono, theme.font_size_large, "bold"),
            text_color=theme.text_secondary
        ).pack(side="left")

        GlowButton(
            header, text="CLEAR", width=80,
            command=lambda: self._log_display.clear()
        ).pack(side="right")

        # Log display
        self._log_display = TerminalLog(tab)
        self._log_display.pack(fill="both", expand=True, padx=10, pady=5)

    def _create_footer(self):
        """Create footer with version info"""
        footer = ctk.CTkFrame(self, fg_color=theme.bg_medium, height=30)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)

        ctk.CTkLabel(
            footer,
            text="v1.0.0 | Lightweight Clipboard Sync",
            font=(theme.font_mono, theme.font_size_small),
            text_color=theme.text_muted
        ).pack(side="left", padx=15, pady=5)

    def _copy_server_url(self):
        """Copy server URL to clipboard"""
        url = self._server_url_var.get()
        if url and url != "Not running":
            pyperclip.copy(url)
            self.log("URL copied to clipboard")

    def _toggle_server(self):
        """Toggle server state"""
        if self._server_running:
            self._on_stop_server()
        else:
            self._on_start_server()

    def _toggle_client(self):
        """Toggle client state"""
        if self._client_connected or self._client_connecting:
            # Disconnect if connected or cancel if connecting/reconnecting
            self._on_disconnect()
        else:
            url = self._client_url_var.get()
            if url and url != "ws://":
                self._on_connect(url)

    # Public methods for updating UI state
    def log(self, message: str):
        """Add message to log display"""
        self._log_display.append(message)

    def set_server_running(self, running: bool, url: str = ""):
        """Update server status"""
        self._server_running = running
        if running:
            self._server_status.set_status("online", "Server: ON")
            self._server_detail_status.set_status("online", "Server: Running")
            self._start_server_btn.configure(text="■ STOP SERVER")
            if url:
                self._server_url_var.set(url)
                # Update tunnel status based on URL
                if "trycloudflare.com" in url:
                    self._tunnel_status.set_status("online", "Tunnel: ON")
                    self._tunnel_detail_status.set_status("online", "Tunnel: Connected")
                elif "localhost" in url or "127.0.0.1" in url:
                    self._tunnel_status.set_status("connecting", "Tunnel: ...")
                    self._tunnel_detail_status.set_status("connecting", "Tunnel: Connecting...")
                else:
                    self._tunnel_status.set_status("waiting", "Tunnel: LAN")
                    self._tunnel_detail_status.set_status("waiting", "Tunnel: LAN only")
        else:
            self._server_status.set_status("offline", "Server: OFF")
            self._server_detail_status.set_status("offline", "Server: Stopped")
            self._tunnel_status.set_status("offline", "Tunnel: -")
            self._tunnel_detail_status.set_status("offline", "Tunnel: Not active")
            self._start_server_btn.configure(text="▶ START SERVER")
            self._server_url_var.set("Not running")

    def set_tunnel_status(self, status: str, label: str):
        """Update tunnel status indicator"""
        self._tunnel_status.set_status(status, label)
        self._tunnel_detail_status.set_status(status, label)

    def set_client_connected(self, connected: bool):
        """Update client status"""
        self._client_connected = connected
        self._client_connecting = False  # No longer connecting
        if connected:
            self._client_status.set_status("online", "Client: ON")
            self._client_detail_status.set_status("online", "Connection: Connected")
            self._sync_status.set_status("online", "Sync: Ready")
            self._connect_btn.configure(text="✖ DISCONNECT")
        else:
            self._client_status.set_status("offline", "Client: OFF")
            self._client_detail_status.set_status("offline", "Connection: Disconnected")
            self._sync_status.set_status("offline", "Sync: Idle")
            self._connect_btn.configure(text="🔗 CONNECT")

    def set_client_connecting(self):
        """Set client to connecting state"""
        self._client_connecting = True
        self._client_status.set_status("connecting", "Client: ...")
        self._client_detail_status.set_status("connecting", "Connection: Connecting...")
        self._sync_status.set_status("waiting", "Sync: Waiting")
        self._connect_btn.configure(text="✖ CANCEL")

    def set_client_reconnecting(self):
        """Set client to reconnecting state - allows user to cancel"""
        self._client_connected = False
        self._client_connecting = True  # Still trying to connect
        self._client_status.set_status("connecting", "Client: ...")
        self._client_detail_status.set_status("connecting", "Connection: Reconnecting...")
        self._sync_status.set_status("waiting", "Sync: Waiting")
        self._connect_btn.configure(text="✖ CANCEL")

    def show_sync_activity(self):
        """Flash sync indicator to show activity"""
        self._sync_status.set_status("syncing", "Sync: Syncing...")
        # Reset after 1 second
        self.after(1000, lambda: self._sync_status.set_status("online", "Sync: Ready")
                   if self._client_connected else None)

    def set_client_count(self, count: int):
        """Update connected clients count"""
        self._clients_label.configure(text=f"👥 {count} client{'s' if count != 1 else ''}")

    def update_history(self, items: list):
        """Update history display"""
        # Clear existing cards
        for card in self._history_cards:
            card.destroy()
        self._history_cards.clear()

        # Create new cards
        for item in items:
            card = ClipboardCard(
                self._history_frame,
                content=item.content,
                timestamp=item.timestamp.strftime("%H:%M:%S"),
                source=item.source,
                on_copy=lambda c=item.content: self._copy_history_item(c),
                on_delete=lambda h=item.content_hash: self._delete_history_item(h)
            )
            card.pack(fill="x", padx=5, pady=3)
            self._history_cards.append(card)

    def _copy_history_item(self, content: str):
        """Copy history item to clipboard"""
        self._on_copy_item(content)
        self.log("Copied from history")

    def _delete_history_item(self, content_hash: str):
        """Delete history item"""
        self._on_delete_item(content_hash)

