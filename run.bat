@echo off
REM CopyPasteEverything - Quick Launch Script
REM ==========================================

echo.
echo   ⚡ COPY.PASTE.EVERYTHING
echo   ========================
echo.

REM Check if venv exists
if not exist "venv" (
    echo [*] Creating virtual environment...
    python -m venv venv
)

REM Activate venv
call venv\Scripts\activate.bat

REM Install dependencies if needed
pip show customtkinter >nul 2>&1
if errorlevel 1 (
    echo [*] Installing dependencies...
    pip install -r requirements.txt -q
)

echo [*] Starting application...
echo.

python main.py

pause

