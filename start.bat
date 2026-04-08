@echo off
chcp 65001 >nul
title HR Agentic System - Launcher
cls

echo ╔══════════════════════════════════════════════════════════════╗
echo ║           HR Agentic System - One Click Launcher             ║
echo ║                    (Windows Edition)                           ║
echo ╚══════════════════════════════════════════════════════════════╝
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.8+ from python.org
    pause
    exit /b 1
)
echo [✓] Python found

:: Check Node
node --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js not found. Please install Node.js 18+ from nodejs.org
    pause
    exit /b 1
)
echo [✓] Node.js found

:: Check Ollama
ollama --version >nul 2>&1
if errorlevel 1 (
    echo [WARNING] Ollama not found. Local AI won't work. Install from ollama.com
    echo [INFO] Cloud fallbacks (Groq/Gemini/OpenRouter) will still work if API keys are set
)

echo.
echo ═══════════════════════════════════════════════════════════════
echo  SETUP CHECK

echo ═══════════════════════════════════════════════════════════════

:: Setup venv if doesn't exist
if not exist "agentic\venv\Scripts\python.exe" (
    echo.
    echo [!] Virtual environment not found. Creating now...
    echo.
    cd agentic
    python setup_venv.py
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment
        cd ..
        pause
        exit /b 1
    )
    cd ..
    echo [✓] Virtual environment created
) else (
    echo [✓] Virtual environment exists
)

:: Check .env file
if not exist "agentic\.env" (
    echo.
    echo [!] .env file not found. Creating from template...
    copy agentic\.env.example agentic\.env >nul
    echo [✓] Created agentic\.env
    echo [!] IMPORTANT: Edit agentic\.env to add your API keys if you want cloud fallbacks
    echo     (Ollama works locally without any keys)
) else (
    echo [✓] .env file exists
)

:: Check Ollama models
echo.
echo [INFO] Checking Ollama models...
ollama list | findstr "qwen2.5-coder" >nul
if errorlevel 1 (
    echo [!] qwen2.5-coder:1.5b not found. Pulling now...
    start "Pulling qwen2.5-coder" cmd /k "ollama pull qwen2.5-coder:1.5b && echo Done && pause"
) else (
    echo [✓] qwen2.5-coder:1.5b ready
)

ollama list | findstr "nemotron-mini" >nul
if errorlevel 1 (
    echo [!] nemotron-mini not found. Pulling now...
    start "Pulling nemotron-mini" cmd /k "ollama pull nemotron-mini && echo Done && pause"
) else (
    echo [✓] nemotron-mini ready
)

echo.
echo ═══════════════════════════════════════════════════════════════
echo  STARTING SERVICES

echo ═══════════════════════════════════════════════════════════════
echo.

:: Kill any existing processes on ports (optional cleanup)
echo [INFO] Cleaning up existing processes...
taskkill /F /IM "python.exe" /FI "WINDOWTITLE eq AGENTIC*" >nul 2>&1
taskkill /F /IM "node.exe" /FI "WINDOWTITLE eq BACKEND*" >nul 2>&1
taskkill /F /IM "node.exe" /FI "WINDOWTITLE eq FRONTEND*" >nul 2>&1
timeout /t 2 /nobreak >nul

:: Get the current directory for paths
set "BASE_DIR=%CD%"

:: Start Agentic AI Server (cyan window)
echo [1/3] Starting AGENTIC AI Server...
echo        URL: http://localhost:8000
echo        API Docs: http://localhost:8000/docs
echo.
start "AGENTIC AI - Port 8000" cmd /k "cd /d "%BASE_DIR%\agentic" && echo ╔════════════════════════════════════════════════╗ && echo ║     AGENTIC AI SERVER - Real-time Logs         ║ && echo ║     URL: http://localhost:8000                 ║ && echo ╚════════════════════════════════════════════════╝ && echo. && venv\Scripts\python -m uvicorn server:app --host 0.0.0.0 --port 8000 --reload --reload-dir . && pause"

timeout /t 3 /nobreak >nul

:: Start Node Backend (green window)
echo [2/3] Starting NODE BACKEND...
echo        URL: http://localhost:3000
echo.
start "BACKEND API - Port 3000" cmd /k "cd /d "%BASE_DIR%\backend" && echo ╔════════════════════════════════════════════════╗ && echo ║      NODE BACKEND SERVER - Real-time Logs      ║ && echo ║      URL: http://localhost:3000                ║ && echo ╚════════════════════════════════════════════════╝ && echo. && npm run dev && pause"

timeout /t 3 /nobreak >nul

:: Start React Frontend (magenta window)
echo [3/3] Starting REACT FRONTEND...
echo        URL: http://localhost:5173
echo.
start "FRONTEND UI - Port 5173" cmd /k "cd /d "%BASE_DIR%\frontend" && echo ╔════════════════════════════════════════════════╗ && echo ║     REACT FRONTEND - Real-time Logs            ║ && echo ║     URL: http://localhost:5173               ║ && echo ╚════════════════════════════════════════════════╝ && echo. && npm run dev && pause"

timeout /t 2 /nobreak >nul

:: Show status
echo.
echo ╔══════════════════════════════════════════════════════════════╗
echo ║                    ALL SERVICES STARTED!                      ║
echo ╠══════════════════════════════════════════════════════════════╣
echo ║  Service        │  URL                        │  Window Title  ║
echo ╠═════════════════╪═════════════════════════════╪════════════════╣
echo ║  Agentic AI     │  http://localhost:8000      │  AGENTIC AI    ║
echo ║  Backend API    │  http://localhost:3000      │  BACKEND API   ║
echo ║  Frontend UI    │  http://localhost:5173      │  FRONTEND UI   ║
echo ╚═════════════════╧═════════════════════════════╧════════════════╝
echo.
echo [INFO] Three terminal windows are now open showing real-time logs
echo [INFO] Do NOT close this window - it monitors the services
.
echo.
echo Press any key to STOP all services and close everything...
pause >nul

:: Cleanup - kill all started processes
echo.
echo [STOPPING] Shutting down all services...
taskkill /F /FI "WINDOWTITLE eq AGENTIC AI*" >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq BACKEND API*" >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq FRONTEND UI*" >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq Pulling*" >nul 2>&1
echo [✓] All services stopped
echo.
pause
