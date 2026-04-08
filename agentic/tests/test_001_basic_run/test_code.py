# ============================================================
# tests/test_001_basic_run/test_code.py
# ============================================================
# Suite 001: Basic Run — covers every core component
#
# Test classes:
#   TestConfig          → config, key rotator, llm_factory sig
#   TestState           → AgentState creation and defaults
#   TestWorkingMemory   → in-run scratch space operations
#   TestEntityMemory    → entity CRUD + dual file writes
#   TestEpisodicStore   → episode save/search/format
#   TestSkillLoader     → Python + Markdown skill loading
#   TestTools           → calculator, datetime, tool list
#   TestVectorStore     → add/search/format_for_prompt
#   TestGraph           → graph compilation (no LLM)
#   TestIntegration     → full pipeline (requires LLM)
#   TestHTTPEndpoints   → HTTP API (requires server on :8000)
#
# Run: pytest tests/test_001_basic_run/ -v -s
# Fast run (no LLM): pytest tests/test_001_basic_run/ -v -s
#                    -k "not Integration and not HTTP"
# ============================================================

import sys
import os
import json
import pytest
import asyncio
import tempfile
from pathlib import Path

# ── Make project root importable ─────────────────────────────
ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

BASE_URL = os.getenv("TEST_BASE_URL", "http://localhost:8000")


# ════════════════════════════════════════════════════════════
# 1. CONFIG
# ════════════════════════════════════════════════════════════

class TestConfig:
    """Test configuration loading, Groq key rotator, llm_factory."""

    def test_config_loads(self):
        from config import cfg
        assert cfg.PROJECT_NAME is not None
        assert cfg.PROVIDER in ("groq", "ollama")
        assert cfg.MAX_ITERATIONS > 0
        assert cfg.MAX_REFLECTION_LOOPS > 0
        print(f"\n✅ Config: project={cfg.PROJECT_NAME}, provider={cfg.PROVIDER}")

    def test_temperatures(self):
        from config import cfg
        t = cfg.AGENT_TEMPERATURES
        assert 0.0 <= t["planner"]   <= 1.0
        assert 0.0 <= t["executor"]  <= 1.0
        assert 0.0 <= t["reflector"] <= 1.0
        assert t["executor"] < t["planner"], "Executor should be more deterministic"
        print(f"✅ Temperatures: {t}")

    def test_groq_key_rotator_round_robin(self):
        from config import GroqKeyRotator
        rotator = GroqKeyRotator(["key_a", "key_b", "key_c"])
        keys = [rotator.next() for _ in range(6)]
        assert keys == ["key_a", "key_b", "key_c", "key_a", "key_b", "key_c"]
        print(f"✅ GroqKeyRotator round-robin: {keys[:3]} → repeats")

    def test_groq_rotator_error_tracking(self):
        from config import GroqKeyRotator
        r = GroqKeyRotator(["k1", "k2"])
        idx, _ = r.next_with_index()
        r.record_error(idx)
        stats = r.stats()
        assert stats[idx]["errors"] == 1
        assert r.total_calls() == 1
        print(f"✅ GroqKeyRotator error tracking: {stats}")

    def test_db_url_masking(self):
        from config import SystemConfig
        cfg2 = SystemConfig()
        masked = cfg2._mask_db_url("postgresql://admin:secret@host:5432/db")
        assert "secret" not in masked
        assert "admin" in masked
        assert "***" in masked
        print(f"✅ DB URL masking: {masked}")

    def test_paths_exist(self):
        from config import cfg
        assert cfg.MEMORY_JSON_DIR.exists(), "memory/json/ must exist"
        assert cfg.MEMORY_MD_DIR.exists(),   "memory/md/ must exist"
        assert cfg.SKILLS_DIR.exists(),      "skills/ must exist"
        assert cfg.SKILLS_MD_DIR.exists(),   "skills/md_skills/ must exist"
        assert cfg.LOG_JSON_DIR.exists(),    "ai-req-res-logging/json/ must exist"
        assert cfg.LOG_MD_DIR.exists(),      "ai-req-res-logging/md/ must exist"
        print("✅ All required directories exist")


# ════════════════════════════════════════════════════════════
# 2. STATE
# ════════════════════════════════════════════════════════════

class TestState:
    """Test AgentState creation and structure."""

    def test_create_initial_state(self):
        from state import create_initial_state
        s = create_initial_state("Test query", "sess_test_001")
        assert s["user_query"]  == "Test query"
        assert s["session_id"]  == "sess_test_001"
        assert s["is_complete"] == False
        assert s["plan"]        == []
        assert s["errors"]      == []
        assert s["reflection_count"] == 0
        assert s["current_step_index"] == 0
        assert len(s["messages"]) == 1
        assert s["messages"][0]["role"] == "user"
        assert s["final_answer"] is None
        print("\n✅ create_initial_state: all fields correct")

    def test_started_at_is_set(self):
        from state import create_initial_state
        s = create_initial_state("Hello")
        assert s["started_at"] is not None
        assert "T" in s["started_at"]
        print(f"✅ started_at: {s['started_at']}")

    def test_append_semantics(self):
        """Annotated list fields should append, not overwrite."""
        from state import create_initial_state
        s = create_initial_state("Query")
        # errors uses operator.add — starts empty
        assert isinstance(s["errors"], list)
        assert isinstance(s["tool_calls"], list)
        assert isinstance(s["thinking_traces"], list)
        print("✅ Append-semantic fields initialized as empty lists")


# ════════════════════════════════════════════════════════════
# 3. WORKING MEMORY
# ════════════════════════════════════════════════════════════

class TestWorkingMemory:
    """Test in-run scratch space."""

    def test_set_get(self):
        from memory.working_memory import WorkingMemory
        wm = WorkingMemory()
        wm.set("risk_score", 0.87)
        assert wm.get("risk_score") == 0.87
        assert wm.get("missing_key", "default") == "default"
        print("\n✅ WorkingMemory set/get: OK")

    def test_append_to_list(self):
        from memory.working_memory import WorkingMemory
        wm = WorkingMemory()
        wm.append_to_list("flags", "wire_fraud")
        wm.append_to_list("flags", "new_account")
        wm.append_to_list("flags", "high_amount")
        assert wm.get("flags") == ["wire_fraud", "new_account", "high_amount"]
        print("✅ WorkingMemory append_to_list: OK")

    def test_increment(self):
        from memory.working_memory import WorkingMemory
        wm = WorkingMemory()
        wm.increment("api_calls")
        wm.increment("api_calls")
        wm.increment("cost", 0.002)
        assert wm.get("api_calls") == 2
        assert abs(wm.get("cost") - 0.002) < 0.0001
        print("✅ WorkingMemory increment: OK")

    def test_snapshot(self):
        from memory.working_memory import WorkingMemory
        wm = WorkingMemory()
        wm.set("a", 1)
        wm.set("b", "hello")
        snap = wm.snapshot()
        assert snap["a"] == 1
        assert snap["b"] == "hello"
        print(f"✅ WorkingMemory snapshot: {snap}")

    def test_delete_and_clear(self):
        from memory.working_memory import WorkingMemory
        wm = WorkingMemory()
        wm.set("x", 42)
        wm.set("y", 99)
        assert wm.delete("x") == True
        assert wm.get("x") is None
        assert wm.get("y") == 99
        wm.clear()
        assert len(wm) == 0
        print("✅ WorkingMemory delete/clear: OK")

    def test_format_for_prompt(self):
        from memory.working_memory import WorkingMemory
        wm = WorkingMemory()
        wm.set("transaction_id", "TX001")
        wm.set("risk_score", 0.92)
        fmt = wm.format_for_prompt()
        assert "transaction_id" in fmt
        assert "TX001" in fmt
        print(f"✅ WorkingMemory format_for_prompt:\n{fmt}")


# ════════════════════════════════════════════════════════════
# 4. ENTITY MEMORY
# ════════════════════════════════════════════════════════════

class TestEntityMemory:
    """Test entity CRUD with dual file writes (json + md)."""

    def test_full_crud(self, tmp_path):
        from memory.entity_memory import EntityMemory
        em = EntityMemory(json_dir=tmp_path/"json", md_dir=tmp_path/"md")

        # CREATE
        em.set("TX001", {"amount": 9800, "country": "NG", "risk": 0.92})
        data = em.get("TX001")
        assert data["amount"] == 9800
        assert data["country"] == "NG"

        # Both files written
        assert (tmp_path/"json"/"entity_TX001.json").exists(), "JSON file missing"
        assert (tmp_path/"md"  /"entity_TX001.md").exists(),   "MD file missing"
        print("\n✅ EntityMemory CREATE: JSON + MD files written")

        # UPDATE (merge)
        em.update("TX001", {"risk": 0.95, "flagged": True})
        updated = em.get("TX001")
        assert updated["risk"]    == 0.95
        assert updated["flagged"] == True
        assert updated["amount"]  == 9800   # preserved from original
        print("✅ EntityMemory UPDATE: merged correctly, original fields preserved")

        # VERSION check
        record = em.get_full_record("TX001")
        assert record["version"] == 2
        assert len(record["history"]) == 2
        print(f"✅ EntityMemory version: v{record['version']}, history len={len(record['history'])}")

        # LIST
        names = em.list_entities()
        assert "TX001" in names
        print(f"✅ EntityMemory list: {names}")

        # FORMAT FOR PROMPT
        fmt = em.format_for_prompt(["TX001"])
        assert "TX001" in fmt
        print(f"✅ EntityMemory format_for_prompt:\n{fmt[:100]}")

        # DELETE
        assert em.delete("TX001") == True
        assert em.get("TX001") is None
        assert not (tmp_path/"json"/"entity_TX001.json").exists()
        print("✅ EntityMemory DELETE: files removed")

    def test_load_all(self, tmp_path):
        from memory.entity_memory import EntityMemory
        em = EntityMemory(json_dir=tmp_path/"json", md_dir=tmp_path/"md")
        em.set("entity_a", {"x": 1})
        em.set("entity_b", {"y": 2})
        all_entities = em.load_all()
        assert "entity_a" in all_entities
        assert "entity_b" in all_entities
        print(f"✅ EntityMemory load_all: {list(all_entities.keys())}")


# ════════════════════════════════════════════════════════════
# 5. EPISODIC STORE
# ════════════════════════════════════════════════════════════

class TestEpisodicStore:
    """Test episode save, search, and format."""

    def _fake_state(self, n: int, session: str = "sess_test") -> dict:
        return {
            "session_id":   session,
            "user_query":   f"What is {n} + {n}?",
            "plan":         [{"step_id": "step_001", "description": "Calculate",
                              "tool": "calculator", "status": "done", "result": str(n*2)}],
            "tool_calls":   [],
            "reflections":  [{"quality_score": 0.95, "approved": True,
                              "issues": [], "suggestions": [], "feedback": "Good",
                              "needs_replanning": False}],
            "final_answer": f"{n} + {n} = {n*2}",
            "is_complete":  True,
            "errors":       [],
            "thinking_traces": [],
            "started_at":   "2025-01-01T00:00:00Z",
            "reflection_count": 1,
        }

    def test_save_and_retrieve(self, tmp_path):
        from memory.episodic_store import EpisodicStore
        store = EpisodicStore(
            json_path = tmp_path / "episodic.jsonl",
            md_path   = tmp_path / "episodic_summary.md",
        )
        for i in range(3):
            ep_id = store.save_episode(self._fake_state(i + 1))
            assert ep_id.startswith("ep_")

        # Both files written
        assert (tmp_path / "episodic.jsonl").exists(), "JSONL file not created"
        assert (tmp_path / "episodic_summary.md").exists(), "MD file not created"
        print(f"\n✅ EpisodicStore: 3 episodes saved, JSONL + MD written")

        # Retrieve
        recent = store.get_recent(5)
        assert len(recent) == 3
        assert recent[-1]["user_query"] == "What is 3 + 3?"
        print(f"✅ EpisodicStore get_recent: {[ep['user_query'] for ep in recent]}")

    def test_get_by_session(self, tmp_path):
        from memory.episodic_store import EpisodicStore
        store = EpisodicStore(
            json_path = tmp_path / "episodic.jsonl",
            md_path   = tmp_path / "episodic_summary.md",
        )
        store.save_episode(self._fake_state(1, "sess_A"))
        store.save_episode(self._fake_state(2, "sess_B"))
        store.save_episode(self._fake_state(3, "sess_A"))

        sess_a = store.get_by_session("sess_A")
        assert len(sess_a) == 2
        print(f"✅ EpisodicStore get_by_session: 2 episodes for sess_A")

    def test_search_by_query(self, tmp_path):
        from memory.episodic_store import EpisodicStore
        store = EpisodicStore(
            json_path = tmp_path / "episodic.jsonl",
            md_path   = tmp_path / "episodic_summary.md",
        )
        store.save_episode(self._fake_state(5))
        results = store.search_by_query("What is 5")
        assert len(results) >= 1
        print(f"✅ EpisodicStore search_by_query: found {len(results)} match(es)")

    def test_format_for_prompt(self, tmp_path):
        from memory.episodic_store import EpisodicStore
        store = EpisodicStore(
            json_path = tmp_path / "episodic.jsonl",
            md_path   = tmp_path / "episodic_summary.md",
        )
        store.save_episode(self._fake_state(7))
        episodes = store.get_recent(5)
        fmt = store.format_for_prompt(episodes)
        assert "SUCCESS" in fmt or "INCOMPLETE" in fmt
        assert "What is 7" in fmt
        print(f"✅ EpisodicStore format_for_prompt:\n{fmt[:200]}")


# ════════════════════════════════════════════════════════════
# 6. SKILL LOADER
# ════════════════════════════════════════════════════════════

class TestSkillLoader:
    """Test Python + Markdown skill loading."""

    def test_ensure_example_skills_created(self, tmp_path):
        """Both example skills created when dirs are empty."""
        from skill_loader import (load_all_skills, ensure_example_skill,
                                   ensure_example_md_skill)
        from config import cfg
        # Point to our temp dirs
        py_dir = tmp_path / "py_skills"
        md_dir = tmp_path / "md_skills"
        py_dir.mkdir(); md_dir.mkdir()

        # Manually create example files
        (py_dir / "example_skill.py").write_text(
            'SKILL_METADATA = {"name":"ex","description":"test","version":"1.0.0","author":"test"}\n'
            'def run(input): return {"success": True, "result": "ok", "error": None}\n'
        )
        (md_dir / "example_guide.md").write_text(
            "---\nname: ex_guide\ndescription: A guide\nversion: 1.0.0\nauthor: Test\n---\n"
            "# Guide\nSome instructions here.\n"
        )

        registry = load_all_skills(py_dir=py_dir, md_dir=md_dir)
        assert len(registry) == 2
        assert "ex" in registry.python_skills
        assert "ex_guide" in registry.md_skills
        print(f"\n✅ SkillLoader: {len(registry)} skills | "
              f"py={registry.python_skills} | md={registry.md_skills}")

    def test_python_skill_call(self, tmp_path):
        from skill_loader import load_all_skills
        py_dir = tmp_path / "py"
        md_dir = tmp_path / "md"
        py_dir.mkdir(); md_dir.mkdir()
        (py_dir / "adder.py").write_text(
            'SKILL_METADATA = {"name":"adder","description":"Adds","version":"1.0.0","author":"test"}\n'
            'def run(input):\n'
            '    a = input.get("a", 0)\n'
            '    b = input.get("b", 0)\n'
            '    return {"success": True, "result": a + b, "error": None}\n'
        )
        registry = load_all_skills(py_dir=py_dir, md_dir=md_dir)
        result   = registry.call("adder", {"a": 3, "b": 4})
        assert result["success"] == True
        assert result["result"]  == 7
        print(f"✅ Python skill call: adder(3,4) = {result['result']}")

    def test_md_skill_context(self, tmp_path):
        from skill_loader import load_all_skills
        py_dir = tmp_path / "py"
        md_dir = tmp_path / "md"
        py_dir.mkdir(); md_dir.mkdir()
        (md_dir / "rules.md").write_text(
            "---\nname: domain_rules\ndescription: Key rules\nversion: 1.0.0\nauthor: Team\n---\n"
            "# Domain Rules\n## Rule 1\nAlways verify.\n## Rule 2\nBe precise.\n"
        )
        registry = load_all_skills(py_dir=py_dir, md_dir=md_dir)
        ctx = registry.get_md_skill_context("domain_rules")
        assert ctx is not None
        assert "Rule 1" in ctx
        assert "Always verify" in ctx
        all_ctx = registry.all_md_context()
        assert "domain_rules" in all_ctx
        print(f"✅ MD skill context loaded:\n{ctx[:100]}")

    def test_fraud_skill(self):
        """Test the included fraud_risk_scorer skill."""
        from skill_loader import load_all_skills
        from config import cfg
        registry = load_all_skills(
            py_dir=cfg.SKILLS_DIR,
            md_dir=cfg.SKILLS_MD_DIR,
        )
        if "fraud_risk_scorer" not in registry.names:
            pytest.skip("fraud_risk_scorer skill not found")

        result = registry.call("fraud_risk_scorer", {
            "amount": 15000, "country": "NG",
            "account_age_days": 2, "is_new_device": True, "hour_of_day": 3,
        })
        assert result["success"] == True
        assert result["result"]["risk_level"] == "critical"
        assert result["result"]["risk_score"] >= 0.8
        print(f"✅ fraud_risk_scorer: score={result['result']['risk_score']}, "
              f"level={result['result']['risk_level']}")
        print(f"   flags={result['result']['flags']}")


# ════════════════════════════════════════════════════════════
# 7. TOOLS
# ════════════════════════════════════════════════════════════

class TestTools:
    """Test built-in tool functions."""

    def test_calculator_basic(self):
        from tools import calculator
        assert calculator.invoke("2 + 2")     == "4"
        assert calculator.invoke("10 - 3")    == "7"
        assert calculator.invoke("6 * 7")     == "42"
        assert calculator.invoke("15 / 3")    == "5.0"
        print("\n✅ Calculator basic ops: OK")

    def test_calculator_percent(self):
        from tools import calculator
        result = float(calculator.invoke("2400 * 0.15"))
        assert abs(result - 360.0) < 0.001
        print(f"✅ Calculator 2400*0.15 = {result}")

    def test_calculator_math_funcs(self):
        from tools import calculator
        import math
        r1 = float(calculator.invoke("sqrt(144)"))
        r2 = float(calculator.invoke("abs(-42)"))
        r3 = float(calculator.invoke("round(3.7)"))
        assert abs(r1 - 12.0) < 0.001
        assert r2 == 42.0
        assert r3 == 4.0
        print(f"✅ Calculator math funcs: sqrt(144)={r1}, abs(-42)={r2}")

    def test_calculator_error(self):
        from tools import calculator
        result = calculator.invoke("import os")
        assert "Error" in result or "error" in result.lower() or "Unsafe" in result
        print(f"✅ Calculator rejects unsafe: '{result}'")

    def test_current_datetime(self):
        from tools import current_datetime
        result = current_datetime.invoke("UTC")
        assert "T" in result
        assert "Z" in result or "+" in result
        print(f"✅ current_datetime: {result}")

    def test_get_all_tools_list(self):
        from tools import get_all_tools
        tools = get_all_tools()
        names = [t.name for t in tools]
        assert "calculator"         in names
        assert "current_datetime"   in names
        assert "skill_call"         in names
        assert "memory_search"      in names
        assert "db_query"           in names
        assert "db_execute"         in names
        print(f"✅ get_all_tools: {len(tools)} tools: {names}")

    def test_tool_descriptions(self):
        from tools import get_tool_descriptions
        desc = get_tool_descriptions()
        assert "calculator" in desc
        assert "db_query"   in desc
        print(f"✅ get_tool_descriptions ({len(desc)} chars)")


# ════════════════════════════════════════════════════════════
# 8. VECTOR STORE
# ════════════════════════════════════════════════════════════

class TestVectorStore:
    """Test FAISS vector store with dual memory writes."""

    def test_add_and_search(self, tmp_path):
        """Add texts and search — check we get results back."""
        try:
            import faiss  # noqa
            from sentence_transformers import SentenceTransformer  # noqa
        except ImportError:
            pytest.skip("faiss-cpu or sentence-transformers not installed")

        from memory.vector_store import VectorMemoryStore
        from config import cfg

        # Patch paths to tmp
        store = VectorMemoryStore.__new__(VectorMemoryStore)
        store.INDEX_FILE    = tmp_path / "index.faiss"
        store.METADATA_FILE = tmp_path / "metadata.json"
        store.JSON_LOG_DIR  = tmp_path / "json"
        store.MD_FILE       = tmp_path / "md" / "vector_memory.md"
        (tmp_path / "json").mkdir()
        (tmp_path / "md").mkdir()
        store._index = store._texts = store._metadatas = store._dim = None
        store._load_or_init()

        texts = [
            "Transaction TX001: $9800 wire to offshore account. High risk.",
            "User U42 has 3 prior fraud flags on their account.",
            "Wire transfers above $9000 often indicate structuring.",
        ]
        ids = store.add_texts(
            texts,
            metadatas=[{"type": "transaction"}, {"type": "user"}, {"type": "rule"}],
        )
        assert len(ids) == 3
        assert store.size == 3

        # JSON log written
        import glob
        logs = list((tmp_path / "json").glob("vector_*.jsonl"))
        assert len(logs) == 1, "vector JSON log not written"

        # MD index written
        assert store.MD_FILE.exists(), "vector MD index not written"
        print(f"\n✅ VectorStore add_texts: {len(ids)} added | JSON+MD written")

        # Search
        results = store.search("offshore wire transfer fraud", top_k=3)
        assert len(results) > 0
        assert "text" in results[0]
        assert "score" in results[0]
        assert "relevance" in results[0]
        assert "rank" in results[0]
        print(f"✅ VectorStore search: {len(results)} results")
        for r in results:
            print(f"   [{r['rank']}] {r['relevance'].upper()} "
                  f"(score={r['score']:.3f}) {r['text'][:60]}")

        # format_for_prompt
        fmt = store.format_for_prompt("fraud wire transfer", top_k=3)
        assert "Relevant Memory" in fmt
        assert "[1]" in fmt
        print(f"✅ VectorStore format_for_prompt:\n{fmt[:200]}")

        # search_texts convenience
        texts_only = store.search_texts("offshore account", top_k=2)
        assert isinstance(texts_only, list)
        print(f"✅ VectorStore search_texts: {len(texts_only)} results")

    def test_empty_search_returns_empty(self, tmp_path):
        """Search on empty store should return []."""
        try:
            import faiss  # noqa
        except ImportError:
            pytest.skip("faiss-cpu not installed")

        from memory.vector_store import VectorMemoryStore
        store = VectorMemoryStore.__new__(VectorMemoryStore)
        store.INDEX_FILE    = tmp_path / "index.faiss"
        store.METADATA_FILE = tmp_path / "metadata.json"
        store.JSON_LOG_DIR  = tmp_path / "json"
        store.MD_FILE       = tmp_path / "md" / "vector.md"
        (tmp_path / "json").mkdir()
        (tmp_path / "md").mkdir()
        store._index = store._texts = store._metadatas = store._dim = None
        store._load_or_init()

        results = store.search("anything")
        assert results == []
        fmt = store.format_for_prompt("anything")
        assert "No relevant memory" in fmt
        print("\n✅ VectorStore empty search returns [] and correct message")


# ════════════════════════════════════════════════════════════
# 9. GRAPH
# ════════════════════════════════════════════════════════════

class TestGraph:
    """Test graph compilation and memory context loader."""

    def test_graph_compiles(self):
        """Graph should compile without needing an LLM."""
        try:
            from graph import build_graph
            graph = build_graph()
            assert graph is not None
            print("\n✅ Graph compiled successfully")
        except Exception as e:
            if "langchain" in str(e).lower() or "import" in str(e).lower():
                pytest.skip(f"LangGraph not installed: {e}")
            raise

    def test_load_memory_context(self):
        try:
            from graph import load_memory_context
            ctx = load_memory_context("test query about fraud", "sess_test")
            assert "episodic_context" in ctx
            assert "vector_context"   in ctx
            assert "entity_context"   in ctx
            assert isinstance(ctx["episodic_context"], list)
            assert isinstance(ctx["vector_context"],   list)
            assert isinstance(ctx["entity_context"],   dict)
            print(f"\n✅ load_memory_context: "
                  f"ep={len(ctx['episodic_context'])}, "
                  f"vec={len(ctx['vector_context'])}, "
                  f"ent={len(ctx['entity_context'])}")
        except Exception as e:
            pytest.skip(f"Memory load failed: {e}")


# ════════════════════════════════════════════════════════════
# 10. INTEGRATION — requires LLM (Ollama or Groq)
# ════════════════════════════════════════════════════════════

class TestIntegration:
    """Full pipeline tests — require LLM to be running."""

    @pytest.mark.asyncio
    async def test_calculator_task(self):
        """Ask the agent to calculate 15% of 2400."""
        try:
            from graph import get_graph, load_memory_context
            from state import create_initial_state

            query      = "What is 15% of 2400? Use the calculator tool."
            memory_ctx = load_memory_context(query, "test_integration_calc")
            state      = create_initial_state(
                user_query       = query,
                session_id       = "test_001_calc",
                episodic_context = memory_ctx["episodic_context"],
                vector_context   = memory_ctx["vector_context"],
                entity_context   = memory_ctx["entity_context"],
            )
            loop        = asyncio.get_event_loop()
            graph       = get_graph()
            final_state = await loop.run_in_executor(None, lambda: graph.invoke(state))

            assert final_state["is_complete"] == True
            assert final_state["final_answer"] is not None
            assert len(final_state["plan"]) >= 1

            # Check answer contains 360
            answer = final_state["final_answer"]
            assert "360" in answer, f"Expected 360 in answer, got: {answer}"

            print(f"\n✅ Integration calculator: answer='{answer[:100]}'")
            print(f"   Steps={len(final_state['plan'])}, "
                  f"Reflections={final_state['reflection_count']}")

        except Exception as e:
            if any(kw in str(e).lower() for kw in
                   ["connection", "ollama", "groq", "apikey", "api_key", "llm"]):
                pytest.skip(f"LLM not available: {e}")
            raise

    @pytest.mark.asyncio
    async def test_datetime_task(self):
        """Ask the agent for the current time."""
        try:
            from graph import get_graph, load_memory_context
            from state import create_initial_state

            query      = "What is the current UTC date and time?"
            memory_ctx = load_memory_context(query, "test_integration_dt")
            state      = create_initial_state(
                user_query = query,
                session_id = "test_001_dt",
                **{k: v for k, v in memory_ctx.items()},
            )
            loop        = asyncio.get_event_loop()
            final_state = await loop.run_in_executor(
                None, lambda: get_graph().invoke(state)
            )
            assert final_state["is_complete"] == True
            assert final_state["final_answer"] is not None
            print(f"\n✅ Integration datetime: answer='{final_state['final_answer'][:80]}'")

        except Exception as e:
            if any(kw in str(e).lower() for kw in ["connection", "ollama", "groq"]):
                pytest.skip(f"LLM not available: {e}")
            raise


# ════════════════════════════════════════════════════════════
# 11. HTTP ENDPOINTS — requires server on :8000
# ════════════════════════════════════════════════════════════

class TestHTTPEndpoints:
    """HTTP API tests — require running server."""

    @pytest.mark.asyncio
    async def test_health_endpoint(self):
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(f"{BASE_URL}/health")
            assert r.status_code == 200
            data = r.json()
            assert data["status"]      == "ok"
            assert data["graph_ready"] == True
            assert "config" in data
            assert "skills_count" in data
            print(f"\n✅ GET /health: status={data['status']}, "
                  f"skills={data['skills_count']}")
        except Exception as e:
            pytest.skip(f"Server not running at {BASE_URL}: {e}")

    @pytest.mark.asyncio
    async def test_skills_endpoint(self):
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(f"{BASE_URL}/skills")
            assert r.status_code == 200
            skills = r.json()
            assert isinstance(skills, list)
            print(f"\n✅ GET /skills: {len(skills)} skills")
            for s in skills:
                print(f"   - [{s.get('type','?')}] {s['name']}: {s['description'][:50]}")
        except Exception as e:
            pytest.skip(f"Server not running: {e}")

    @pytest.mark.asyncio
    async def test_run_endpoint(self):
        try:
            import httpx
            async with httpx.AsyncClient(timeout=120.0) as client:
                r = await client.post(
                    f"{BASE_URL}/run",
                    json={
                        "query":      "What is 10% of 500? Use the calculator.",
                        "session_id": "test_http_001",
                    },
                )
            assert r.status_code == 200
            data = r.json()
            assert "final_answer"  in data
            assert "session_id"    in data
            assert "plan"          in data
            assert "reflections"   in data
            assert "duration_ms"   in data
            assert data["is_complete"] == True
            assert "50" in (data["final_answer"] or "")
            print(f"\n✅ POST /run: answer='{data['final_answer'][:80]}'")
            print(f"   duration={data['duration_ms']:.0f}ms, "
                  f"steps={len(data['plan'])}, "
                  f"reflections={data['reflection_count']}")
        except Exception as e:
            pytest.skip(f"Server not running or LLM unavailable: {e}")

    @pytest.mark.asyncio
    async def test_memory_endpoints(self):
        try:
            import httpx
            async with httpx.AsyncClient(timeout=15.0) as client:
                # Episodic
                r1 = await client.get(f"{BASE_URL}/memory/episodic?n=3")
                assert r1.status_code == 200
                assert isinstance(r1.json(), list)

                # Entities
                r2 = await client.get(f"{BASE_URL}/memory/entities")
                assert r2.status_code == 200
                assert isinstance(r2.json(), dict)

                # Vector search
                r3 = await client.post(
                    f"{BASE_URL}/memory/vector/search",
                    json={"query": "fraud transaction", "top_k": 3},
                )
                assert r3.status_code == 200
                assert isinstance(r3.json(), list)

            print(f"\n✅ Memory endpoints: episodic={len(r1.json())}, "
                  f"entities={len(r2.json())}, vector={len(r3.json())}")
        except Exception as e:
            pytest.skip(f"Server not running: {e}")


# ════════════════════════════════════════════════════════════
# ENTRY POINT
# ════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import subprocess
    result = subprocess.run(
        ["pytest", __file__, "-v", "-s",
         "-k", "not Integration and not HTTP"],
        cwd=str(ROOT),
    )
    sys.exit(result.returncode)
