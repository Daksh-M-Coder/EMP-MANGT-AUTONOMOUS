#Requires -Version 5.1
<#
.SYNOPSIS
    Keep nemotron-mini loaded in Ollama for fast AI responses.
    
.DESCRIPTION
    This script keeps the nemotron-mini model hot-loaded in Ollama memory.
    By default, Ollama unloads models after 5 minutes of inactivity.
    This sends a heartbeat request every 3 minutes to keep it loaded.
    
    BENEFIT: First response time drops from ~10-30s (cold load) to ~1-3s (hot).
    
.EXAMPLE
    .\load-nemotron.ps1
    
    # Run in background (no window)
    Start-Process PowerShell -ArgumentList "-File .\load-nemotron.ps1" -WindowStyle Hidden
    
.NOTES
    Press Ctrl+C to stop the heartbeat loop.
#>

$ErrorActionPreference = "Stop"

$model = "nemotron-mini"
$ollamaUrl = "http://localhost:11434/api/generate"
$heartbeatInterval = 180  # 3 minutes in seconds

Write-Host @"
========================================
   NEMOTRON-MINI MODEL KEEP-ALIVE
========================================

Model: $model
Heartbeat: Every $($heartbeatInterval / 60) minutes

This script keeps the model loaded for fast responses.
Without this, first response takes 10-30s to load the model.
With keep-alive: responses are instant (~1-3s).

Press Ctrl+C to stop.

========================================
"@ -ForegroundColor Cyan

# Check if Ollama is running
try {
    $null = Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -Method GET -TimeoutSec 5
    Write-Host "[OK] Ollama is running" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Ollama is not running! Start Ollama first." -ForegroundColor Red
    Write-Host "Download from: https://ollama.com" -ForegroundColor Yellow
    exit 1
}

# Check if model exists
try {
    $models = Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -Method GET
    $modelExists = $models.models | Where-Object { $_.name -like "*$model*" }
    if (-not $modelExists) {
        Write-Host "[!] Model '$model' not found. Pulling now..." -ForegroundColor Yellow
        ollama pull $model
    } else {
        Write-Host "[OK] Model '$model' exists" -ForegroundColor Green
    }
} catch {
    Write-Host "[WARNING] Could not check model list" -ForegroundColor Yellow
}

# Initial load - send a warmup request
Write-Host "`n[1] Warming up model (first load takes ~30s)..." -ForegroundColor Cyan
$warmupBody = @{
    model = $model
    prompt = "Hi"
    stream = $false
    options = @{ temperature = 0 }
} | ConvertTo-Json -Compress

try {
    $null = Invoke-RestMethod -Uri $ollamaUrl -Method POST -Body $warmupBody -ContentType "application/json" -TimeoutSec 60
    Write-Host "[OK] Model is now HOT (loaded in memory)" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Failed to load model: $_" -ForegroundColor Red
    exit 1
}

# Keep-alive loop
$counter = 1
while ($true) {
    Write-Host "`n[$counter] Sending heartbeat in $($heartbeatInterval / 60) minutes..." -ForegroundColor DarkGray
    
    for ($i = $heartbeatInterval; $i -gt 0; $i -= 10) {
        Start-Sleep -Seconds 10
        Write-Host "  ... waiting $i seconds" -ForegroundColor DarkGray -NoNewline
        Write-Host ""  # Newline
    }
    
    try {
        $heartbeatBody = @{
            model = $model
            prompt = "."  # Minimal prompt to keep model loaded
            stream = $false
            options = @{ temperature = 0 }
        } | ConvertTo-Json -Compress
        
        $null = Invoke-RestMethod -Uri $ollamaUrl -Method POST -Body $heartbeatBody -ContentType "application/json" -TimeoutSec 30
        Write-Host "[OK] Heartbeat sent - model stays HOT" -ForegroundColor Green
    } catch {
        Write-Host "[WARNING] Heartbeat failed: $_" -ForegroundColor Yellow
    }
    
    $counter++
}
