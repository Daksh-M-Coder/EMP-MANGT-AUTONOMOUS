#!/usr/bin/env python3
"""
Setup virtual environment and install dependencies for HR Agentic System.
Run this first before starting the project.
"""

import subprocess
import sys
import os
from pathlib import Path

def run_command(cmd, cwd=None, check=True):
    """Run a shell command and handle errors."""
    print(f"\n▶ Running: {cmd}")
    try:
        result = subprocess.run(
            cmd if sys.platform != "win32" else cmd.replace("source ", ""),
            shell=True,
            cwd=cwd,
            check=check,
            capture_output=True,
            text=True
        )
        if result.stdout:
            print(result.stdout)
        return result
    except subprocess.CalledProcessError as e:
        print(f"✗ Error: {e}")
        if e.stderr:
            print(e.stderr)
        if check:
            sys.exit(1)
        return e

def main():
    agentic_dir = Path(__file__).parent
    venv_dir = agentic_dir / "venv"
    
    print("=" * 60)
    print("HR Agentic System - Virtual Environment Setup")
    print("=" * 60)
    
    # Create virtual environment
    if not venv_dir.exists():
        print(f"\n📦 Creating virtual environment at {venv_dir}...")
        subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)
        print("✓ Virtual environment created")
    else:
        print(f"\n✓ Virtual environment already exists at {venv_dir}")
    
    # Determine activation and pip paths
    if sys.platform == "win32":
        pip_path = venv_dir / "Scripts" / "pip.exe"
        python_path = venv_dir / "Scripts" / "python.exe"
    else:
        pip_path = venv_dir / "bin" / "pip"
        python_path = venv_dir / "bin" / "python"
    
    # Upgrade pip
    print("\n⬆ Upgrading pip...")
    subprocess.run([str(python_path), "-m", "pip", "install", "--upgrade", "pip"], check=True)
    
    # Install requirements
    requirements_file = agentic_dir / "requirements.txt"
    if requirements_file.exists():
        print(f"\n📥 Installing dependencies from {requirements_file}...")
        subprocess.run([str(pip_path), "install", "-r", str(requirements_file)], check=True)
        print("✓ All dependencies installed")
    else:
        print(f"✗ requirements.txt not found at {requirements_file}")
        sys.exit(1)
    
    print("\n" + "=" * 60)
    print("✓ Setup complete!")
    print("=" * 60)
    print(f"\nTo activate the environment:")
    if sys.platform == "win32":
        print(f"  {venv_dir}\\Scripts\\activate")
    else:
        print(f"  source {venv_dir}/bin/activate")
    print(f"\nTo run the server:")
    print(f"  python run.py")

if __name__ == "__main__":
    main()
