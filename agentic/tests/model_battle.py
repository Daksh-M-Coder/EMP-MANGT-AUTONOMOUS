#!/usr/bin/env python3
# ============================================================
# tests/model_battle.py — Model Battle Test  V4
# ============================================================
# V4 UPDATES:
#   + All benchmark Ollama models added:
#       qwen2.5-coder:1.5b   (Qwen2.5-Coder 1.5B)
#       qwen2.5-coder:3b     (Qwen2.5-Coder 3B)
#       granite3.1-moe:1b    (Granite 3.1 MoE 1B)
#       granite3.1-moe:3b    (Granite 3.1 MoE 3B)
#       nemotron-mini        (Nemotron-Mini 4B / Nemotron-3 Nano)
#       deepseek-r1:1.5b     (DeepSeek-R1 1.5B)
#       qwen2.5:3b           (general baseline)
#       qwen2.5:7b           (quality baseline)
#   + MULTI_MODEL_BATTLE: tests Planner/Executor/Reflector using
#     different models in a single pipeline run
#   + auto-skip if model not pulled (check Ollama tags first)
#   + report now includes RAM usage column + multi-model section
#   + battle() programmatic API unchanged for pytest use
#
# KEPT FROM V3 (unchanged):
#   + Groq battle entry (cloud fallback)
#   + GLM-OCR vision battle (image path optional)
#   + generate_report() structure
#   + check_ollama_running() / check_ollama_model_available()
#   + argparse CLI (--prompt, --image, --no-groq, --output)
#
# HOW TO RUN:
#   python tests/model_battle.py                    # all available models
#   python tests/model_battle.py --quick            # 3B models only
#   python tests/model_battle.py --multi-model      # multi-model run
#   python tests/model_battle.py --no-groq          # skip Groq
#   python tests/model_battle.py --prompt "your task"
#   python tests/model_battle.py --image /tmp/invoice.png
#
# PULL ALL MODELS FIRST:
#   ollama pull qwen2.5:3b
#   ollama pull qwen2.5-coder:1.5b
#   ollama pull qwen2.5-coder:3b
#   ollama pull granite3.1-moe:1b
#   ollama pull granite3.1-moe:3b
#   ollama pull nemotron-mini
#   ollama pull deepseek-r1:1.5b
# ============================================================

import sys
import os
import time
import json
import argparse
import datetime
from pathlib import Path
from typing import Optional, List

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# ── Default prompt ────────────────────────────────────────────
DEFAULT_PROMPT = (
    "You are helping with financial analysis. "
    "A customer wants to transfer $9,800 to an account in Nigeria. "
    "The account was created 3 days ago, it's 3am, and it's a new device. "
    "Analyze the risk, use the calculator to compute 15% of $9800 as a fee, "
    "and give a clear APPROVE or BLOCK recommendation with reasoning."
)

# ════════════════════════════════════════════════════════════
# BATTLE ENTRIES — all benchmark models
# ════════════════════════════════════════════════════════════
#
# Sorted by: smallest RAM first (easiest to run).
# Each entry maps to one full Planner→Executor→Reflector run.
#
# STATUS KEY (set at runtime by check_ollama_model_available):
#   "available"  — pulled and ready
#   "missing"    — not pulled (skip with instruction to pull)
#   "offline"    — Ollama server not running

OLLAMA_MODELS_TO_BATTLE: List[dict] = [

    # ── Ultra-fast / low-RAM ──────────────────────────────
    {
        "id":       "deepseek-r1:1.5b",
        "label":    "DeepSeek-R1 1.5B",
        "provider": "ollama",
        "model":    "deepseek-r1:1.5b",
        "ram_gb":   1.1,
        "tier":     "ultra-fast",
        "note":     "Chain-of-thought reasoning. Shows thinking traces. Best for Reflector.",
        "pull":     "ollama pull deepseek-r1:1.5b",
    },
    {
        "id":       "qwen2.5-coder:1.5b",
        "label":    "Qwen2.5-Coder 1.5B",
        "provider": "ollama",
        "model":    "qwen2.5-coder:1.5b",
        "ram_gb":   1.2,
        "tier":     "ultra-fast",
        "note":     "Excellent structured JSON output. Top score for its size. Best Planner.",
        "pull":     "ollama pull qwen2.5-coder:1.5b",
    },
    {
        "id":       "granite3.1-moe:1b",
        "label":    "Granite 3.1 MoE 1B",
        "provider": "ollama",
        "model":    "granite3.1-moe:1b",
        "ram_gb":   0.9,
        "tier":     "ultra-fast",
        "note":     "IBM MoE architecture. Enterprise reliability. Tiny RAM footprint.",
        "pull":     "ollama pull granite3.1-moe:1b",
    },

    # ── Fast / mid-RAM ────────────────────────────────────
    {
        "id":       "qwen2.5:3b",
        "label":    "Qwen2.5 3B",
        "provider": "ollama",
        "model":    "qwen2.5:3b",
        "ram_gb":   2.3,
        "tier":     "fast",
        "note":     "General-purpose baseline. Default model. Balanced speed/quality.",
        "pull":     "ollama pull qwen2.5:3b",
    },
    {
        "id":       "qwen2.5-coder:3b",
        "label":    "Qwen2.5-Coder 3B",
        "provider": "ollama",
        "model":    "qwen2.5-coder:3b",
        "ram_gb":   2.3,
        "tier":     "fast",
        "note":     "Best structured output. Outperforms many 7B on JSON/code tasks.",
        "pull":     "ollama pull qwen2.5-coder:3b",
    },
    {
        "id":       "granite3.1-moe:3b",
        "label":    "Granite 3.1 MoE 3B",
        "provider": "ollama",
        "model":    "granite3.1-moe:3b",
        "ram_gb":   2.5,
        "tier":     "fast",
        "note":     "IBM MoE. Best tool-calling reliability. Top Executor candidate.",
        "pull":     "ollama pull granite3.1-moe:3b",
    },
    {
        "id":       "nemotron-mini",
        "label":    "Nemotron-Mini 4B",
        "provider": "ollama",
        "model":    "nemotron-mini",
        "ram_gb":   3.1,
        "tier":     "fast",
        "note":     "NVIDIA Nemotron-3 Nano 4B. Strong at evaluation and critical thinking.",
        "pull":     "ollama pull nemotron-mini",
    },

    # ── Medium / higher-quality ───────────────────────────
    {
        "id":       "qwen2.5:7b",
        "label":    "Qwen2.5 7B",
        "provider": "ollama",
        "model":    "qwen2.5:7b",
        "ram_gb":   4.7,
        "tier":     "medium",
        "note":     "Quality baseline. Better reasoning than 3B. Good for complex tasks.",
        "pull":     "ollama pull qwen2.5:7b",
    },
]

# ── Groq cloud entry (kept from V3) ──────────────────────────
GROQ_BATTLE_ENTRY = {
    "id":       "groq",
    "label":    "Groq LLM (Cloud)",
    "provider": "groq",
    "model":    "llama-3.3-70b-versatile",
    "ram_gb":   0.0,
    "tier":     "cloud",
    "note":     "Cloud-based. Requires GROQ_KEYS in .env. Key rotation supported.",
    "pull":     "Set GROQ_KEYS=gsk_key1,gsk_key2 in .env",
}

# ── Multi-model run config (V4 new) ──────────────────────────
# Tests running different models per agent in a single pipeline.
# Edit these to match models you've pulled.
MULTI_MODEL_CONFIGS = [
    {
        "label": "Coder+Granite+Nemotron",
        "desc":  "Planner=Qwen2.5-Coder 1.5B, Executor=Granite MoE 3B, Reflector=Nemotron-Mini",
        "map":   {
            "planner":   "qwen2.5-coder:1.5b",
            "executor":  "granite3.1-moe:3b",
            "reflector": "nemotron-mini",
        },
        "needs": ["qwen2.5-coder:1.5b", "granite3.1-moe:3b", "nemotron-mini"],
    },
    {
        "label": "Coder3B+Granite1B+DeepSeek",
        "desc":  "Planner=Qwen2.5-Coder 3B, Executor=Granite MoE 1B, Reflector=DeepSeek-R1 1.5B",
        "map":   {
            "planner":   "qwen2.5-coder:3b",
            "executor":  "granite3.1-moe:1b",
            "reflector": "deepseek-r1:1.5b",
        },
        "needs": ["qwen2.5-coder:3b", "granite3.1-moe:1b", "deepseek-r1:1.5b"],
    },
    {
        "label": "All-Qwen2.5-3B (baseline)",
        "desc":  "All agents: Qwen2.5 3B (standard single-model baseline)",
        "map":   {
            "planner":   "qwen2.5:3b",
            "executor":  "qwen2.5:3b",
            "reflector": "qwen2.5:3b",
        },
        "needs": ["qwen2.5:3b"],
    },
]


# ════════════════════════════════════════════════════════════
# OLLAMA AVAILABILITY CHECKS
# ════════════════════════════════════════════════════════════

def check_ollama_running(base_url: str = "http://localhost:11434") -> bool:
    """Check if Ollama server is reachable."""
    try:
        import requests
        return requests.get(f"{base_url}/api/tags", timeout=3).status_code == 200
    except Exception:
        return False


def check_ollama_model_available(model_name: str, base_url: str = "http://localhost:11434") -> bool:
    """Check if a specific model is pulled in Ollama."""
    try:
        import requests
        resp = requests.get(f"{base_url}/api/tags", timeout=5)
        if resp.status_code == 200:
            pulled = [m["name"] for m in resp.json().get("models", [])]
            tag    = model_name.split(":")[0]
            return any(m == model_name or m.startswith(tag) for m in pulled)
        return False
    except Exception:
        return False


def get_pulled_models(base_url: str = "http://localhost:11434") -> list[str]:
    """Return list of all pulled model names."""
    try:
        import requests
        resp = requests.get(f"{base_url}/api/tags", timeout=5)
        if resp.status_code == 200:
            return [m["name"] for m in resp.json().get("models", [])]
        return []
    except Exception:
        return []


# ════════════════════════════════════════════════════════════
# SINGLE MODEL BATTLE RUNNER
# ════════════════════════════════════════════════════════════

def run_single_battle(
    model_config: dict,
    prompt:       str,
    session_id:   str,
    verbose:      bool = True,
) -> dict:
    """
    Run one full Planner→Executor→Reflector pipeline with one model.

    All three agents use the same model (single-model run).
    For mixed-model runs use run_multi_model_battle().

    Returns result dict with metrics.
    """
    label    = model_config["label"]
    provider = model_config["provider"]
    model    = model_config["model"]

    if verbose:
        print(f"\n{'='*65}")
        print(f"  🥊  {label}")
        print(f"       Model: {model} | RAM: {model_config.get('ram_gb', '?')} GB")
        print(f"       {model_config.get('note', '')}")
        print(f"{'='*65}")

    result = {
        "label":            label,
        "model":            model,
        "provider":         provider,
        "ram_gb":           model_config.get("ram_gb", 0),
        "tier":             model_config.get("tier", "?"),
        "success":          False,
        "latency_sec":      0.0,
        "plan_steps":       0,
        "tools_called":     0,
        "tool_names":       [],
        "reflection_score": 0.0,
        "reflection_count": 0,
        "answer_length":    0,
        "final_answer":     "",
        "errors":           [],
        "error_message":    "",
        "run_type":         "single",
    }

    # Stash originals for restore
    try:
        from config import cfg, llm_factory
        original_provider = cfg.PROVIDER
        original_models   = dict(cfg.OLLAMA_MODELS)

        if provider == "ollama":
            cfg.PROVIDER = "ollama"
            cfg.OLLAMA_MODELS = {k: model for k in ["planner", "executor", "reflector"]}
            os.environ["LLM_PROVIDER"] = "ollama"
            os.environ["OLLAMA_MODEL"] = model
        elif provider == "groq":
            from config import _parse_groq_keys
            keys = _parse_groq_keys()
            if not keys:
                result["error_message"] = "GROQ_KEYS not set in .env — skipping Groq"
                if verbose:
                    print(f"  ⚠️  {result['error_message']}")
                return result
            cfg.PROVIDER = "groq"
            os.environ["LLM_PROVIDER"] = "groq"

        from graph import build_graph, load_memory_context
        from state import create_initial_state

        if verbose:
            print(f"  ⏳ Running pipeline...")

        graph      = build_graph()
        memory_ctx = load_memory_context(prompt, session_id)
        state      = create_initial_state(
            user_query       = prompt,
            session_id       = session_id,
            episodic_context = memory_ctx["episodic_context"],
            vector_context   = memory_ctx["vector_context"],
            entity_context   = memory_ctx["entity_context"],
        )

        t_start     = time.time()
        final_state = graph.invoke(state)
        latency     = time.time() - t_start

        plan        = final_state.get("plan", [])
        tool_calls  = final_state.get("tool_calls", [])
        reflections = final_state.get("reflections", [])
        answer      = final_state.get("final_answer") or ""
        ref_score   = reflections[-1].get("quality_score", 0.0) if reflections else 0.0

        result.update({
            "success":          final_state.get("is_complete", False),
            "latency_sec":      round(latency, 2),
            "plan_steps":       len(plan),
            "tools_called":     len(tool_calls),
            "tool_names":       list({tc.get("tool_name", "?") for tc in tool_calls}),
            "reflection_score": round(ref_score, 3),
            "reflection_count": final_state.get("reflection_count", 0),
            "answer_length":    len(answer),
            "final_answer":     answer[:600],
            "errors":           final_state.get("errors", []),
        })

        if verbose:
            status = "✅" if result["success"] else "⚠️"
            print(f"  {status} {latency:.1f}s | steps={len(plan)} | "
                  f"tools={len(tool_calls)} | score={ref_score:.2f}")
            if answer:
                print(f"  💬 {answer[:120]}...")

    except Exception as e:
        result["error_message"] = f"{type(e).__name__}: {e}"
        if verbose:
            print(f"  ❌ {result['error_message']}")
    finally:
        try:
            cfg.PROVIDER      = original_provider
            cfg.OLLAMA_MODELS = original_models
            os.environ["LLM_PROVIDER"] = original_provider
        except Exception:
            pass

    return result


# ════════════════════════════════════════════════════════════
# MULTI-MODEL BATTLE RUNNER (V4 new)
# ════════════════════════════════════════════════════════════

def run_multi_model_battle(
    multi_config: dict,
    prompt:       str,
    session_id:   str,
    ollama_url:   str  = "http://localhost:11434",
    verbose:      bool = True,
) -> dict:
    """
    Run one pipeline where each agent uses a DIFFERENT model.

    Uses invoke_with_model_map() from graph.py — the V4
    multi-model feature.

    Args:
        multi_config: Entry from MULTI_MODEL_CONFIGS
        prompt:       Battle prompt
        session_id:   Unique session ID
        ollama_url:   Ollama server URL
        verbose:      Print progress

    Returns:
        Result dict (same shape as run_single_battle, run_type="multi")
    """
    label   = multi_config["label"]
    desc    = multi_config["desc"]
    map_    = multi_config["map"]
    needs   = multi_config.get("needs", [])

    if verbose:
        print(f"\n{'='*65}")
        print(f"  🎯  MULTI-MODEL: {label}")
        print(f"       {desc}")
        for agent, model in map_.items():
            print(f"       {agent:10s} → {model}")
        print(f"{'='*65}")

    result = {
        "label":            f"Multi: {label}",
        "model":            json.dumps(map_),
        "provider":         "multi-ollama",
        "ram_gb":           0.0,
        "tier":             "multi",
        "success":          False,
        "latency_sec":      0.0,
        "plan_steps":       0,
        "tools_called":     0,
        "tool_names":       [],
        "reflection_score": 0.0,
        "reflection_count": 0,
        "answer_length":    0,
        "final_answer":     "",
        "errors":           [],
        "error_message":    "",
        "run_type":         "multi",
        "model_map":        map_,
    }

    # Check all required models are pulled
    missing = [m for m in needs if not check_ollama_model_available(m, ollama_url)]
    if missing:
        result["error_message"] = f"Models not pulled: {', '.join(missing)}"
        if verbose:
            for m in missing:
                mentry = next((e for e in OLLAMA_MODELS_TO_BATTLE if e["model"] == m), None)
                cmd = mentry["pull"] if mentry else f"ollama pull {m}"
                print(f"  ⚠️  Missing: {m}  →  {cmd}")
        return result

    try:
        from graph import invoke_with_model_map, load_memory_context
        from state import create_initial_state

        if verbose:
            print(f"  ⏳ Running multi-model pipeline...")

        memory_ctx = load_memory_context(prompt, session_id)
        state      = create_initial_state(
            user_query       = prompt,
            session_id       = session_id,
            episodic_context = memory_ctx["episodic_context"],
            vector_context   = memory_ctx["vector_context"],
            entity_context   = memory_ctx["entity_context"],
        )

        t_start     = time.time()
        final_state = invoke_with_model_map(state, map_)
        latency     = time.time() - t_start

        plan        = final_state.get("plan", [])
        tool_calls  = final_state.get("tool_calls", [])
        reflections = final_state.get("reflections", [])
        answer      = final_state.get("final_answer") or ""
        ref_score   = reflections[-1].get("quality_score", 0.0) if reflections else 0.0

        result.update({
            "success":          final_state.get("is_complete", False),
            "latency_sec":      round(latency, 2),
            "plan_steps":       len(plan),
            "tools_called":     len(tool_calls),
            "tool_names":       list({tc.get("tool_name","?") for tc in tool_calls}),
            "reflection_score": round(ref_score, 3),
            "reflection_count": final_state.get("reflection_count", 0),
            "answer_length":    len(answer),
            "final_answer":     answer[:600],
            "errors":           final_state.get("errors", []),
        })

        if verbose:
            status = "✅" if result["success"] else "⚠️"
            print(f"  {status} {latency:.1f}s | steps={len(plan)} | "
                  f"tools={len(tool_calls)} | score={ref_score:.2f}")
            if answer:
                print(f"  💬 {answer[:120]}...")

    except Exception as e:
        result["error_message"] = f"{type(e).__name__}: {e}"
        if verbose:
            print(f"  ❌ {result['error_message']}")

    return result


# ════════════════════════════════════════════════════════════
# GLM-OCR BATTLE RUNNER (kept from V3, unchanged)
# ════════════════════════════════════════════════════════════

def run_glm_ocr_battle(image_path: str, extraction_goal: str) -> dict:
    """Test GLM-OCR vision extraction (unchanged from V3)."""
    print(f"\n{'='*65}")
    print(f"  🔍  GLM-OCR Vision Model")
    print(f"       Image: {image_path}")
    print(f"       Goal:  {extraction_goal[:55]}")
    print(f"{'='*65}")

    result = {
        "label":         "GLM-OCR (Vision)",
        "model":         "glm4v",
        "provider":      "glm_ocr",
        "success":       False,
        "latency_sec":   0.0,
        "extracted_len": 0,
        "extracted_text":"",
        "error_message": "",
        "note":          "OCR only — not a reasoning model",
    }

    try:
        from config import glm_ocr_call, cfg
        if not cfg.GLM_OCR_ENABLED:
            result["error_message"] = "GLM_OCR_ENABLED=false in .env"
            print(f"  ⚠️  GLM-OCR disabled")
            return result

        t_start = time.time()
        text    = glm_ocr_call(image_path=image_path, prompt=extraction_goal)
        latency = time.time() - t_start

        result.update({
            "success":        not text.startswith("ERROR:"),
            "latency_sec":    round(latency, 2),
            "extracted_len":  len(text),
            "extracted_text": text[:400],
        })
        status = "✅" if result["success"] else "❌"
        print(f"  {status} {latency:.1f}s | {len(text)} chars extracted")
        if result["success"]:
            print(f"  📄 {text[:120]}...")
        else:
            print(f"  ❌ {text}")
    except Exception as e:
        result["error_message"] = str(e)
        print(f"  ❌ Exception: {e}")

    return result


# ════════════════════════════════════════════════════════════
# REPORT GENERATOR
# ════════════════════════════════════════════════════════════

def generate_report(
    results:       list[dict],
    prompt:        str,
    output_path:   Path,
    multi_results: Optional[list[dict]] = None,
    glm_result:    Optional[dict]       = None,
) -> str:
    """Generate full comparison report and save to file."""
    try:
        from tabulate import tabulate
        HAS_TABULATE = True
    except ImportError:
        HAS_TABULATE = False

    ts    = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    lines = []

    lines += [
        "=" * 72,
        "  🥊  MODEL BATTLE RESULTS — Universal LangGraph Agent  V4",
        "=" * 72,
        f"  Date:   {ts}",
        f"  Prompt: {prompt[:75]}{'...' if len(prompt) > 75 else ''}",
        "=" * 72,
        "",
    ]

    # ── Single-model summary table ────────────────────────
    single = [r for r in results if r.get("run_type") != "multi"]
    if single:
        lines += ["SINGLE-MODEL RESULTS", "-" * 72]
        headers = ["Model", "RAM", "Tier", "✅", "⏱️s", "📋Steps", "🔧Tools", "⭐Score", "📝Len"]
        rows = []
        for r in single:
            ok = "✅" if r["success"] else ("⚠️" if not r.get("error_message") else "❌")
            rows.append([
                r["label"],
                f"{r.get('ram_gb', 0):.1f}G",
                r.get("tier", "?"),
                ok,
                f"{r['latency_sec']:.1f}",
                r["plan_steps"],
                r["tools_called"],
                f"{r['reflection_score']:.2f}",
                r["answer_length"],
            ])

        if HAS_TABULATE:
            lines.append(tabulate(rows, headers=headers, tablefmt="grid"))
        else:
            lines.append("  " + " | ".join(headers))
            for row in rows:
                lines.append("  " + " | ".join(str(c) for c in row))
        lines.append("")

        # Winner analysis
        successful = [r for r in single if r["success"]]
        if successful and len(successful) > 1:
            fastest  = min(successful, key=lambda r: r["latency_sec"])
            smartest = max(successful, key=lambda r: r["reflection_score"])
            max_lat  = max(r["latency_sec"]  for r in successful) or 1
            max_sc   = max(r["reflection_score"] for r in successful) or 1
            scored   = sorted(
                [(0.5 * r["reflection_score"] / max_sc +
                  0.3 * (1 - r["latency_sec"] / max_lat) +
                  0.2 * (r["tools_called"] / max(r["tools_called"] for r in successful or [1])),
                  r) for r in successful],
                reverse=True,
            )
            lines += [
                "WINNER ANALYSIS",
                "-" * 72,
                f"  ⚡ Fastest:        {fastest['label']} ({fastest['latency_sec']:.1f}s)",
                f"  🧠 Highest Score:  {smartest['label']} (score={smartest['reflection_score']:.2f})",
            ]
            if scored:
                w_score, winner = scored[0]
                lines += [
                    f"  🏆 OVERALL WINNER: {winner['label']}",
                    f"     (composite={w_score:.3f}: 50% quality + 30% speed + 20% tools)",
                ]
            lines.append("")

    # ── Multi-model results table ─────────────────────────
    if multi_results:
        lines += ["", "MULTI-MODEL PIPELINE RESULTS (V4)", "-" * 72,
                  "  Each row = one run where Planner/Executor/Reflector use different models.", ""]
        mheaders = ["Config", "✅", "⏱️s", "📋Steps", "🔧Tools", "⭐Score"]
        mrows    = []
        for r in multi_results:
            ok = "✅" if r["success"] else ("⚠️" if not r.get("error_message") else "❌")
            mrows.append([
                r["label"],
                ok,
                f"{r['latency_sec']:.1f}",
                r["plan_steps"],
                r["tools_called"],
                f"{r['reflection_score']:.2f}",
            ])
        if HAS_TABULATE:
            lines.append(tabulate(mrows, headers=mheaders, tablefmt="grid"))
        else:
            lines.append("  " + " | ".join(mheaders))
            for row in mrows:
                lines.append("  " + " | ".join(str(c) for c in row))

        for r in multi_results:
            if r.get("model_map"):
                lines += [
                    "",
                    f"  Config: {r['label']}",
                ]
                for agent, model in r["model_map"].items():
                    lines.append(f"    {agent:10s} → {model}")
                if r.get("error_message"):
                    lines.append(f"  ❌ Error: {r['error_message']}")
                elif r["final_answer"]:
                    lines.append(f"  Answer: {r['final_answer'][:200]}")
        lines.append("")

    # ── Detailed per-model results ────────────────────────
    lines += ["", "DETAILED RESULTS PER MODEL", "=" * 72, ""]
    for r in results:
        status = "SUCCESS" if r["success"] else "FAILED"
        lines += [
            f"  ── {r['label']} ({r.get('tier','?')} | {r.get('ram_gb',0):.1f}GB RAM) ──",
            f"  Status:           {status}",
            f"  Latency:          {r['latency_sec']:.2f}s",
            f"  Plan Steps:       {r['plan_steps']}",
            f"  Tools Called:     {r['tools_called']}",
        ]
        if r.get("tool_names"):
            lines.append(f"  Tool Names:       {', '.join(r['tool_names'])}")
        lines += [
            f"  Reflection Score: {r['reflection_score']:.3f}",
            f"  Answer Length:    {r['answer_length']} chars",
        ]
        if r.get("error_message"):
            lines.append(f"  ❌ Error:          {r['error_message']}")
        if r["final_answer"]:
            lines += ["  Answer:", "  " + "-"*55]
            for ln in r["final_answer"].splitlines()[:10]:
                lines.append(f"    {ln}")
            if len(r["final_answer"]) > 600:
                lines.append("    [... truncated ...]")
        lines.append("")

    # ── GLM-OCR section (kept from V3) ───────────────────
    if glm_result:
        lines += [
            "GLM-OCR VISION RESULTS", "=" * 72,
            f"  Model:   {glm_result['model']} | Mode: see GLM_OCR_MODE in .env",
            f"  Status:  {'SUCCESS' if glm_result['success'] else 'FAILED'}",
            f"  Latency: {glm_result['latency_sec']:.2f}s",
            f"  Chars:   {glm_result.get('extracted_len', 0)}",
            f"  Note:    {glm_result.get('note', '')}",
        ]
        if glm_result.get("error_message"):
            lines.append(f"  ❌ Error: {glm_result['error_message']}")
        if glm_result.get("extracted_text"):
            lines += ["  Extracted:", "  " + "-"*55,
                      f"    {glm_result['extracted_text'][:250]}"]
        lines.append("")

    # ── Recommendations ───────────────────────────────────
    lines += [
        "RECOMMENDATIONS", "=" * 72,
        "  Constrained hardware (<2 GB RAM):",
        "    → deepseek-r1:1.5b or qwen2.5-coder:1.5b or granite3.1-moe:1b",
        "",
        "  Best overall single model (~2.3 GB):",
        "    → qwen2.5-coder:3b (structured output) or qwen2.5:3b (general)",
        "",
        "  Best multi-model config (recommended ~5 GB total):",
        "    Planner=qwen2.5-coder:1.5b | Executor=granite3.1-moe:3b | Reflector=nemotron-mini",
        "    Set in .env:",
        "      OLLAMA_PLANNER_MODEL=qwen2.5-coder:1.5b",
        "      OLLAMA_EXECUTOR_MODEL=granite3.1-moe:3b",
        "      OLLAMA_REFLECTOR_MODEL=nemotron-mini",
        "    Or via API: POST /run { model_map: { planner: '...', executor: '...', reflector: '...' } }",
        "",
        "  Image/OCR tasks: always use glm_ocr_extract() tool (GLM-OCR)",
        "  Cloud fallback:  set LLM_PROVIDER=groq + GROQ_KEYS=... in .env",
        "",
        "=" * 72,
        f"  Report: {output_path}",
        "=" * 72,
    ]

    report = "\n".join(lines)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")
    return report


# ════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="V4 Model Battle — benchmark all Ollama models on the same prompt",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python tests/model_battle.py                    # all available models
  python tests/model_battle.py --quick            # 3B and under only
  python tests/model_battle.py --multi-model      # also run multi-agent configs
  python tests/model_battle.py --no-groq          # skip Groq
  python tests/model_battle.py --prompt "Your task"
  python tests/model_battle.py --image /tmp/invoice.png
  python tests/model_battle.py --output tests/results/my_run.txt
        """
    )
    parser.add_argument("--prompt",      default=DEFAULT_PROMPT)
    parser.add_argument("--image",       default="")
    parser.add_argument("--no-groq",     action="store_true")
    parser.add_argument("--quick",       action="store_true",
                        help="Only test models ≤ 3B params (faster run)")
    parser.add_argument("--multi-model", action="store_true",
                        help="Also run multi-agent model combos")
    parser.add_argument("--output",      default="tests/results/model_battle_results.txt")
    parser.add_argument("--verbose",     action="store_true", default=True)
    args = parser.parse_args()

    output_path = ROOT / args.output
    from config import cfg
    ollama_url  = cfg.OLLAMA_BASE_URL

    print("\n" + "=" * 65)
    print("  🥊  MODEL BATTLE V4 — Universal LangGraph Agent")
    print("=" * 65)
    print(f"  Prompt:  {args.prompt[:60]}...")
    print(f"  Output:  {output_path}")
    print("=" * 65)

    # ── Check Ollama ──────────────────────────────────────
    ollama_up   = check_ollama_running(ollama_url)
    pulled      = get_pulled_models(ollama_url) if ollama_up else []

    if not ollama_up:
        print(f"\n  ⚠️  Ollama offline at {ollama_url}")
        print("      Start with: ollama serve")
    else:
        print(f"\n  ✅ Ollama running | {len(pulled)} models pulled")
        if pulled:
            print(f"     Pulled: {', '.join(pulled[:6])}{'...' if len(pulled)>6 else ''}")

    # ── Build battle list ─────────────────────────────────
    models_to_run = []

    for entry in OLLAMA_MODELS_TO_BATTLE:
        if args.quick and entry.get("ram_gb", 0) > 3.0:
            print(f"  ⏭️  Skip {entry['label']} (--quick, RAM={entry['ram_gb']}GB)")
            continue
        if not ollama_up:
            print(f"  ⏭️  Skip {entry['label']} (Ollama offline)")
            continue
        if not check_ollama_model_available(entry["model"], ollama_url):
            print(f"  ⏭️  Skip {entry['label']} — not pulled")
            print(f"       Run: {entry['pull']}")
            continue
        models_to_run.append(entry)

    if not args.no_groq and os.getenv("GROQ_KEYS"):
        models_to_run.append(GROQ_BATTLE_ENTRY)
    elif not args.no_groq:
        print(f"  ⏭️  Skip Groq (GROQ_KEYS not set)")

    if not models_to_run:
        print("\n  ❌ No models available.")
        print("     Pull at least one: ollama pull qwen2.5:3b")
        sys.exit(1)

    print(f"\n  📋 Models to battle: {len(models_to_run)}")
    for m in models_to_run:
        ram = f"{m.get('ram_gb', '?')}GB" if m.get("ram_gb") else "cloud"
        print(f"     • {m['label']} ({ram})")

    # ── Run single-model battles ──────────────────────────
    ts_run  = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    results = []

    for i, mc in enumerate(models_to_run, 1):
        result = run_single_battle(
            model_config = mc,
            prompt       = args.prompt,
            session_id   = f"battle_{ts_run}_m{i}",
            verbose      = args.verbose,
        )
        results.append(result)

    # ── Multi-model runs ──────────────────────────────────
    multi_results = []
    if args.multi_model and ollama_up:
        print(f"\n\n{'='*65}")
        print(f"  🎯  MULTI-MODEL BATTLE ({len(MULTI_MODEL_CONFIGS)} configs)")
        print(f"{'='*65}")
        for j, mc in enumerate(MULTI_MODEL_CONFIGS, 1):
            result = run_multi_model_battle(
                multi_config = mc,
                prompt       = args.prompt,
                session_id   = f"battle_{ts_run}_multi{j}",
                ollama_url   = ollama_url,
                verbose      = args.verbose,
            )
            multi_results.append(result)

    # ── GLM-OCR ───────────────────────────────────────────
    glm_result = None
    if args.image:
        if not Path(args.image).exists():
            print(f"\n  ⚠️  Image not found: {args.image}")
        else:
            glm_result = run_glm_ocr_battle(
                image_path     = args.image,
                extraction_goal= "Extract all text, numbers, and key information from this image.",
            )

    # ── Report ────────────────────────────────────────────
    print(f"\n\n{'='*65}")
    print("  📊  GENERATING REPORT")
    print(f"{'='*65}")

    all_results = results + multi_results
    report = generate_report(
        results       = all_results,
        prompt        = args.prompt,
        output_path   = output_path,
        multi_results = multi_results if multi_results else None,
        glm_result    = glm_result,
    )
    print(report)
    print(f"\n  ✅ Report saved: {output_path}")


# ════════════════════════════════════════════════════════════
# PROGRAMMATIC API (for pytest / other scripts)
# ════════════════════════════════════════════════════════════

def battle(
    prompt:       str           = DEFAULT_PROMPT,
    models:       Optional[list] = None,
    image:        Optional[str]  = None,
    output:       Optional[str]  = None,
    multi_model:  bool           = False,
) -> list[dict]:
    """
    Programmatic battle API.

    Args:
        prompt:      The prompt to test all models on
        models:      List of model config dicts (defaults to OLLAMA_MODELS_TO_BATTLE)
        image:       Optional image path for GLM-OCR test
        output:      Optional output file path
        multi_model: Also run multi-agent model combos

    Returns:
        List of result dicts

    Usage in pytest:
        from tests.model_battle import battle
        results = battle("What is 15% of 2400?")
        assert any(r["success"] for r in results)

    Usage with multi-model:
        results = battle(
            "Analyze fraud risk",
            multi_model=True,
        )
        multi = [r for r in results if r.get("run_type") == "multi"]
    """
    _models  = models or OLLAMA_MODELS_TO_BATTLE
    results  = []

    for i, mc in enumerate(_models, 1):
        result = run_single_battle(mc, prompt, f"api_battle_{int(time.time())}_{i}", verbose=False)
        results.append(result)

    if multi_model:
        from config import cfg
        for j, mc in enumerate(MULTI_MODEL_CONFIGS, 1):
            result = run_multi_model_battle(
                mc, prompt, f"api_multi_{int(time.time())}_{j}",
                ollama_url=cfg.OLLAMA_BASE_URL, verbose=False,
            )
            results.append(result)

    if output:
        generate_report(
            results       = results,
            prompt        = prompt,
            output_path   = Path(output),
            multi_results = [r for r in results if r.get("run_type") == "multi"] or None,
        )
    return results


if __name__ == "__main__":
    main()
