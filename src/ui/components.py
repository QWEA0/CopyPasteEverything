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

