# -*- coding: utf-8 -*-
"""
CopyPasteEverything - Lightweight Clipboard Sync Tool
=====================================================

A geek-style, lightweight clipboard synchronization tool for Windows.
Features:
- Auto tunnel support for remote connections
- Real-time clipboard sync between devices
- Clipboard history with search
- Minimal resource usage

Usage:
    python main.py

Author: CopyPasteEverything
Version: 1.0.0
"""

import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.app import main

if __name__ == "__main__":
    main()

