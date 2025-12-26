@echo off
REM CopyPasteEverything - Nuitka Build Script
REM ==========================================
REM Compiles Python to C for faster startup

echo.
echo   🚀 NUITKA BUILD
echo   ===============
echo   Compiling Python to C...
echo.

REM Check if venv exists
if not exist "venv" (
    echo [*] Creating virtual environment...
    python -m venv venv
)

REM Activate venv
call venv\Scripts\activate.bat

REM Install Nuitka if needed
pip show nuitka >nul 2>&1
if errorlevel 1 (
    echo [*] Installing Nuitka and dependencies...
    pip install -r requirements-build.txt -q
)

REM Run the Nuitka build script
python build_nuitka.py

echo.
pause

