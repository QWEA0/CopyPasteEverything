# -*- coding: utf-8 -*-
"""
theme.py - Geek/Hacker style theme configuration
Defines colors, fonts, and styling for the terminal-like UI
"""

from dataclasses import dataclass
from typing import Tuple


@dataclass
class GeekTheme:
    """Geek/Hacker terminal-style theme"""
    
    # Main colors - Matrix/Terminal inspired
    bg_dark: str = "#0a0e14"          # Deep dark background
    bg_medium: str = "#0d1117"         # Medium background
    bg_light: str = "#161b22"          # Lighter background for cards
    bg_hover: str = "#21262d"          # Hover state
    
    # Accent colors - Neon/Cyber
    accent_green: str = "#00ff9f"      # Matrix green
    accent_cyan: str = "#00d4ff"       # Cyber cyan  
    accent_purple: str = "#bd00ff"     # Neon purple
    accent_orange: str = "#ff9f00"     # Warning orange
    accent_red: str = "#ff0050"        # Error red
    
    # Text colors
    text_primary: str = "#e6edf3"      # Primary text
    text_secondary: str = "#8b949e"    # Secondary text
    text_muted: str = "#484f58"        # Muted text
    
    # Border colors
    border_default: str = "#30363d"
    border_active: str = "#00ff9f"
    
    # Fonts
    font_mono: str = "Consolas"
    font_mono_alt: str = "JetBrains Mono"
    font_size_small: int = 10
    font_size_normal: int = 12
    font_size_large: int = 14
    font_size_title: int = 18
    
    # Dimensions
    corner_radius: int = 8
    padding: int = 12
    
    # Terminal prompt style
    prompt_symbol: str = "❯"
    cursor_symbol: str = "█"


# Global theme instance
theme = GeekTheme()


# CustomTkinter color configurations
CTK_COLORS = {
    "CTkFrame": {
        "fg_color": theme.bg_medium,
        "border_color": theme.border_default
    },
    "CTkButton": {
        "fg_color": theme.bg_light,
        "hover_color": theme.bg_hover,
        "border_color": theme.accent_green,
        "text_color": theme.accent_green
    },
    "CTkEntry": {
        "fg_color": theme.bg_dark,
        "border_color": theme.border_default,
        "text_color": theme.text_primary
    },
    "CTkLabel": {
        "text_color": theme.text_primary
    },
    "CTkTextbox": {
        "fg_color": theme.bg_dark,
        "border_color": theme.border_default,
        "text_color": theme.accent_green
    }
}


def get_status_color(status: str) -> str:
    """Get color for status indicator"""
    status_colors = {
        "connected": theme.accent_green,
        "disconnected": theme.accent_red,
        "connecting": theme.accent_orange,
        "syncing": theme.accent_cyan,
        "idle": theme.text_muted
    }
    return status_colors.get(status, theme.text_muted)


def format_terminal_line(prefix: str, message: str, color: str = None) -> Tuple[str, str]:
    """Format a line for terminal-style display"""
    timestamp = ""  # Can add timestamp if needed
    line = f"{theme.prompt_symbol} [{prefix}] {message}"
    return line, color or theme.text_secondary

