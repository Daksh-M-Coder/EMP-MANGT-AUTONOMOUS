# 🤖 Universal LangGraph Agentic System

A **production-grade, universal multi-agent system** built with LangGraph.
Adapts to any domain — fraud detection, HR, trading, personal assistant — by
changing only config and dropping skill files into `/skills/`.

---

## Architecture

```
                    ┌─────────┐
      User Query ──▶│ PLANNER │  temperature=0.3
                    └────┬────┘
                         │  plan (list of steps)
                    ┌────▼────┐
                    │EXECUTOR │  temperature=0.1  ◀─── loops per step
                    └────┬────┘
                         │  final_answer
                    ┌────▼────┐
                    │REFLECTOR│  temperature=0.2
                    └────┬────┘
                         │
              ┌──────────┼──────────┐
           approved   replan      retry
              │          │          │
            END       PLANNER   EXECUTOR
```

### Memory System
| Layer | Storage | Purpose |
|-------|---------|---------|
| Episodic | `memory/json/episodic.jsonl` + `memory/md/` | Full run history |
| Vector | FAISS index in `memory/vector_index/` | Semantic RAG search |
| Entity | `.json` + `.md` per entity | Structured facts about objects |
| Working | In `AgentState` dict | Scratch space within a run |

---

## Quick Start

### 1. Install dependencies
```bash
cd ai/agentic/
pip install -r requirements.txt
```

### 2. Configure
```bash
cp .env.example .env
# Edit .env — set LLM_PROVIDER=ollama or groq
```

### 3. Pull a model (Ollama)
```bash
ollama pull qwen2.5:3b
# OR: tinyllama, deepseek-r1:1.5b, qwen2.5:7b
```

### 4. Start the server
```bash
uvicorn server:app --host 0.0.0.0 --port 8000 --reload
# API docs: http://localhost:8000/docs
```

### 5. Run a query
```bash
curl -X POST http://localhost:8000/run \
  -H "Content-Type: application/json" \
  -d '{"query": "What is 15% of 2400? Show your work."}'
```

---

## Folder Structure

```
ai/agentic/
├── .env.example          ← Copy to .env and configure
├── config.py             ← All configuration (single source of truth)
├── state.py              ← LangGraph AgentState TypedDict
├── graph.py              ← LangGraph graph assembly + routing
├── planner.py            ← Planner agent node (temp=0.3)
├── executor.py           ← Executor agent node (temp=0.1)
├── reflector.py          ← Reflector agent node (temp=0.2)
├── tools.py              ← Built-in tool definitions
├── skill_loader.py       ← Dynamic skill loader from /skills/
├── logger.py             ← Structured logging (JSON + MD)
├── server.py             ← FastAPI server (all HTTP endpoints)
├── requirements.txt      ← Python dependencies
│
├── skills/               ← Drop .py skill files here (auto-loaded)
│   └── fraud_risk_scorer.py   ← Example domain skill
│
├── memory/
│   ├── episodic_store.py ← JSONL run history
│   ├── vector_store.py   ← FAISS semantic search
│   ├── entity_memory.py  ← Key-value entity facts
│   ├── working_memory.py ← In-run scratch space
│   ├── json/             ← All structured memory files
│   └── md/               ← Human-readable memory files
│
├── ai-req-res-logging/
│   ├── json/             ← Structured LLM call logs (JSONL)
│   └── md/               ← Beautiful markdown LLM call logs
│
└── tests/
    ├── README.md
    └── test_001_basic_pipeline/
        ├── test_code.py
        └── results.md
```

---

## API Reference

All endpoints documented with examples at `/docs` (Swagger UI).

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/run` | Run agent pipeline, get full result |
| `GET` | `/stream` | Stream execution as SSE events |
| `GET` | `/health` | System health + config summary |
| `GET` | `/skills` | List loaded skills |
| `POST` | `/skills/reload` | Hot-reload skills (no restart) |
| `GET` | `/memory/episodic?n=5` | Recent run history |
| `GET` | `/memory/entities` | All entity facts |
| `DELETE` | `/memory/entity/{name}` | Delete an entity |
| `POST` | `/memory/vector/search` | Semantic memory search |
| `GET` | `/logs?date=2025-01-15` | View log files |

---

## Writing a Skill

Create any `.py` file in `/skills/`:

```python
# skills/my_domain_skill.py

SKILL_METADATA = {
    "name":        "my_skill",
    "description": "Does something useful for my domain.",
    "version":     "1.0.0",
    "author":      "Your Name",
}

def run(input: dict) -> dict:
    # input is whatever the agent passes
    result = do_something(input.get("param"))
    return {
        "success": True,
        "result":  result,
        "error":   None,
    }
```

Then either restart the server or call `POST /skills/reload`.
The Executor can call it via the `skill_call` tool:
```
skill_call("my_skill", '{"param": "value"}')
```

---

## Adapting to a New Domain

To use this for a **new project**, only change:

1. **`.env`** — Set `PROJECT_NAME`, `SYSTEM_PROMPT`, `LLM_PROVIDER`
2. **`/skills/`** — Add domain-specific skill files
3. **`config.py`** — Optionally tune temperatures or iteration limits
4. **`state.py`** — Optionally add domain-specific fields to `AgentState`

Everything else — memory, logging, routing, API — works unchanged.

### Example adaptations:

**Fraud Detection:**
```bash
PROJECT_NAME=FraudGuard
SYSTEM_PROMPT=You are a fraud detection AI. Always include a risk score.
```
→ Add `skills/fraud_risk_scorer.py`, `skills/transaction_lookup.py`

**HR Assistant:**
```bash
PROJECT_NAME=HRBot
SYSTEM_PROMPT=You are an HR assistant. Focus on candidate fit and culture.
```
→ Add `skills/resume_parser.py`, `skills/job_matcher.py`

**Trading:**
```bash
PROJECT_NAME=TradeBot
SYSTEM_PROMPT=You are a quantitative analyst. Be precise with numbers.
```
→ Add `skills/price_fetcher.py`, `skills/indicator_calculator.py`

---

## LLM Support

| Provider | Models | Config |
|----------|--------|--------|
| **Ollama** (local) | `qwen2.5:3b`, `qwen2.5:7b`, `tinyllama`, `deepseek-r1:1.5b` | `LLM_PROVIDER=ollama` |
| **Groq** (cloud) | `llama-3.3-70b-versatile` | `LLM_PROVIDER=groq`, `GROQ_KEYS=key1,key2,...` |

Groq supports **4-8 API key rotation** (round-robin, thread-safe).

---

## Running Tests

```bash
# Unit tests (no LLM needed)
pytest tests/test_001_basic_pipeline/ -v -s -k "not Integration"

# All tests (LLM required)
pytest tests/ -v -s
```

---

## Logs

Every LLM call is logged to two formats simultaneously:

**JSON** (`ai-req-res-logging/json/YYYY-MM-DD.jsonl`):
```json
{"log_id": "a3f2b1c0", "timestamp": "...", "agent": "planner",
 "prompt": "...", "response": "...", "latency_ms": 342.5}
```

**Markdown** (`ai-req-res-logging/md/YYYY-MM-DD.md`):
```markdown
## 🤖 LLM Call `a3f2b1c0` — PLANNER
| Field | Value |
|-------|-------|
| Latency | 342.5 ms |
...
### 📥 Prompt
### 📤 Raw Response
### ✅ Parsed Output
```
