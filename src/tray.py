# -*- coding: utf-8 -*-
"""
tray.py - System tray icon management
Provides minimize to tray functionality for seamless background operation
"""

import threading
from typing import Callable, Optional
from PIL import Image, ImageDraw
import pystray
from pystray import MenuItem as Item


def create_icon_image(size: int = 64, color: str = "#00ff9f") -> Image.Image:
    """Create a simple clipboard icon"""
    image = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    
    # Draw clipboard shape
    margin = size // 8
    clip_height = size // 6
    
    # Main board
    draw.rounded_rectangle(
        [margin, margin + clip_height//2, size - margin, size - margin],
        radius=size // 10,
        fill=color
    )
    
    # Clip at top
    clip_width = size // 3
    clip_x = (size - clip_width) // 2
    draw.rounded_rectangle(
        [clip_x, margin, clip_x + clip_width, margin + clip_height],
        radius=size // 20,
        fill=color
    )
    
    # Inner lines (content representation)
    line_margin = size // 4
    line_y_start = margin + clip_height + size // 8
    line_spacing = size // 8
    
    for i in range(3):
        y = line_y_start + i * line_spacing
        draw.line(
            [line_margin, y, size - line_margin - (i * size // 10), y],
            fill="#0a0e14",
            width=max(2, size // 20)
        )
    
    return image


class TrayIcon:
    """
    System tray icon with menu.
    Allows minimizing to tray and quick actions.
    """
    
    def __init__(
        self,
        on_show: Callable[[], None] = None,
        on_quit: Callable[[], None] = None,
        on_toggle_server: Callable[[], None] = None
    ):
        self.on_show = on_show or (lambda: None)
        self.on_quit = on_quit or (lambda: None)
        self.on_toggle_server = on_toggle_server or (lambda: None)
        
        self._icon: Optional[pystray.Icon] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._server_running = False
    
    def start(self):
        """Start tray icon in background thread"""
        if self._running:
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
    
    def _run(self):
        """Run tray icon"""
        image = create_icon_image()
        
        menu = pystray.Menu(
            Item("Show Window", lambda: self.on_show(), default=True),
            Item("Toggle Server", lambda: self.on_toggle_server()),
            pystray.Menu.SEPARATOR,
            Item("Quit", lambda: self._quit())
        )
        
        self._icon = pystray.Icon(
            "CopyPasteEverything",
            image,
            "CopyPasteEverything",
            menu
        )
        
        self._icon.run()
    
    def _quit(self):
        """Handle quit from tray"""
        self.on_quit()
        self.stop()
    
    def stop(self):
        """Stop tray icon"""
        self._running = False
        if self._icon:
            self._icon.stop()
    
    def update_status(self, server_running: bool):
        """Update icon to reflect server status"""
        self._server_running = server_running
        if self._icon:
            color = "#00ff9f" if server_running else "#ff0050"
            self._icon.icon = create_icon_image(color=color)

