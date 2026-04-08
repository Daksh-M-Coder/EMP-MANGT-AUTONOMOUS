# Test Suite 001: Basic Run

## Purpose
End-to-end coverage of every core component:
config, state, working memory, entity memory, episodic store,
skill loader (Python + Markdown), tools, vector store, graph, and HTTP API.

## How to Run

```bash
# From ai/agentic/

# Fast — unit tests only (no LLM, no server needed):
pytest tests/test_001_basic_run/ -v -s -k "not Integration and not HTTP"

# Full — with LLM (Ollama must be running):
pytest tests/test_001_basic_run/ -v -s

# Full — with HTTP server:
uvicorn server:app --port 8000 &
pytest tests/test_001_basic_run/ -v -s
```

## Status
⬜ NOT YET RUN

---

## Expected Results (Unit Tests — no LLM needed)

| Class | Test | Expected |
|-------|------|----------|
| TestConfig | test_config_loads | ✅ |
| TestConfig | test_temperatures | ✅ |
| TestConfig | test_groq_key_rotator_round_robin | ✅ |
| TestConfig | test_groq_rotator_error_tracking | ✅ |
| TestConfig | test_db_url_masking | ✅ |
| TestConfig | test_paths_exist | ✅ |
| TestState | test_create_initial_state | ✅ |
| TestState | test_started_at_is_set | ✅ |
| TestState | test_append_semantics | ✅ |
| TestWorkingMemory | test_set_get | ✅ |
| TestWorkingMemory | test_append_to_list | ✅ |
| TestWorkingMemory | test_increment | ✅ |
| TestWorkingMemory | test_snapshot | ✅ |
| TestWorkingMemory | test_delete_and_clear | ✅ |
| TestWorkingMemory | test_format_for_prompt | ✅ |
| TestEntityMemory | test_full_crud | ✅ |
| TestEntityMemory | test_load_all | ✅ |
| TestEpisodicStore | test_save_and_retrieve | ✅ |
| TestEpisodicStore | test_get_by_session | ✅ |
| TestEpisodicStore | test_search_by_query | ✅ |
| TestEpisodicStore | test_format_for_prompt | ✅ |
| TestSkillLoader | test_ensure_example_skills_created | ✅ |
| TestSkillLoader | test_python_skill_call | ✅ |
| TestSkillLoader | test_md_skill_context | ✅ |
| TestSkillLoader | test_fraud_skill | ✅ |
| TestTools | test_calculator_basic | ✅ |
| TestTools | test_calculator_percent | ✅ |
| TestTools | test_calculator_math_funcs | ✅ |
| TestTools | test_calculator_error | ✅ |
| TestTools | test_current_datetime | ✅ |
| TestTools | test_get_all_tools_list | ✅ |
| TestTools | test_tool_descriptions | ✅ |
| TestVectorStore | test_add_and_search | ✅ (needs faiss-cpu) |
| TestVectorStore | test_empty_search_returns_empty | ✅ (needs faiss-cpu) |
| TestGraph | test_graph_compiles | ✅ (needs langgraph) |
| TestGraph | test_load_memory_context | ✅ |

## Integration Tests (require LLM)

| Class | Test | Expected |
|-------|------|----------|
| TestIntegration | test_calculator_task | ⚠️ Requires Ollama/Groq |
| TestIntegration | test_datetime_task | ⚠️ Requires Ollama/Groq |

## HTTP Tests (require server)

| Class | Test | Expected |
|-------|------|----------|
| TestHTTPEndpoints | test_health_endpoint | ⚠️ Requires server |
| TestHTTPEndpoints | test_skills_endpoint | ⚠️ Requires server |
| TestHTTPEndpoints | test_run_endpoint | ⚠️ Requires server + LLM |
| TestHTTPEndpoints | test_memory_endpoints | ⚠️ Requires server |

---

## Actual Results
_Fill in after running tests_

**Date:** ___________
**Duration:** ___________
**Pass/Fail:** ___ / ___

```
paste pytest output here
```
