#!/usr/bin/env python3
"""
HR Agentic System - Project Runner
Starts the LangGraph agentic server with auto-reload for development.
"""

import subprocess
import sys
import os
from pathlib import Path

def check_venv():
    """Check if running in virtual environment."""
    in_venv = (
        hasattr(sys, 'real_prefix') or
        (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix)
    )
    
    venv_path = Path(__file__).parent / "venv"
    
    if not in_venv and venv_path.exists():
        print("⚠ Not running in virtual environment!")
        print("\nPlease activate it first:")
        if sys.platform == "win32":
            print(f"  {venv_path}\\Scripts\\activate")
        else:
            print(f"  source {venv_path}/bin/activate")
        print("\nOr run: python setup_venv.py")
        
        response = input("\nContinue anyway? [y/N]: ").lower()
        if response != 'y':
            sys.exit(1)

def check_env_file():
    """Check if .env file exists."""
    env_file = Path(__file__).parent / ".env"
    env_example = Path(__file__).parent / ".env.example"
    
    if not env_file.exists():
        print("⚠ No .env file found!")
        if env_example.exists():
            print(f"\nCreating from {env_example.name}...")
            env_file.write_text(env_example.read_text())
            print(f"✓ Created {env_file}")
            print("\n⚠ IMPORTANT: Edit .env and add your API keys if needed:")
            print("  - GROQ_API_KEY (optional, for cloud fallback)")
            print("  - GEMINI_API_KEY (optional, for cloud fallback)")
            print("  - OPENROUTER_API_KEY (optional, for cloud fallback)")
            print("\nOllama works locally without API keys!")
        else:
            print("✗ No .env.example file found!")
            sys.exit(1)

def main():
    agentic_dir = Path(__file__).parent
    
    print("=" * 60)
    print("HR Agentic System - Server Runner")
    print("=" * 60)
    
    # Check virtual environment
    check_venv()
    
    # Check .env file
    check_env_file()
    
    # Check if server.py exists
    server_file = agentic_dir / "server.py"
    if not server_file.exists():
        # Try main.py or app.py
        for alt in ["main.py", "app.py", "api.py"]:
            alt_file = agentic_dir / alt
            if alt_file.exists():
                server_file = alt_file
                break
        else:
            print("✗ No server.py, main.py, app.py, or api.py found!")
            sys.exit(1)
    
    print(f"\n🚀 Starting server from {server_file.name}...")
    print("📡 Server will be available at: http://localhost:8000")
    print("📖 API docs available at: http://localhost:8000/docs")
    print("\nPress Ctrl+C to stop\n")
    
    # Run uvicorn with auto-reload
    try:
        subprocess.run([
            sys.executable, "-m", "uvicorn",
            f"{server_file.stem}:app",
            "--host", "0.0.0.0",
            "--port", "8000",
            "--reload",
            "--reload-dir", str(agentic_dir)
        ], cwd=str(agentic_dir))
    except KeyboardInterrupt:
        print("\n\n✓ Server stopped")
        sys.exit(0)

if __name__ == "__main__":
    main()
