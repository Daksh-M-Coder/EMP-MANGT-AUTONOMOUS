#!/usr/bin/env python3
"""
HR Agentic System - Complete Project Launcher
Starts all services: Agentic AI Server, Node Backend, and React Frontend
"""

import subprocess
import sys
import os
import time
import signal
from pathlib import Path
from threading import Thread

# Store process references
processes = []

def log_output(process, name, color):
    """Log output from a process with color coding."""
    colors = {
        'agentic': '\033[36m',   # Cyan
        'backend': '\033[32m',   # Green
        'frontend': '\033[35m',  # Magenta
        'reset': '\033[0m'
    }
    prefix = f"{colors.get(color, '')}[{name}]{colors['reset']}"
    
    try:
        for line in iter(process.stdout.readline, b''):
            if line:
                print(f"{prefix} {line.decode('utf-8', errors='replace').rstrip()}", flush=True)
    except:
        pass

def start_agentic():
    """Start the agentic AI server."""
    agentic_dir = Path(__file__).parent / "agentic"
    
    # Check venv
    venv_python = agentic_dir / "venv" / "Scripts" / "python.exe"
    if not venv_python.exists():
        venv_python = agentic_dir / "venv" / "bin" / "python"
    
    python = str(venv_python) if venv_python.exists() else sys.executable
    
    # Find server file
    for server_file in ["server.py", "main.py", "app.py"]:
        if (agentic_dir / server_file).exists():
            break
    else:
        print("✗ No server file found in agentic/")
        return None
    
    print("🚀 Starting Agentic AI Server...")
    process = subprocess.Popen(
        [python, "-m", "uvicorn", f"{Path(server_file).stem}:app", 
         "--host", "0.0.0.0", "--port", "8000", "--reload"],
        cwd=str(agentic_dir),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
    )
    processes.append((process, "agentic"))
    
    # Start log thread
    Thread(target=log_output, args=(process, "AGENTIC", "agentic"), daemon=True).start()
    
    time.sleep(3)  # Wait for startup
    return process

def start_backend():
    """Start the Node.js backend."""
    backend_dir = Path(__file__).parent / "backend"
    
    if not (backend_dir / "package.json").exists():
        print("✗ No package.json found in backend/")
        return None
    
    print("🚀 Starting Node.js Backend...")
    
    cmd = ["npm", "run", "dev"] if sys.platform != "win32" else ["cmd", "/c", "npm run dev"]
    
    process = subprocess.Popen(
        cmd,
        cwd=str(backend_dir),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        shell=sys.platform == "win32",
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
    )
    processes.append((process, "backend"))
    
    # Start log thread
    Thread(target=log_output, args=(process, "BACKEND", "backend"), daemon=True).start()
    
    time.sleep(3)
    return process

def start_frontend():
    """Start the React frontend."""
    frontend_dir = Path(__file__).parent / "frontend"
    
    if not (frontend_dir / "package.json").exists():
        print("✗ No package.json found in frontend/")
        return None
    
    print("🚀 Starting React Frontend...")
    
    cmd = ["npm", "run", "dev"] if sys.platform != "win32" else ["cmd", "/c", "npm run dev"]
    
    process = subprocess.Popen(
        cmd,
        cwd=str(frontend_dir),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        shell=sys.platform == "win32",
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
    )
    processes.append((process, "frontend"))
    
    # Start log thread
    Thread(target=log_output, args=(process, "FRONTEND", "frontend"), daemon=True).start()
    
    return process

def cleanup(signum=None, frame=None):
    """Clean up all processes on exit."""
    print("\n\n🛑 Shutting down all services...")
    
    for process, name in processes:
        print(f"  Stopping {name}...")
        try:
            if sys.platform == "win32":
                process.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                process.terminate()
            
            # Wait a bit, then kill if needed
            try:
                process.wait(timeout=5)
            except:
                process.kill()
        except:
            pass
    
    print("✓ All services stopped")
    sys.exit(0)

def main():
    print("=" * 60)
    print("HR Agentic System - Complete Launcher")
    print("=" * 60)
    
    # Setup cleanup on exit
    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)
    
    # Start services
    agentic = start_agentic()
    backend = start_backend()
    frontend = start_frontend()
    
    if not any([agentic, backend, frontend]):
        print("\n✗ No services started!")
        sys.exit(1)
    
    print("\n" + "=" * 60)
    print("✓ All services started!")
    print("=" * 60)
    print("\n📡 Agentic AI: http://localhost:8000")
    print("🔌 Node Backend: http://localhost:3000 (or check output)")
    print("⚛ React Frontend: http://localhost:5173 (or check output)")
    print("\nPress Ctrl+C to stop all services\n")
    
    # Keep main thread alive
    try:
        while True:
            time.sleep(1)
            # Check if any process died
            for process, name in processes:
                if process.poll() is not None:
                    print(f"\n⚠ {name} process exited with code {process.poll()}")
    except KeyboardInterrupt:
        cleanup()

if __name__ == "__main__":
    main()
