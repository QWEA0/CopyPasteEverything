# -*- coding: utf-8 -*-
"""
components.py - Custom UI components with geek/terminal styling
Reusable widgets for the clipboard sync application
"""

import customtkinter as ctk
from typing import Callable, Optional
from .theme import theme


class TerminalLog(ctk.CTkTextbox):
    """Terminal-style log display widget"""

    def __init__(self, master, **kwargs):
        super().__init__(
            master,
            fg_color=theme.bg_dark,
            text_color=theme.accent_green,
            font=(theme.font_mono, theme.font_size_normal),
            border_width=1,
            border_color=theme.border_default,
            corner_radius=theme.corner_radius,
            **kwargs
        )
        self.configure(state="disabled")
        self._line_count = 0
        self._max_lines = 500

    def append(self, text: str, color: str = None):
        """Append text to the log"""
        self.configure(state="normal")

        # Add newline if not first line
        if self._line_count > 0:
            self.insert("end", "\n")

        # Insert text
        self.insert("end", f"❯ {text}")
        self._line_count += 1

        # Trim old lines
        if self._line_count > self._max_lines:
            self.delete("1.0", "2.0")
            self._line_count -= 1

        self.configure(state="disabled")
        self.see("end")

    def clear(self):
        """Clear the log"""
        self.configure(state="normal")
        self.delete("1.0", "end")
        self._line_count = 0
        self.configure(state="disabled")


class StatusIndicator(ctk.CTkFrame):
    """Status indicator with pulsing dot and label"""

    def __init__(self, master, label: str = "Status", **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)

        self._dot = ctk.CTkLabel(
            self,
            text="●",
            font=(theme.font_mono, 14),
            text_color=theme.text_muted,
            width=20
        )
        self._dot.pack(side="left", padx=(0, 5))

        self._label = ctk.CTkLabel(
            self,
            text=label,
            font=(theme.font_mono, theme.font_size_normal),
            text_color=theme.text_secondary
        )
        self._label.pack(side="left")

        self._status = "offline"
        self._blinking = False

    def set_status(self, status: str, label: str = None):
        """Update status indicator"""
        colors = {
            "online": theme.accent_green,
            "offline": theme.accent_red,
            "connecting": theme.accent_orange,
            "syncing": theme.accent_cyan,
            "waiting": theme.accent_purple
        }
        self._status = status
        self._dot.configure(text_color=colors.get(status, theme.text_muted))
        if label:
            self._label.configure(text=label)

        # Start/stop blinking for connecting state
        if status == "connecting" and not self._blinking:
            self._blinking = True
            self._blink()
        elif status != "connecting":
            self._blinking = False

    def _blink(self):
        """Blink animation for connecting state"""
        if not self._blinking:
            return
        current = self._dot.cget("text")
        self._dot.configure(text="○" if current == "●" else "●")
        self.after(500, self._blink)


class GlowButton(ctk.CTkButton):
    """Button with glow/neon effect styling"""

    def __init__(self, master, text: str, accent: str = None, **kwargs):
        accent = accent or theme.accent_green
        super().__init__(
            master,
            text=text,
            font=(theme.font_mono, theme.font_size_normal, "bold"),
            fg_color="transparent",
            hover_color=theme.bg_hover,
            border_width=1,
            border_color=accent,
            text_color=accent,
            corner_radius=theme.corner_radius,
            **kwargs
        )


class ClipboardCard(ctk.CTkFrame):
    """Card displaying clipboard history item"""

    def __init__(self, master, content: str, timestamp: str, source: str,
                 on_copy: Callable[[], None] = None, on_delete: Callable[[], None] = None, **kwargs):
        super().__init__(
            master,
            fg_color=theme.bg_light,
            border_width=1,
            border_color=theme.border_default,
            corner_radius=theme.corner_radius,
            **kwargs
        )

        # Header with timestamp and source
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=(8, 4))

        source_color = theme.accent_cyan if source == "remote" else theme.accent_green
        ctk.CTkLabel(
            header,
            text=f"[{source.upper()}]",
            font=(theme.font_mono, theme.font_size_small),
            text_color=source_color
        ).pack(side="left")

        ctk.CTkLabel(
            header,
            text=timestamp,
            font=(theme.font_mono, theme.font_size_small),
            text_color=theme.text_muted
        ).pack(side="right")

        # Content preview
        preview = content[:100] + "..." if len(content) > 100 else content
        preview = preview.replace("\n", " ↵ ")

        ctk.CTkLabel(
            self,
            text=preview,
            font=(theme.font_mono, theme.font_size_normal),
            text_color=theme.text_primary,
            anchor="w",
            justify="left"
        ).pack(fill="x", padx=10, pady=(0, 4))

        # Actions
        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.pack(fill="x", padx=10, pady=(0, 8))

        if on_copy:
            GlowButton(
                actions, text="COPY", width=60, height=24,
                command=on_copy
            ).pack(side="left", padx=(0, 5))

        if on_delete:
            GlowButton(
                actions, text="DEL", width=50, height=24,
                accent=theme.accent_red, command=on_delete
            ).pack(side="left")




class TransferProgressBar(ctk.CTkFrame):
    """Progress bar for file transfers with filename and percentage"""

    def __init__(self, master, transfer_id: str, filename: str,
                 on_cancel: Optional[Callable[[str], None]] = None, **kwargs):
        super().__init__(
            master,
            fg_color=theme.bg_light,
            border_width=1,
            border_color=theme.border_default,
            corner_radius=theme.corner_radius,
            height=50,
            **kwargs
        )
        self.pack_propagate(False)

        self.transfer_id = transfer_id
        self.filename = filename
        self._on_cancel = on_cancel

        # Main content frame
        content = ctk.CTkFrame(self, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=10, pady=8)

        # Top row: filename and percentage
        top_row = ctk.CTkFrame(content, fg_color="transparent")
        top_row.pack(fill="x")

        # Direction indicator + filename
        display_name = filename if len(filename) <= 30 else f"...{filename[-27:]}"
        self._filename_label = ctk.CTkLabel(
            top_row,
            text=f"📁 {display_name}",
            font=(theme.font_mono, theme.font_size_small),
            text_color=theme.text_primary,
            anchor="w"
        )
        self._filename_label.pack(side="left")

        # Percentage label
        self._percent_label = ctk.CTkLabel(
            top_row,
            text="0%",
            font=(theme.font_mono, theme.font_size_small, "bold"),
            text_color=theme.accent_cyan,
            width=50
        )
        self._percent_label.pack(side="right")

        # Cancel button (small X)
        if on_cancel:
            cancel_btn = ctk.CTkButton(
                top_row,
                text="✖",
                width=20,
                height=20,
                font=(theme.font_mono, 10),
                fg_color="transparent",
                hover_color=theme.bg_hover,
                text_color=theme.accent_red,
                command=lambda: on_cancel(transfer_id)
            )
            cancel_btn.pack(side="right", padx=(0, 5))

        # Progress bar
        self._progress_bar = ctk.CTkProgressBar(
            content,
            fg_color=theme.bg_dark,
            progress_color=theme.accent_cyan,
            height=8,
            corner_radius=4
        )
        self._progress_bar.pack(fill="x", pady=(5, 0))
        self._progress_bar.set(0)

    def set_progress(self, progress: float):
        """Update progress (0-100)"""
        self._progress_bar.set(progress / 100)
        self._percent_label.configure(text=f"{progress:.0f}%")

        # Change color based on progress
        if progress >= 100:
            self._progress_bar.configure(progress_color=theme.accent_green)
            self._percent_label.configure(text_color=theme.accent_green)

    def set_complete(self):
        """Mark transfer as complete"""
        self.set_progress(100)
        self._filename_label.configure(text=f"✓ {self.filename}")

    def set_error(self, error: str = "Failed"):
        """Mark transfer as failed"""
        self._progress_bar.configure(progress_color=theme.accent_red)
        self._percent_label.configure(text="ERR", text_color=theme.accent_red)
        self._filename_label.configure(text=f"✖ {self.filename}")


class TransferPanel(ctk.CTkFrame):
    """Panel showing all active file transfers"""

    def __init__(self, master, on_cancel: Optional[Callable[[str], None]] = None, **kwargs):
        super().__init__(
            master,
            fg_color=theme.bg_medium,
            corner_radius=theme.corner_radius,
            **kwargs
        )

        self._on_cancel = on_cancel
        self._transfers: dict = {}  # transfer_id -> TransferProgressBar

        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=(8, 5))

        self._header_label = ctk.CTkLabel(
            header,
            text="📤 TRANSFERS",
            font=(theme.font_mono, theme.font_size_small, "bold"),
            text_color=theme.accent_cyan
        )
        self._header_label.pack(side="left")

        self._count_label = ctk.CTkLabel(
            header,
            text="",
            font=(theme.font_mono, theme.font_size_small),
            text_color=theme.text_muted
        )
        self._count_label.pack(side="right")

        # Scrollable container for transfers
        self._container = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
            height=100
        )
        self._container.pack(fill="both", expand=True, padx=5, pady=(0, 5))

        # Initially hidden
        self.pack_forget()
        self._visible = False

    def add_transfer(self, transfer_id: str, filename: str, direction: str = "upload"):
        """Add a new transfer to the panel"""
        if transfer_id in self._transfers:
            return

        progress_bar = TransferProgressBar(
            self._container,
            transfer_id=transfer_id,
            filename=filename,
            on_cancel=self._on_cancel
        )
        progress_bar.pack(fill="x", pady=2)

        self._transfers[transfer_id] = progress_bar
        self._update_count()
        self._show()

    def update_progress(self, transfer_id: str, progress: float):
        """Update progress for a transfer"""
        if transfer_id in self._transfers:
            self._transfers[transfer_id].set_progress(progress)

    def complete_transfer(self, transfer_id: str):
        """Mark transfer as complete and remove after delay"""
        if transfer_id in self._transfers:
            self._transfers[transfer_id].set_complete()
            # Remove after 2 seconds
            self.after(2000, lambda: self._remove_transfer(transfer_id))

    def fail_transfer(self, transfer_id: str, error: str = "Failed"):
        """Mark transfer as failed"""
        if transfer_id in self._transfers:
            self._transfers[transfer_id].set_error(error)
            # Remove after 3 seconds
            self.after(3000, lambda: self._remove_transfer(transfer_id))

    def _remove_transfer(self, transfer_id: str):
        """Remove a transfer from the panel"""
        if transfer_id in self._transfers:
            self._transfers[transfer_id].destroy()
            del self._transfers[transfer_id]
            self._update_count()

            if not self._transfers:
                self._hide()

    def _update_count(self):
        """Update the transfer count label"""
        count = len(self._transfers)
        self._count_label.configure(text=f"({count} active)" if count > 0 else "")

    def _show(self):
        """Show the panel"""
        if not self._visible:
            self.pack(fill="x", padx=10, pady=5, before=self.master.winfo_children()[0]
                      if self.master.winfo_children() else None)
            self._visible = True

    def _hide(self):
        """Hide the panel"""
        if self._visible:
            self.pack_forget()
            self._visible = False
