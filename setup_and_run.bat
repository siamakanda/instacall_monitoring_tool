@echo off
SETLOCAL EnableDelayedExpansion

echo ============================================================
echo      Instacall Monitoring Tool - Automated Setup and Run
echo ============================================================

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] Error: Python is not installed or not added to your system PATH.
    echo Please install Python 3.10 or later before running this script.
    pause
    exit /b
)

if not exist .env (
    if exist .env.example (
        echo [+] Creating .env file from .env.example...
        copy .env.example .env >nul
        echo [!] ACTION REQUIRED: Edit .env and add your portal credentials.
        echo     PORTAL_USERNAME="your_username"
        echo     PORTAL_PASSWORD="your_password"
    ) else (
        echo [!] .env.example not found. Create .env with:
        echo     PORTAL_USERNAME="your_username"
        echo     PORTAL_PASSWORD="your_password"
    )
)

if not exist venv (
    echo [+] Creating Python virtual environment...
    python -m venv venv
) else (
    echo [+] Virtual environment already exists.
)

echo [+] Activating virtual environment...
call venv\Scripts\activate

if exist requirements.txt (
    echo [+] Installing dependencies...
    pip install -r requirements.txt
)

echo ============================================================
echo [+] Setup complete. Launching Monitoring Tool...
echo ============================================================
echo.
echo   Menu options:
echo     0 - Quick Check Parallel (Async)
echo     1 - Start Monitor
echo     2 - Quick Balances
echo     3 - Quick Summary
echo     5 - Settings
echo     6 - Profiles
echo     7 - History
echo     8 - Export
echo     9 - Exit
echo.
python menu.py

pause
