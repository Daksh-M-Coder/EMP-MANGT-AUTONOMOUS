#Requires -Version 5.1
<#
.SYNOPSIS
    Unload nemotron-mini from Ollama memory to free up RAM.
    
.DESCRIPTION
    This script immediately unloads the nemotron-mini model from Ollama memory.
    Use this when you want to free up GPU/CPU RAM for other tasks.
    The model will be reloaded on next request (taking 10-30s).
    
.EXAMPLE
    .\unload-nemotron.ps1
    
.NOTES
    No confirmation needed - runs immediately.
#>

$ErrorActionPreference = "Stop"

$model = "nemotron-mini"
$ollamaUrl = "http://localhost:11434/api/generate"

Write-Host @"
========================================
   NEMOTRON-MINI MODEL UNLOAD
========================================

This will FREE UP memory by unloading the model.
Next request will take 10-30s to reload.

========================================
"@ -ForegroundColor Yellow

# Check if Ollama is running
try {
    $null = Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -Method GET -TimeoutSec 5
} catch {
    Write-Host "[INFO] Ollama is not running - nothing to unload." -ForegroundColor Gray
    exit 0
}

# Unload the model by sending a special request
# Ollama unloads a model when you ask it to generate with keep_alive=0
try {
    Write-Host "Unloading $model from memory..." -ForegroundColor Cyan -NoNewline
    
    $unloadBody = @{
        model = $model
        prompt = ""
        stream = $false
        keep_alive = 0  # 0 = unload immediately
    } | ConvertTo-Json -Compress
    
    # Sending empty prompt with keep_alive=0 unloads the model
    Invoke-RestMethod -Uri $ollamaUrl -Method POST -Body $unloadBody -ContentType "application/json" -TimeoutSec 10 | Out-Null
    
    Write-Host " DONE" -ForegroundColor Green
    Write-Host "`n[OK] Model unloaded - memory freed!" -ForegroundColor Green
    Write-Host "    Next request will reload the model (10-30s)." -ForegroundColor Gray
    
} catch {
    # If it fails, the model was probably not loaded anyway
    Write-Host " DONE (model was not loaded)" -ForegroundColor Gray
}

# Also kill any running load-nemotron.ps1 processes
$loadProcesses = Get-Process | Where-Object { 
    $_.ProcessName -eq "powershell" -and 
    $_.MainWindowTitle -like "*nemotron*" 
}

if ($loadProcesses) {
    Write-Host "`nStopping keep-alive scripts..." -ForegroundColor Cyan
    $loadProcesses | ForEach-Object { 
        try {
            Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
            Write-Host "  Stopped PID $($_.Id)" -ForegroundColor Gray
        } catch {
            # Ignore errors
        }
    }
}

Write-Host "`n========================================" -ForegroundColor Yellow
Write-Host "Model unloaded successfully!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Yellow
