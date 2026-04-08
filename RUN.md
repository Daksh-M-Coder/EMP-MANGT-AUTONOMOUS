# HR Agentic System - Quick Start Guide

## 🚀 WINDOWS ONE-CLICK START

Simply double-click **`start.bat`**

This will:
1. ✓ Check Python, Node.js, Ollama installations
2. ✓ Create virtual environment (if missing)
3. ✓ Install Python dependencies
4. ✓ Pull Ollama models (if missing)
5. ✓ Open 3 separate windows with **real-time logs**
6. ✓ Show this status window to monitor everything

### What Opens:
- **Window 1 (Cyan)**: Agentic AI Server - http://localhost:8000
- **Window 2 (Green)**: Node Backend - http://localhost:3000  
- **Window 3 (Magenta)**: React Frontend - http://localhost:5173
- **Window 4 (This one)**: Status monitor - press any key to STOP all

---

## 📋 Mac/Linux Alternative

```bash
python3 start_all.py
```

---

## 🔧 First-Time Setup (Manual)

If the .bat fails, do manual setup:

### 1. Create Virtual Environment
```bash
cd agentic
python setup_venv.py
```

### 2. Copy Environment File
```bash
copy .env.example .env   # Windows
cp .env.example .env    # Mac/Linux
```

### 3. Pull Ollama Models
```bash
ollama pull qwen2.5-coder:1.5b
ollama pull nemotron-mini
```

---

## 🌐 Service URLs

| Service | URL | Description |
|---------|-----|-------------|
| React Frontend | http://localhost:5173 | Main HRMS UI with AI Chat |
| Node Backend | http://localhost:3000 | REST API + Draft management |
| Agentic AI | http://localhost:8000 | LangGraph AI Server |
| API Docs | http://localhost:8000/docs | Swagger UI |

---

## � Project Files

```
EMPLOYEE DATA MGT SYS/
├── start.bat              ← ⭐ ONE CLICK WINDOWS LAUNCHER
├── agentic/
│   ├── venv/              # Python virtual env (auto-created)
│   ├── setup_venv.py      # Setup script
│   ├── run.py             # Run agentic only
│   └── .env               # Your config (edit this)
├── backend/               # Node.js + SQLite
├── frontend/              # React + Vite
└── start_all.py           # Mac/Linux launcher
```

---

## 🛠️ Troubleshooting

| Problem | Solution |
|---------|----------|
| "Python not found" | Install from python.org |
| "npm not found" | Install Node.js from nodejs.org |
| "OLLAMA not found" | Install from ollama.com |
| Ports in use | Change in config files or restart PC |
| Import errors | Run `python agentic/setup_venv.py` |

---

## 💡 Tips

- **Hot reload enabled** - Code changes auto-restart services
- **3 windows = 3 logs** - Each service shows real-time output
- **Close status window** - Press any key in the main window to stop all
- **Ollama optional** - Cloud APIs work without it (add keys to .env)
