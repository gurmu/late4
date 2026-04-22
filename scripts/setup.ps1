# ============================================
# ITSM Knowledge-Based Multi-Agent Setup (PowerShell)
# ============================================

Write-Host ""
Write-Host "========================================================================" -ForegroundColor Cyan
Write-Host "   ITSM Knowledge-Based Multi-Agent Solution" -ForegroundColor Cyan
Write-Host "   Setup Script (PowerShell)" -ForegroundColor Cyan
Write-Host "========================================================================" -ForegroundColor Cyan
Write-Host ""

# Check Python
Write-Host "[*] Checking prerequisites..." -ForegroundColor Blue
try {
    $pythonVersion = python --version 2>&1
    Write-Host "[OK] Python found: $pythonVersion" -ForegroundColor Green
}
catch {
    Write-Host "[ERROR] Python is not installed or not in PATH" -ForegroundColor Red
    Write-Host "Please install Python 3.11+ from https://www.python.org/downloads/" -ForegroundColor Yellow
    exit 1
}

# Check Docker
try {
    $dockerVersion = docker --version 2>&1
    Write-Host "[OK] Docker found: $dockerVersion" -ForegroundColor Green
}
catch {
    Write-Host "[WARNING] Docker not found (optional for local dev)" -ForegroundColor Yellow
}

# Check Azure CLI
try {
    $azVersion = az --version 2>&1 | Select-Object -First 1
    Write-Host "[OK] Azure CLI found" -ForegroundColor Green
}
catch {
    Write-Host "[WARNING] Azure CLI not found (required for deployment)" -ForegroundColor Yellow
}

Write-Host ""

# Create virtual environment
Write-Host "[*] Setting up Python virtual environment..." -ForegroundColor Blue
if (Test-Path "venv") {
    Write-Host "[WARNING] Virtual environment already exists" -ForegroundColor Yellow
    $recreate = Read-Host "Recreate it? (y/N)"
    if ($recreate -eq "y" -or $recreate -eq "Y") {
        Write-Host "[*] Removing old virtual environment..." -ForegroundColor Blue
        Remove-Item -Recurse -Force venv
        Write-Host "[*] Creating new virtual environment..." -ForegroundColor Blue
        python -m venv venv
    }
}
else {
    python -m venv venv
    Write-Host "[OK] Virtual environment created" -ForegroundColor Green
}

Write-Host ""

# Activate virtual environment
Write-Host "[*] Activating virtual environment..." -ForegroundColor Blue
& .\venv\Scripts\Activate.ps1
if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne $null) {
    Write-Host "[ERROR] Failed to activate virtual environment" -ForegroundColor Red
    exit 1
}
Write-Host "[OK] Virtual environment activated" -ForegroundColor Green

Write-Host ""

# Upgrade pip
Write-Host "[*] Upgrading pip..." -ForegroundColor Blue
python -m pip install --upgrade pip --quiet
Write-Host "[OK] pip upgraded" -ForegroundColor Green

Write-Host ""

# Install dependencies
Write-Host "[*] Installing dependencies..." -ForegroundColor Blue
Write-Host "This may take a few minutes..." -ForegroundColor Yellow
pip install -r requirements.txt --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Failed to install dependencies" -ForegroundColor Red
    exit 1
}
Write-Host "[OK] Dependencies installed successfully" -ForegroundColor Green

Write-Host ""

# Create .env file
if (-not (Test-Path ".env")) {
    Write-Host "[*] Creating .env file from template..." -ForegroundColor Blue
    Copy-Item .env.example .env
    Write-Host "[OK] .env file created" -ForegroundColor Green
    Write-Host "[WARNING] IMPORTANT: Please update .env with your Azure credentials!" -ForegroundColor Yellow
}
else {
    Write-Host "[WARNING] .env file already exists (not overwriting)" -ForegroundColor Yellow
}

Write-Host ""

# Summary
Write-Host "========================================================================" -ForegroundColor Green
Write-Host "" -ForegroundColor Green
Write-Host "   Setup completed successfully!" -ForegroundColor Green
Write-Host "" -ForegroundColor Green
Write-Host "========================================================================" -ForegroundColor Green
Write-Host ""

Write-Host "Next Steps:" -ForegroundColor Yellow
Write-Host ""
Write-Host "  1. Update your .env file with Azure credentials:" -ForegroundColor White
Write-Host "     notepad .env" -ForegroundColor Cyan
Write-Host ""
Write-Host "  2. Update .env with GCC Azure OpenAI and AI Search values" -ForegroundColor White
Write-Host "     - AZURE_OPENAI_ENDPOINT / DEPLOYMENT / API_VERSION" -ForegroundColor White
Write-Host "     - AZURE_SEARCH_ENDPOINT / AZURE_SEARCH_INDEX" -ForegroundColor White
Write-Host ""
Write-Host "  3. Start the FastAPI services:" -ForegroundColor White
Write-Host "     docker-compose up -d" -ForegroundColor Cyan
Write-Host ""
Write-Host "  4. Verify APIs are running:" -ForegroundColor White
Write-Host "     curl http://localhost:8000/" -ForegroundColor Cyan
Write-Host "     curl http://localhost:8001/" -ForegroundColor Cyan
Write-Host ""
Write-Host "  5. Run the orchestrator:" -ForegroundColor White
Write-Host "     .\venv\Scripts\Activate.ps1" -ForegroundColor Cyan
Write-Host "     python src\main.py --help" -ForegroundColor Cyan
Write-Host ""
Write-Host "========================================================================" -ForegroundColor Green
Write-Host ""
