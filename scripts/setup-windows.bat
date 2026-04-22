@echo off
REM ============================================
REM ITSM Knowledge-Based Multi-Agent Setup (Windows)
REM ============================================

echo.
echo ========================================================================
echo    ITSM Knowledge-Based Multi-Agent Solution
echo    Setup Script (Windows)
echo ========================================================================
echo.

REM Check Python
echo [*] Checking prerequisites...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH
    echo Please install Python 3.11+ from https://www.python.org/downloads/
    pause
    exit /b 1
)
echo [OK] Python found
python --version

REM Check Docker
docker --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [WARNING] Docker not found (optional for local dev)
) else (
    echo [OK] Docker found
    docker --version
)

REM Check Azure CLI
az --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [WARNING] Azure CLI not found (required for deployment)
) else (
    echo [OK] Azure CLI found
)

echo.

REM Create virtual environment
echo [*] Setting up Python virtual environment...
if exist venv (
    echo [WARNING] Virtual environment already exists
    set /p recreate="Recreate it? (y/N): "
    if /i "%recreate%"=="y" (
        echo [*] Removing old virtual environment...
        rmdir /s /q venv
        echo [*] Creating new virtual environment...
        python -m venv venv
    )
) else (
    python -m venv venv
    echo [OK] Virtual environment created
)

echo.

REM Activate virtual environment
echo [*] Activating virtual environment...
call venv\Scripts\activate.bat
if %errorlevel% neq 0 (
    echo [ERROR] Failed to activate virtual environment
    pause
    exit /b 1
)
echo [OK] Virtual environment activated

echo.

REM Upgrade pip
echo [*] Upgrading pip...
python -m pip install --upgrade pip --quiet
echo [OK] pip upgraded

echo.

REM Install dependencies
echo [*] Installing dependencies...
echo This may take a few minutes...
pip install -r requirements.txt --quiet
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install dependencies
    pause
    exit /b 1
)
echo [OK] Dependencies installed successfully

echo.

REM Create .env file
if not exist .env (
    echo [*] Creating .env file from template...
    copy .env.example .env
    echo [OK] .env file created
    echo [WARNING] IMPORTANT: Please update .env with your Azure credentials!
) else (
    echo [WARNING] .env file already exists (not overwriting)
)

echo.

REM Summary
echo ========================================================================
echo.
echo   Setup completed successfully!
echo.
echo ========================================================================
echo.
echo Next Steps:
echo.
echo   1. Update your .env file with Azure credentials:
echo      notepad .env
echo.
echo   2. Update .env with GCC Azure OpenAI and AI Search values
echo      - AZURE_OPENAI_ENDPOINT / DEPLOYMENT / API_VERSION
echo      - AZURE_SEARCH_ENDPOINT / AZURE_SEARCH_INDEX
echo.
echo   3. Start the FastAPI services:
echo      docker-compose up -d
echo.
echo   4. Verify APIs are running:
echo      curl http://localhost:8000/
echo      curl http://localhost:8001/
echo.
echo   5. Run the orchestrator:
echo      venv\Scripts\activate
echo      python src\main.py --help
echo.
echo ========================================================================
echo.

pause
