# 🧪 Tests — Universal LangGraph Agentic System

## Overview

This folder contains all test suites for the system.
Tests are numbered incrementally and self-contained.
Each test suite lives in its own numbered folder.

---

## Folder Naming Convention

```
tests/
├── README.md                          ← You are here
├── test_001_basic_run/                ← Suite 001: basic pipeline
│   ├── test_code.py                   ← pytest test file
│   └── results.md                     ← Results log (fill after running)
├── test_002_memory_stores/            ← Suite 002: memory layer tests
│   ├── test_code.py
│   └── results.md
├── test_003_skill_loader/             ← Suite 003: skill loading
│   ├── test_code.py
│   └── results.md
└── test_NNN_<description>/            ← Your next suite
    ├── test_code.py
    └── results.md
```

**Numbering Rule:** Always use 3-digit zero-padded numbers: `001`, `002`, ..., `099`, `100`.
Never reuse a number. Never rename existing folders.

---

## Test Categories

| Category | Description | Prefix example |
|----------|-------------|----------------|
| `basic_run` | End-to-end pipeline run | `test_001_basic_run` |
| `memory_*` | Memory store operations | `test_002_memory_stores` |
| `skill_*` | Skill loading/calling | `test_003_skill_loader` |
| `api_*` | HTTP endpoint tests | `test_004_api_endpoints` |
| `tools_*` | Individual tool tests | `test_005_tools` |
| `graph_*` | Graph routing/edges | `test_006_graph_routing` |
| `domain_*` | Domain-specific logic | `test_010_fraud_detection` |

---

## Running Tests

```bash
# Navigate to project root
cd ai/agentic/

# Run ALL tests
pytest tests/ -v

# Run a specific suite
pytest tests/test_001_basic_run/ -v

# Run with print output visible
pytest tests/ -v -s

# Run only fast unit tests (no LLM needed)
pytest tests/ -v -s -k "not Integration and not HTTP"

# Run async tests
pytest tests/ -v --asyncio-mode=auto

# Run with coverage
pytest tests/ -v --cov=. --cov-report=term-missing
```

---

## Environment Setup

```bash
# Copy and fill in .env
cp .env.example .env

# For unit tests only (no LLM needed):
# No special setup required — just install deps

# For integration tests (LLM required):
# Option A — Ollama:
ollama pull qwen2.5:3b

# Option B — Groq:
# Add to .env:  GROQ_KEYS=gsk_key1,gsk_key2,...

# For HTTP/API tests (server must be running):
uvicorn server:app --host 0.0.0.0 --port 8000 --reload
```

**Recommended test `.env` overrides for speed:**
```bash
MAX_ITERATIONS=3
MAX_REFLECTION_LOOPS=1
VECTOR_TOP_K=2
```

---

## Writing a New Test Suite

### 1. Create the folder
```bash
mkdir tests/test_NNN_my_feature
```

### 2. Create `test_code.py`
```python
# tests/test_NNN_my_feature/test_code.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest

# ── Unit tests (no LLM, no server) ──────────────────────────
class TestMyFeature:
    def test_basic(self):
        from my_module import my_function
        result = my_function("input")
        assert result == "expected"
        print(f"\n✅ my_function: {result}")

# ── Integration tests (require LLM) ──────────────────────────
class TestMyFeatureIntegration:
    @pytest.mark.asyncio
    async def test_with_llm(self):
        try:
            from graph import get_graph, load_memory_context
            from state import create_initial_state
            # ... test logic ...
        except Exception as e:
            pytest.skip(f"LLM not available: {e}")

# ── HTTP tests (require server on :8000) ─────────────────────
class TestMyFeatureHTTP:
    @pytest.mark.asyncio
    async def test_endpoint(self):
        try:
            import httpx
            async with httpx.AsyncClient(timeout=60.0) as client:
                r = await client.post("http://localhost:8000/run",
                                      json={"query": "test"})
            assert r.status_code == 200
        except Exception as e:
            pytest.skip(f"Server not running: {e}")
```

### 3. Create `results.md`
```markdown
# Test NNN: My Feature

## Date
YYYY-MM-DD

## Status
⬜ NOT YET RUN

## Test Results
| Test | Status | Duration | Notes |
|------|--------|----------|-------|
| test_basic | ⬜ | - | - |
```

### 4. After running, fill in `results.md`
```markdown
## Status
✅ ALL PASS  (or ❌ FAILURES)

## Test Results
| Test | Status | Duration | Notes |
|------|--------|----------|-------|
| test_basic | ✅ PASS | 0.02s | result matched expected |
```

---

## Test Status Legend

| Symbol | Meaning |
|--------|---------|
| ⬜ | Not yet run |
| ✅ | Pass |
| ❌ | Fail |
| ⚠️ | Skipped (missing dependency) |
| 🔄 | Running / in progress |

---

## Test Isolation Rules

1. **No shared state** — each test must be independent
2. **Use `tmp_path`** — for file-based tests, use pytest's `tmp_path` fixture
3. **Skip gracefully** — use `pytest.skip()` when LLM/server is unavailable
4. **No hardcoded ports** — read from `os.getenv("TEST_BASE_URL", "http://localhost:8000")`
5. **Clean up** — delete test entities/episodes created during tests

---

## CI/CD Integration

```yaml
# .github/workflows/test.yml
- name: Run unit tests
  run: |
    pip install -r requirements.txt
    pytest tests/ -v -k "not Integration and not HTTP" --tb=short
```
