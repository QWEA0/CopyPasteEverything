# -*- coding: utf-8 -*-
"""
config.py - Configuration management for CopyPasteEverything
Handles all configuration settings including network, storage, and UI preferences
"""

import os
import json
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional

# Application directories
APP_NAME = "CopyPasteEverything"
APP_DIR = Path(os.environ.get("APPDATA", ".")) / APP_NAME
DATA_DIR = APP_DIR / "data"
CONFIG_FILE = APP_DIR / "config.json"

# Ensure directories exist
APP_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class Config:
    """Application configuration dataclass"""
    # Network settings
    server_port: int = 2580
    tunnel_enabled: bool = True
    tunnel_subdomain: str = ""
    
    # Sync settings
    auto_sync: bool = True
    sync_interval_ms: int = 500
    max_content_size: int = 10 * 1024 * 1024  # 10MB

    # File transfer settings
    max_file_size: int = 50 * 1024 * 1024  # 50MB per file
    max_total_file_size: int = 100 * 1024 * 1024  # 100MB total per transfer

    # Chunked transfer settings (for large files)
    chunk_threshold: int = 10 * 1024 * 1024  # 10MB - files larger than this use chunked transfer
    chunk_size: int = 256 * 1024  # 256KB per chunk (smaller for better reliability over tunnels)
    max_concurrent_transfers: int = 3  # Max concurrent file transfers
    transfer_timeout: int = 300  # 5 minutes timeout for each transfer
    resume_enabled: bool = True  # Enable resume for interrupted transfers
    
    # History settings
    history_enabled: bool = True
    max_history_items: int = 100
    
    # UI settings
    theme: str = "dark"
    always_on_top: bool = False
    minimize_to_tray: bool = True
    start_minimized: bool = False
    
    # Security
    encryption_enabled: bool = True
    connection_password: str = ""
    
    def save(self):
        """Save configuration to file"""
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(asdict(self), f, indent=2, ensure_ascii=False)
    
    @classmethod
    def load(cls) -> 'Config':
        """Load configuration from file"""
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return cls(**data)
            except Exception:
                pass
        return cls()


# Global config instance
config = Config.load()

