@echo off
REM CopyPasteEverything - Installation Script
REM ==========================================

echo.
echo   ⚡ COPY.PASTE.EVERYTHING INSTALLER
echo   ===================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH
    echo Please install Python 3.10+ from https://python.org
    pause
    exit /b 1
)

echo [*] Python found
python --version

echo.
echo [*] Creating virtual environment...
python -m venv venv

echo [*] Activating virtual environment...
call venv\Scripts\activate.bat

echo [*] Upgrading pip...
python -m pip install --upgrade pip -q

echo [*] Installing dependencies...
pip install -r requirements.txt

echo.
echo   ✓ Installation complete!
echo.
echo   To run the application:
echo     - Double-click run.bat
echo     - Or run: python main.py
echo.

pause

