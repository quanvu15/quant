#!/usr/bin/env pwsh
# ============================================================
# Analytics Microservice — Dev Setup Script (Windows PowerShell)
# Chạy: .\scripts\setup_dev.ps1
# ============================================================

$ErrorActionPreference = "Stop"
$ROOT = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$API_DIR = Join-Path $ROOT "analytics"
$QT_DIR = Join-Path $ROOT "fincept-qt"
$SCRIPTS_DIR = Join-Path $QT_DIR "scripts"
$VENV_DIR = Join-Path $QT_DIR "venv-numpy2"

Write-Host "`n=== Analytics Microservice Dev Setup ===" -ForegroundColor Cyan
Write-Host "Root: $ROOT"

# ── Step 1: Check Python ──────────────────────────────────────
Write-Host "`n[1/5] Checking Python..." -ForegroundColor Yellow
$pyVersion = python --version 2>&1
Write-Host "  Python: $pyVersion"

# ── Step 2: Create/verify analytics venv ─────────────────────
Write-Host "`n[2/5] Setting up analytics venv..." -ForegroundColor Yellow
$apiVenv = Join-Path $API_DIR ".venv"
if (-not (Test-Path $apiVenv)) {
    Write-Host "  Creating .venv..."
    Set-Location $API_DIR
    python -m venv .venv
} else {
    Write-Host "  .venv already exists ✓"
}

Write-Host "  Installing API dependencies..."
& "$apiVenv\Scripts\pip" install -r "$API_DIR\requirements.txt" -q
Write-Host "  API venv ready ✓"

# ── Step 3: Check/create venv-numpy2 ─────────────────────────
Write-Host "`n[3/5] Checking venv-numpy2..." -ForegroundColor Yellow
$venvPython = Join-Path $VENV_DIR "Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    Write-Host "  venv-numpy2 not found. Creating..." -ForegroundColor Yellow
    Write-Host "  WARNING: This will take 15-30 minutes!" -ForegroundColor Red
    $confirm = Read-Host "  Create venv-numpy2 now? (y/N)"
    if ($confirm -eq "y" -or $confirm -eq "Y") {
        Set-Location $QT_DIR
        python -m venv venv-numpy2
        Write-Host "  Installing requirements-numpy2.txt (please wait)..."
        & "$venvPython" -m pip install --upgrade pip -q
        & "$venvPython" -m pip install -r "$QT_DIR\resources\requirements-numpy2.txt"
        Write-Host "  venv-numpy2 created ✓"
    } else {
        Write-Host "  Skipping venv-numpy2. Some endpoints will not work." -ForegroundColor Yellow
    }
} else {
    # Quick check: yfinance installed?
    $yf = & $venvPython -c "import yfinance; print('ok')" 2>&1
    if ($yf -eq "ok") {
        Write-Host "  venv-numpy2 ready ✓ (yfinance OK)"
    } else {
        Write-Host "  venv-numpy2 exists but yfinance missing. Run:" -ForegroundColor Yellow
        Write-Host "  $venvPython -m pip install -r $QT_DIR\resources\requirements-numpy2.txt"
    }
}

# ── Step 4: Check Redis ───────────────────────────────────────
Write-Host "`n[4/5] Checking Redis..." -ForegroundColor Yellow
$redisRunning = docker ps 2>&1 | Select-String "redis"
if ($redisRunning) {
    Write-Host "  Redis already running ✓"
} else {
    Write-Host "  Starting Redis via Docker..."
    docker run -d --name analytics-redis -p 6379:6379 redis:7.4-alpine 2>&1 | Out-Null
    Start-Sleep -Seconds 2
    Write-Host "  Redis started ✓"
}

# ── Step 5: Verify .env ───────────────────────────────────────
Write-Host "`n[5/5] Checking .env..." -ForegroundColor Yellow
$envFile = Join-Path $API_DIR ".env"
if (-not (Test-Path $envFile)) {
    Write-Host "  .env not found, creating from template..."
    Copy-Item "$API_DIR\.env.example" $envFile
    Write-Host "  .env created. Please edit it!" -ForegroundColor Yellow
} else {
    Write-Host "  .env exists ✓"
}

# Update SCRIPTS_DIR and VENV_NUMPY2_PYTHON in .env
$envContent = Get-Content $envFile -Raw
$envContent = $envContent -replace "SCRIPTS_DIR=.*", "SCRIPTS_DIR=$SCRIPTS_DIR"
if (Test-Path $venvPython) {
    $envContent = $envContent -replace "VENV_NUMPY2_PYTHON=.*", "VENV_NUMPY2_PYTHON=$venvPython"
}
Set-Content $envFile $envContent
Write-Host "  Updated SCRIPTS_DIR and VENV_NUMPY2_PYTHON in .env ✓"

# ── Summary ───────────────────────────────────────────────────
Write-Host "`n=== Setup Complete ===" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. Edit analytics\.env — add your LLM API key"
Write-Host "     (Groq free key: https://console.groq.com)"
Write-Host ""
Write-Host "  2. Start the API:"
Write-Host "     cd analytics"
Write-Host "     .venv\Scripts\activate"
Write-Host "     uvicorn app.main:app --reload --port 8000"
Write-Host ""
Write-Host "  3. Test:"
Write-Host "     curl http://localhost:8000/health"
Write-Host "     Open: http://localhost:8000/docs"
Write-Host ""
