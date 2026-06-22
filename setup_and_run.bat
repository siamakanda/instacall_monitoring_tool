@echo off
SETLOCAL EnableDelayedExpansion

echo ============================================================
echo      Instacall Balance Monitor - Automated Setup and Run
echo ============================================================

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] Error: Python is not installed or not added to your system PATH.
    echo Please install Python before running this script.
    pause
    exit /b
)

if not exist .env.example (
    echo [+] Creating .env.example file...
    (
        echo PORTAL_USERNAME="your_username_here"
        echo PORTAL_PASSWORD="your_password_here"
        echo CUSTOMER_IDS="18,22,35"
    ) > .env.example
)

if not exist .env (
    echo [+] Creating production .env file from template...
    copy .env.example .env >nul
    echo [!] ACTION REQUIRED: Please open the .env file and add your real credentials.
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
    echo [+] Installing dependencies from requirements.txt...
    pip install -r requirements.txt
) else (
    echo [!] Warning: requirements.txt not found. Skipping dependency install.
)

echo ============================================================
echo [+] Setup complete. Launching balance monitor loop...
echo ============================================================
python balance_alert.py

pause