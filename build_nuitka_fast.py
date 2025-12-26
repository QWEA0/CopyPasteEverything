#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
build_nuitka_fast.py - Nuitka build script for fastest startup
Uses standalone mode (folder distribution) instead of onefile for instant startup
"""

import os
import shutil
import subprocess
import sys


def check_requirements():
    """Check if Nuitka is installed"""
    try:
        result = subprocess.run(
            [sys.executable, '-m', 'nuitka', '--version'],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            version = result.stdout.strip().split('\n')[0]
            print(f"✓ {version}")
            return True
        else:
            print("✗ Nuitka not working properly")
            return False
    except Exception:
        print("✗ Nuitka not installed")
        print("  Run: pip install -r requirements-build.txt")
        return False


def clean_build():
    """Clean previous builds"""
    dirs_to_remove = [
        'main.build', 'main.dist', 'main.onefile-build',
        'nuitka_dist_fast'
    ]
    for dir_name in dirs_to_remove:
        if os.path.exists(dir_name):
            try:
                shutil.rmtree(dir_name, ignore_errors=True)
                print(f"✓ Removed {dir_name}")
            except Exception as e:
                print(f"⚠ Could not remove {dir_name}: {e}")


def build_nuitka():
    """Build using Nuitka in standalone mode (fastest startup)"""
    print("\n🔨 Building with Nuitka (standalone mode for fastest startup)...")
    print("   This creates a folder with the exe and dependencies\n")

    # Nuitka command - STANDALONE mode (no onefile)
    cmd = [
        sys.executable, '-m', 'nuitka',

        # Output options
        '--standalone',                     # Standalone distribution (folder)
        # NO --onefile flag = faster startup!
        '--output-filename=CopyPasteEverything.exe',
        '--output-dir=nuitka_dist_fast',

        # Windows options
        '--windows-console-mode=disable',   # No console window (GUI app)
        '--mingw64',                        # Use MinGW64 compiler

        # Plugin for GUI frameworks
        '--enable-plugin=tk-inter',         # For customtkinter/tkinter

        # Include packages
        '--include-package=src',
        '--include-package=customtkinter',
        '--include-package=pystray',
        '--include-package=PIL',
        '--include-package=websockets',
        '--include-package=aiohttp',
        '--include-package=cryptography',

        # Optimization
        '--assume-yes-for-downloads',       # Auto download dependencies
        '--remove-output',                  # Remove build folder after

        # Entry point
        'main.py'
    ]

    # Add icon if .ico file exists
    ico_path = 'assets/icon.ico'
    if os.path.exists(ico_path):
        cmd.insert(-1, f'--windows-icon-from-ico={ico_path}')
        print(f"   Using icon: {ico_path}")
    
    print("Command:", ' '.join(cmd))
    print("-" * 60)
    
    result = subprocess.run(cmd)
    
    if result.returncode == 0:
        exe_path = os.path.join('nuitka_dist_fast', 'main.dist', 'CopyPasteEverything.exe')
        if os.path.exists(exe_path):
            size_mb = os.path.getsize(exe_path) / (1024 * 1024)
            print("-" * 60)
            print(f"✓ Build successful!")
            print(f"✓ Output: {exe_path} ({size_mb:.1f} MB)")
            print(f"\n📁 Distribution folder: nuitka_dist_fast\\main.dist\\")
            print(f"   This folder contains the exe and all dependencies")
            print(f"   ⚡ Startup is INSTANT (no extraction needed)!")
            return True
    
    print("✗ Build failed!")
    return False


def print_tips():
    """Print usage tips"""
    print("\n💡 Tips:")
    print("1. ⚡ Standalone mode = INSTANT startup (no extraction)")
    print("2. 📁 Distribute the entire 'main.dist' folder")
    print("3. 💾 Larger disk space but much faster startup")
    print("4. 🎯 For single-file distribution, use build_nuitka.py instead")


if __name__ == '__main__':
    print("🚀 CopyPasteEverything - Nuitka Fast Builder")
    print("=" * 60)
    print("Standalone mode for INSTANT startup (no extraction delay)")
    print("=" * 60)
    
    if not check_requirements():
        sys.exit(1)
    
    clean_build()
    
    if build_nuitka():
        print_tips()
        print("\n✅ Build complete!")
    else:
        print("\n❌ Build failed!")
        sys.exit(1)

