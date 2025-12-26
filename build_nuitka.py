#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
build_nuitka.py - Nuitka build script for CopyPasteEverything
Uses Nuitka to compile Python to C for faster startup and execution
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
        'dist/main.build', 'dist/main.dist', 'dist/main.onefile-build'
    ]
    for dir_name in dirs_to_remove:
        if os.path.exists(dir_name):
            try:
                shutil.rmtree(dir_name, ignore_errors=True)
                print(f"✓ Removed {dir_name}")
            except Exception as e:
                print(f"⚠ Could not remove {dir_name}: {e}")

    # Clean old exe
    exe_files = ['main.exe', 'CopyPasteEverything.exe', 'dist/CopyPasteEverything.exe']
    for exe in exe_files:
        if os.path.exists(exe):
            try:
                os.remove(exe)
                print(f"✓ Removed {exe}")
            except Exception as e:
                print(f"⚠ Could not remove {exe}: {e}")


def build_nuitka():
    """Build using Nuitka"""
    print("\n🔨 Building with Nuitka (compiling to C)...")
    print("   This may take several minutes on first build...\n")

    # Nuitka command with optimization flags
    cmd = [
        sys.executable, '-m', 'nuitka',

        # Output options
        '--standalone',                     # Create standalone distribution
        '--onefile',                        # Single exe file
        '--output-filename=CopyPasteEverything.exe',
        '--output-dir=nuitka_dist',

        # Windows options
        '--windows-console-mode=disable',   # No console window (GUI app)
        '--mingw64',                        # Use MinGW64 compiler (auto-download)

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
        '--lto=yes',                        # Link Time Optimization for smaller size
        '--onefile-tempdir-spec=%TEMP%\\CopyPasteEverything',  # Use temp dir for faster extraction

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
        exe_path = os.path.join('nuitka_dist', 'CopyPasteEverything.exe')
        if os.path.exists(exe_path):
            size_mb = os.path.getsize(exe_path) / (1024 * 1024)
            print("-" * 60)
            print(f"✓ Build successful!")
            print(f"✓ Output: {exe_path} ({size_mb:.1f} MB)")
            return True
    
    print("✗ Build failed!")
    return False


def print_tips():
    """Print optimization tips"""
    print("\n💡 Tips:")
    print("1. First build is slow (compiling C code), subsequent builds are faster")
    print("2. Nuitka exe should start 3-5x faster than PyInstaller")
    print("3. For even smaller size, you can use --lto=yes (Link Time Optimization)")
    print("4. Use --show-progress for detailed build progress")


if __name__ == '__main__':
    print("🚀 CopyPasteEverything - Nuitka Builder")
    print("=" * 60)
    print("Compiles Python to C for faster startup and execution")
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

