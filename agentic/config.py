# ============================================================
# config.py — Universal LangGraph Agentic System  V5 (STABLE)
# ============================================================
# V4 ADDITIONS (nothing removed from V3):
#   + OLLAMA_MODEL_REGISTRY — full benchmark model catalogue with
#     RAM requirements, speed, quality, and pull commands
#   + ModelProfile TypedDict — typed metadata per registry entry
#   + Per-agent model selection (Planner/Executor/Reflector can
#     each use a different model in a single run)
#   + Dynamic model override: resolve_agent_models() + override API
#   + SystemConfig.set_agent_models() — change models mid-run
#   + SystemConfig.get_model_info() — query registry by name
#   + SystemConfig.get_active_model_map() — current agent→model map
#   + /models API helper: list_model_registry() function
#   + llm_factory() model_map parameter for per-agent routing
#
# KEPT EXACTLY (V3 → V4, zero changes):
#   + Groq key rotation (GroqKeyRotator, groq_rotator(), GROQ_MODELS)
#   + GLM-OCR full config block (glm_ocr_call, GLM_OCR_* vars)
#   + All path constants (BASE_DIR, MEMORY_*, LOG_*, etc.)
#   + All temperature constants (AGENT_TEMPERATURES)
#   + SystemConfig.summary(), _mask_db_url(), get_llm()
#   + llm_factory() signature (model_override still works)
#
# ════════════════════════════════════════════════════════════
# BACKEND ARCHITECTURE OVERVIEW
# ════════════════════════════════════════════════════════════
#
#   REASONING BACKENDS (Planner / Executor / Reflector):
#   ─────────────────────────────────────────────────────────
#   ollama  → any model in OLLAMA_MODEL_REGISTRY (local, no key)
#   groq    → llama-3.3-70b-versatile (cloud, key rotation)
#
#   MULTI-MODEL SINGLE RUN (V4 new feature):
#   ─────────────────────────────────────────────────────────
#   Planner  = qwen2.5-coder:1.5b  (fast, structured output)
#   Executor = granite3.1-moe:3b   (strong tool-calling)
#   Reflector= nemotron-mini       (quality evaluation)
#   Set via env or API: model_map={"planner": "...", "executor": "..."}
#
#   VISION / OCR TOOL (NOT a reasoning model):
#   ─────────────────────────────────────────────────────────
#   GLM-OCR → https://github.com/zai-org/GLM-OCR
#     Mode A: ollama pull glm4v  → ChatOllama with image input
#     Mode B: local HTTP server  → POST /ocr with base64 image
#   Called ONLY via glm_ocr_extract() tool in tools.py.
#
# ════════════════════════════════════════════════════════════
# ADAPTING TO A NEW PROJECT
# ════════════════════════════════════════════════════════════
#
#   1. Edit .env:
#        PROJECT_NAME=FraudGuard
#        SYSTEM_PROMPT=You are a fraud detection AI. Score 0.0-1.0.
#        LLM_PROVIDER=ollama
#        OLLAMA_MODEL=qwen2.5:3b       # default for all agents
#        OLLAMA_PLANNER_MODEL=qwen2.5-coder:3b  # optional per-agent
#        OLLAMA_EXECUTOR_MODEL=granite3.1-moe:3b
#
#   2. Add skills to /skills/ (auto-loaded):
#        skills/fraud_scorer.py
#
#   3. For multi-model run via API:
#        POST /run  { "query": "...", "model_map": {
#          "planner": "qwen2.5-coder:1.5b",
#          "executor": "granite3.1-moe:3b",
#          "reflector": "nemotron-mini"
#        }}
#
#   4. uvicorn server:app --port 8000 --reload
#
# ============================================================

import os
import itertools
import threading
from pathlib import Path
from typing import Literal, Optional, TypedDict
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent / ".env")

# ── Root Paths ────────────────────────────────────────────────
BASE_DIR         = Path(__file__).parent
MEMORY_DIR       = BASE_DIR / "memory"
MEMORY_JSON_DIR  = MEMORY_DIR / "json"
MEMORY_MD_DIR    = MEMORY_DIR / "md"
SKILLS_DIR       = BASE_DIR / "skills"
SKILLS_MD_DIR    = SKILLS_DIR / "md_skills"
LOG_DIR          = BASE_DIR / "ai-req-res-logging"
LOG_JSON_DIR     = LOG_DIR / "json"
LOG_MD_DIR       = LOG_DIR / "md"
VECTOR_INDEX_DIR = MEMORY_DIR / "vector_index"
TESTS_DIR        = BASE_DIR / "tests"

for _d in [
    MEMORY_JSON_DIR, MEMORY_MD_DIR,
    SKILLS_DIR, SKILLS_MD_DIR,
    LOG_JSON_DIR, LOG_MD_DIR,
    VECTOR_INDEX_DIR, TESTS_DIR,
    TESTS_DIR / "results",
]:
    _d.mkdir(parents=True, exist_ok=True)


# ════════════════════════════════════════════════════════════
# MODEL PROFILE — typed metadata for registry entries
# ════════════════════════════════════════════════════════════

class ModelProfile(TypedDict):
    """
    Metadata for one model in the OLLAMA_MODEL_REGISTRY.

    Fields:
        name:         Exact Ollama model tag (used in ollama pull)
        label:        Human-friendly display name
        params:       Parameter count string (e.g. "1.5B", "3B")
        ram_gb:       Approximate RAM required in GB
        speed:        Relative speed: "ultra-fast" | "fast" | "medium" | "slow"
        quality:      Relative quality: "basic" | "good" | "great" | "excellent"
        strengths:    List of what this model is best at
        best_for:     Which agent role it's recommended for
        pull_cmd:     Shell command to pull this model
        notes:        Extra notes (e.g. benchmark scores, quirks)
    """
    name:      str
    label:     str
    params:    str
    ram_gb:    float
    speed:     str
    quality:   str
    strengths: list
    best_for:  list
    pull_cmd:  str
    notes:     str


# ════════════════════════════════════════════════════════════
# OLLAMA MODEL REGISTRY — full benchmark catalogue
# ════════════════════════════════════════════════════════════
#
# All models are local — no API key required.
# Pull any model with: ollama pull <name>
#
# HOW TO CHOOSE:
#   Low RAM (<4 GB):   tinyllama, qwen2.5-coder:1.5b, deepseek-r1:1.5b
#   Mid RAM (4-8 GB):  qwen2.5-coder:3b, granite3.1-moe:3b, nemotron-mini
#   High RAM (8-16 GB):qwen2.5:7b, qwen2.5-coder:7b
#
# MULTI-AGENT RECOMMENDATION (good balance, ~6 GB total):
#   Planner  → qwen2.5-coder:1.5b  (structured JSON plans, fast)
#   Executor → granite3.1-moe:3b   (tool-calling, instruction-following)
#   Reflector→ nemotron-mini        (quality evaluation, critical thinking)
#
# PULL ALL RECOMMENDED MODELS:
#   ollama pull qwen2.5:3b
#   ollama pull qwen2.5-coder:1.5b
#   ollama pull qwen2.5-coder:3b
#   ollama pull granite3.1-moe:1b
#   ollama pull granite3.1-moe:3b
#   ollama pull nemotron-mini
#   ollama pull deepseek-r1:1.5b
#   ollama pull glm4v            # vision/OCR only

OLLAMA_MODEL_REGISTRY: dict[str, ModelProfile] = {

    # ── Qwen2.5 Series (Alibaba) ─────────────────────────────
    "qwen2.5:3b": ModelProfile(
        name      = "qwen2.5:3b",
        label     = "Qwen2.5 3B",
        params    = "3B",
        ram_gb    = 2.3,
        speed     = "fast",
        quality   = "good",
        strengths = ["general reasoning", "math", "code", "multilingual"],
        best_for  = ["planner", "executor", "reflector"],
        pull_cmd  = "ollama pull qwen2.5:3b",
        notes     = "Best default choice. Balanced speed/quality. Recommended start.",
    ),
    "qwen2.5:7b": ModelProfile(
        name      = "qwen2.5:7b",
        label     = "Qwen2.5 7B",
        params    = "7B",
        ram_gb    = 4.7,
        speed     = "medium",
        quality   = "great",
        strengths = ["complex reasoning", "long context", "math", "code"],
        best_for  = ["planner"],
        pull_cmd  = "ollama pull qwen2.5:7b",
        notes     = "Higher quality than 3B. Use for Planner when quality matters.",
    ),
    "qwen2.5:14b": ModelProfile(
        name      = "qwen2.5:14b",
        label     = "Qwen2.5 14B",
        params    = "14B",
        ram_gb    = 9.0,
        speed     = "slow",
        quality   = "excellent",
        strengths = ["deep reasoning", "analysis", "long documents"],
        best_for  = ["planner"],
        pull_cmd  = "ollama pull qwen2.5:14b",
        notes     = "Best local quality. Requires 16GB+ RAM.",
    ),

    # ── Qwen2.5-Coder Series (Alibaba — Code-optimised) ──────
    "qwen2.5-coder:1.5b": ModelProfile(
        name      = "qwen2.5-coder:1.5b",
        label     = "Qwen2.5-Coder 1.5B",
        params    = "1.5B",
        ram_gb    = 1.2,
        speed     = "ultra-fast",
        quality   = "good",
        strengths = ["structured output", "JSON plans", "code", "function calls"],
        best_for  = ["planner", "executor"],
        pull_cmd  = "ollama pull qwen2.5-coder:1.5b",
        notes     = "Excellent for Planner (JSON plan generation). Very low RAM. "
                    "Top benchmark score for its size class.",
    ),
    "qwen2.5-coder:3b": ModelProfile(
        name      = "qwen2.5-coder:3b",
        label     = "Qwen2.5-Coder 3B",
        params    = "3B",
        ram_gb    = 2.3,
        speed     = "fast",
        quality   = "great",
        strengths = ["code", "structured JSON", "tool calling", "function arguments"],
        best_for  = ["planner", "executor"],
        pull_cmd  = "ollama pull qwen2.5-coder:3b",
        notes     = "Best-in-class for structured output. Outperforms many 7B models "
                    "on code/JSON tasks. Strong benchmark results.",
    ),
    "qwen2.5-coder:7b": ModelProfile(
        name      = "qwen2.5-coder:7b",
        label     = "Qwen2.5-Coder 7B",
        params    = "7B",
        ram_gb    = 4.7,
        speed     = "medium",
        quality   = "excellent",
        strengths = ["complex code", "structured output", "multi-step reasoning"],
        best_for  = ["planner"],
        pull_cmd  = "ollama pull qwen2.5-coder:7b",
        notes     = "Top-tier code model. Highly recommended for code-heavy domains.",
    ),

    # ── IBM Granite 3.1 MoE Series (IBM Research) ────────────
    "granite3.1-moe:1b": ModelProfile(
        name      = "granite3.1-moe:1b",
        label     = "Granite 3.1 MoE 1B",
        params    = "1B (MoE)",
        ram_gb    = 0.9,
        speed     = "ultra-fast",
        quality   = "good",
        strengths = ["instruction following", "tool use", "enterprise tasks"],
        best_for  = ["executor", "reflector"],
        pull_cmd  = "ollama pull granite3.1-moe:1b",
        notes     = "Mixture-of-Experts architecture. Very fast for tiny size. "
                    "IBM enterprise-grade safety and reliability. Low VRAM.",
    ),
    "granite3.1-moe:3b": ModelProfile(
        name      = "granite3.1-moe:3b",
        label     = "Granite 3.1 MoE 3B",
        params    = "3B (MoE)",
        ram_gb    = 2.5,
        speed     = "fast",
        quality   = "great",
        strengths = ["tool calling", "structured tasks", "enterprise reliability"],
        best_for  = ["executor", "reflector"],
        pull_cmd  = "ollama pull granite3.1-moe:3b",
        notes     = "Best MoE model for tool-calling tasks. IBM enterprise safety. "
                    "Excellent Executor model — instruction-following is its strength.",
    ),

    # ── NVIDIA Nemotron Series ────────────────────────────────
    "nemotron-mini": ModelProfile(
        name      = "nemotron-mini",
        label     = "Nemotron-Mini 4B",
        params    = "4B",
        ram_gb    = 3.1,
        speed     = "fast",
        quality   = "great",
        strengths = ["reasoning", "math", "critical thinking", "evaluation", "multi-step tasks"],
        best_for  = ["planner", "executor", "reflector"],
        pull_cmd  = "ollama pull nemotron-mini",
        notes     = "⭐ V5 PRIMARY DEFAULT. NVIDIA Nemotron-3 Nano 4B. "
                    "Best all-round model for this system. Excellent reasoning, "
                    "evaluation, and instruction following. ~3.1 GB RAM.",
    ),

    # ── DeepSeek-R1 Series ────────────────────────────────────
    "deepseek-r1:1.5b": ModelProfile(
        name      = "deepseek-r1:1.5b",
        label     = "DeepSeek-R1 1.5B",
        params    = "1.5B",
        ram_gb    = 1.1,
        speed     = "ultra-fast",
        quality   = "good",
        strengths = ["chain-of-thought", "math", "reasoning traces"],
        best_for  = ["reflector", "planner"],
        pull_cmd  = "ollama pull deepseek-r1:1.5b",
        notes     = "Distilled R1 reasoning model. Shows thinking traces. "
                    "Excellent for Reflector when you want detailed quality reasoning.",
    ),
    "deepseek-r1:7b": ModelProfile(
        name      = "deepseek-r1:7b",
        label     = "DeepSeek-R1 7B",
        params    = "7B",
        ram_gb    = 4.7,
        speed     = "medium",
        quality   = "excellent",
        strengths = ["deep reasoning", "math", "analysis", "long thinking"],
        best_for  = ["planner", "reflector"],
        pull_cmd  = "ollama pull deepseek-r1:7b",
        notes     = "Full R1 reasoning chain. High quality. Slower but thorough.",
    ),

    # ── TinyLlama — ultra-constrained hardware ─────────────────
    "tinyllama": ModelProfile(
        name      = "tinyllama",
        label     = "TinyLlama 1.1B",
        params    = "1.1B",
        ram_gb    = 0.7,
        speed     = "ultra-fast",
        quality   = "basic",
        strengths = ["simple tasks", "speed", "low resource"],
        best_for  = ["executor"],
        pull_cmd  = "ollama pull tinyllama",
        notes     = "For severely constrained hardware only (<1 GB RAM). "
                    "Limited reasoning. Good for simple extraction tasks.",
    ),

    # ── Vision (GLM-OCR — NOT a reasoning model) ──────────────
    "glm4v": ModelProfile(
        name      = "glm4v",
        label     = "GLM-4V (Vision/OCR)",
        params    = "9B",
        ram_gb    = 6.0,
        speed     = "medium",
        quality   = "great",
        strengths = ["image OCR", "document reading", "visual understanding"],
        best_for  = ["vision_tool"],   # NOT a reasoning agent
        pull_cmd  = "ollama pull glm4v",
        notes     = "GLM-OCR vision model. Used ONLY via glm_ocr_extract() tool. "
                    "Do NOT set as Planner/Executor/Reflector model.",
    ),

    # ── Ollama Cloud Models (optional, requires Ollama account) ──
    # These run on Ollama's cloud infrastructure, not locally.
    # Set OLLAMA_CLOUD_MODEL=kimi-k2:cloud and LLM_PROVIDER=ollama
    # The base_url stays http://localhost:11434 — Ollama client
    # transparently routes cloud model requests to Ollama servers.
    "kimi-k2:cloud": ModelProfile(
        name      = "kimi-k2:cloud",
        label     = "Kimi K2.5 (Cloud)",
        params    = "Cloud",
        ram_gb    = 0.0,   # runs remotely
        speed     = "fast",
        quality   = "excellent",
        strengths = ["long context", "reasoning", "coding", "agent tasks"],
        best_for  = ["planner", "executor"],
        pull_cmd  = "# Requires Ollama cloud account. No local pull needed.",
        notes     = "Moonshot AI Kimi K2.5 via Ollama cloud. Optional backup. "
                    "Set OLLAMA_CLOUD_MODEL=kimi-k2:cloud in .env to use. "
                    "No API key needed if Ollama cloud account is linked.",
    ),
}


# ════════════════════════════════════════════════════════════
# CONTEXT WINDOW CONFIGURATION (V5 new)
# ════════════════════════════════════════════════════════════
#
# Ollama models have a default context window (usually 2048-4096).
# We set explicit num_ctx per agent to control token usage:
#
#   Planner:   CONTEXT_PLANNER   tokens  (small — just needs the task)
#   Executor:  CONTEXT_EXECUTOR  tokens  (grows with step index at runtime)
#   Reflector: CONTEXT_REFLECTOR tokens  (large — needs full plan + answer)
#
# The graph dynamically increases executor context as steps accumulate.
# Override in .env:
#   CONTEXT_PLANNER=4096
#   CONTEXT_EXECUTOR_BASE=4096
#   CONTEXT_EXECUTOR_MAX=8192
#   CONTEXT_REFLECTOR=8192

CONTEXT_PLANNER:       int = int(os.getenv("CONTEXT_PLANNER",        "4096"))
CONTEXT_EXECUTOR_BASE: int = int(os.getenv("CONTEXT_EXECUTOR_BASE",  "4096"))
CONTEXT_EXECUTOR_MAX:  int = int(os.getenv("CONTEXT_EXECUTOR_MAX",   "8192"))
CONTEXT_REFLECTOR:     int = int(os.getenv("CONTEXT_REFLECTOR",      "8192"))

# Cloud model tag (for Ollama cloud routing)
OLLAMA_CLOUD_MODEL: str = os.getenv("OLLAMA_CLOUD_MODEL", "")


# ════════════════════════════════════════════════════════════
# AGENT TEMPERATURE DEFAULTS (unchanged from V3)
# ════════════════════════════════════════════════════════════

AGENT_TEMPERATURES: dict[str, float] = {
    "planner":   float(os.getenv("PLANNER_TEMP",   "0.3")),
    "executor":  float(os.getenv("EXECUTOR_TEMP",  "0.1")),
    "reflector": float(os.getenv("REFLECTOR_TEMP", "0.2")),
}

# ════════════════════════════════════════════════════════════
# CONTEXT WINDOW SIZES — per agent role  (V5 new)
# ════════════════════════════════════════════════════════════
#
# WHY PER-AGENT:
#   Planner  → moderate context: query + memory snippets + tool list (~4k)
#   Executor → larger context: accumulates step results + tool outputs (~8k)
#   Reflector→ moderate context: final answer + plan summary (~4k)
#
# graph.py passes these as num_ctx to ChatOllama, which sets
# the Ollama context window for that specific agent call.
# Executor context grows dynamically as steps accumulate.
#
# OVERRIDE IN .env:
#   CONTEXT_PLANNER=4096
#   CONTEXT_EXECUTOR=8192
#   CONTEXT_REFLECTOR=4096
#   CONTEXT_MAX=16384      # hard ceiling, never exceeded
#
# MODEL CONTEXT LIMITS (native — we stay well below these):
#   nemotron-mini:     128k tokens  (use up to 16k safely)
#   qwen2.5-coder:3b:  32k tokens   (use up to 8k safely)
#   granite3.1-moe:3b: 8k tokens    (keep at 4k-6k)
#   deepseek-r1:1.5b:  32k tokens   (use up to 8k safely)
#   qwen2.5:7b:        128k tokens  (use up to 16k safely)

AGENT_CONTEXT_WINDOWS: dict[str, int] = {
    "planner":   int(os.getenv("CONTEXT_PLANNER",   "4096")),
    "executor":  int(os.getenv("CONTEXT_EXECUTOR",  "8192")),
    "reflector": int(os.getenv("CONTEXT_REFLECTOR", "4096")),
}
CONTEXT_WINDOW_MAX: int = int(os.getenv("CONTEXT_MAX", "16384"))


# ════════════════════════════════════════════════════════════
# OLLAMA AGENT MODEL MAP (per-agent, env-configurable)
# ════════════════════════════════════════════════════════════
#
# Priority resolution order (first match wins):
#   1. Per-agent env var:  OLLAMA_PLANNER_MODEL=qwen2.5-coder:3b
#   2. Global env var:     OLLAMA_MODEL=qwen2.5:3b
#   3. Built-in default:   qwen2.5:3b
#
# Shortcut env vars (aliases for common roles):
#   OLLAMA_FAST_MODEL    → use this for executor (speed-oriented)
#   OLLAMA_QUALITY_MODEL → use this for planner (quality-oriented)
#   OLLAMA_CODER_MODEL   → use this for code/structured output tasks

_DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "nemotron-mini")

OLLAMA_MODELS: dict[str, str] = {
    "planner": os.getenv(
        "OLLAMA_PLANNER_MODEL",
        os.getenv("OLLAMA_QUALITY_MODEL", _DEFAULT_MODEL)
    ),
    "executor": os.getenv(
        "OLLAMA_EXECUTOR_MODEL",
        os.getenv("OLLAMA_FAST_MODEL",
                  os.getenv("OLLAMA_CODER_MODEL", _DEFAULT_MODEL))
    ),
    "reflector": os.getenv(
        "OLLAMA_REFLECTOR_MODEL",
        _DEFAULT_MODEL
    ),
}

# ── Groq model map (unchanged from V3) ───────────────────────
GROQ_MODELS: dict[str, str] = {
    "planner":   os.getenv("GROQ_PLANNER_MODEL",   "llama-3.3-70b-versatile"),
    "executor":  os.getenv("GROQ_EXECUTOR_MODEL",  "llama-3.3-70b-versatile"),
    "reflector": os.getenv("GROQ_REFLECTOR_MODEL", "llama-3.3-70b-versatile"),
}

# ── Gemini model map (Google AI) ─────────────────────────────
GEMINI_MODELS: dict[str, str] = {
    "planner":   os.getenv("GEMINI_PLANNER_MODEL",   "gemini-2.0-flash-lite"),
    "executor":  os.getenv("GEMINI_EXECUTOR_MODEL",  "gemini-2.0-flash-lite"),
    "reflector": os.getenv("GEMINI_REFLECTOR_MODEL", "gemini-2.0-flash"),
}

# ── OpenRouter model map (OpenAI-compatible) ─────────────────
OPENROUTER_MODELS: dict[str, str] = {
    "planner":   os.getenv("OPENROUTER_PLANNER_MODEL",   "nvidia/llama-3.1-nemotron-70b"),
    "executor":  os.getenv("OPENROUTER_EXECUTOR_MODEL",  "nvidia/llama-3.1-nemotron-70b"),
    "reflector": os.getenv("OPENROUTER_REFLECTOR_MODEL", "nvidia/llama-3.1-nemotron-70b"),
}


# ════════════════════════════════════════════════════════════
# GLM-OCR CONFIGURATION (unchanged from V3 — kept exactly)
# ════════════════════════════════════════════════════════════
#
# GLM-OCR (https://github.com/zai-org/GLM-OCR) — vision/OCR only.
# NOT a reasoning LLM. ONLY called via glm_ocr_extract() tool.
#
# Mode A (ollama): ollama pull glm4v → GLM_OCR_MODE=ollama
# Mode B (http):   run GLM-OCR server → GLM_OCR_MODE=http, GLM_OCR_URL=...

GLM_OCR_MODE: str         = os.getenv("GLM_OCR_MODE",         "ollama")
GLM_OCR_OLLAMA_MODEL: str = os.getenv("GLM_OCR_OLLAMA_MODEL", "glm4v")
GLM_OCR_URL: str          = os.getenv("GLM_OCR_URL",          "http://localhost:7860")
GLM_OCR_TIMEOUT: int      = int(os.getenv("GLM_OCR_TIMEOUT",  "60"))
GLM_OCR_ENABLED: bool     = os.getenv("GLM_OCR_ENABLED", "true").lower() == "true"


def glm_ocr_call(
    image_path: Optional[str] = None,
    image_b64:  Optional[str] = None,
    prompt:     str            = "Extract all text from this image. Output only the extracted text.",
    ollama_url: str            = "http://localhost:11434",
) -> str:
    """
    Call GLM-OCR to extract text from an image.
    (Unchanged from V3 — kept exactly for compatibility.)

    Architecture:
        Agent step → glm_ocr_extract() tool → glm_ocr_call()
        Result injected into working memory as text.
        Reasoning agents stay text-only — they never see images.

    Args:
        image_path: Local file path (jpg/png/pdf)
        image_b64:  Base64-encoded image string
        prompt:     What to extract ("Get the invoice total and date")
        ollama_url: Ollama server URL (Mode A)

    Returns:
        Extracted text, or "ERROR: ..." on failure.
    """
    if not GLM_OCR_ENABLED:
        return "ERROR: GLM-OCR is disabled (GLM_OCR_ENABLED=false in .env)"

    if image_b64 is None and image_path:
        import base64
        try:
            with open(image_path, "rb") as f:
                image_b64 = base64.b64encode(f.read()).decode("utf-8")
        except FileNotFoundError:
            return f"ERROR: Image file not found: {image_path}"
        except Exception as e:
            return f"ERROR: Could not read image: {e}"

    if image_b64 is None:
        return "ERROR: Must provide either image_path or image_b64"

    # ── Mode A: Ollama ────────────────────────────────────────
    if GLM_OCR_MODE == "ollama":
        try:
            import ollama as _ollama_sdk
            response = _ollama_sdk.chat(
                model    = GLM_OCR_OLLAMA_MODEL,
                messages = [{
                    "role":    "user",
                    "content": prompt,
                    "images":  [image_b64],
                }],
                options  = {"temperature": 0.0},
            )
            return response["message"]["content"].strip()
        except ImportError:
            try:
                from langchain_ollama import ChatOllama
                from langchain_core.messages import HumanMessage
                llm = ChatOllama(
                    model       = GLM_OCR_OLLAMA_MODEL,
                    base_url    = ollama_url,
                    temperature = 0.0,
                )
                msg = HumanMessage(content=[
                    {"type": "text",      "text":      prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                ])
                return llm.invoke([msg]).content.strip()
            except Exception as e2:
                return f"ERROR: Ollama GLM call failed: {e2}"
        except Exception as e:
            return f"ERROR: GLM-OCR Ollama error: {e}"

    # ── Mode B: HTTP API ──────────────────────────────────────
    elif GLM_OCR_MODE == "http":
        try:
            import requests as _req
            resp = _req.post(
                f"{GLM_OCR_URL}/ocr",
                json    = {"image": image_b64, "prompt": prompt},
                timeout = GLM_OCR_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("text") or data.get("result") or str(data)
        except Exception as e:
            return f"ERROR: GLM-OCR HTTP error: {e}"

    return f"ERROR: Unknown GLM_OCR_MODE='{GLM_OCR_MODE}'. Use 'ollama' or 'http'."


# ════════════════════════════════════════════════════════════
# GROQ KEY ROTATOR (unchanged from V3 — kept exactly)
# ════════════════════════════════════════════════════════════

class GroqKeyRotator:
    """
    Thread-safe, infinite round-robin Groq API key rotator.

    WHY: Groq free tier ≈ 30 req/min per key.
         4 keys → ~120 req/min effective throughput.

    SETUP (.env): GROQ_KEYS=gsk_key1,gsk_key2,gsk_key3,gsk_key4

    USAGE:
        key        = rotator.next()
        idx, key   = rotator.next_with_index()
        rotator.record_error(idx)  # mark a failed key
        rotator.stats()            # per-key dashboard
    """

    def __init__(self, keys: list[str]):
        if not keys:
            raise ValueError("GroqKeyRotator needs at least 1 key. Set GROQ_KEYS= in .env")
        self._keys       = keys
        self._cycle      = itertools.cycle(enumerate(keys))
        self._lock       = threading.Lock()
        self._call_count = [0] * len(keys)
        self._err_count  = [0] * len(keys)
        self._total      = 0

    def next(self) -> str:
        _, key = self.next_with_index()
        return key

    def next_with_index(self) -> tuple[int, str]:
        with self._lock:
            idx, key = next(self._cycle)
            self._call_count[idx] += 1
            self._total += 1
            return idx, key

    def record_error(self, key_index: int) -> None:
        with self._lock:
            if 0 <= key_index < len(self._err_count):
                self._err_count[key_index] += 1

    def stats(self) -> list[dict]:
        with self._lock:
            return [
                {
                    "key_index": i,
                    "calls":     self._call_count[i],
                    "errors":    self._err_count[i],
                    "key_tail":  f"...{self._keys[i][-6:]}",
                }
                for i in range(len(self._keys))
            ]

    def total_calls(self) -> int:
        with self._lock:
            return self._total

    @property
    def count(self) -> int:
        return len(self._keys)


def _parse_groq_keys() -> list[str]:
    raw = os.getenv("GROQ_KEYS", "")
    return [k.strip() for k in raw.split(",") if k.strip()]


# ════════════════════════════════════════════════════════════
# MODEL REGISTRY HELPERS (V4 new)
# ════════════════════════════════════════════════════════════

def get_model_info(model_name: str) -> Optional[ModelProfile]:
    """
    Look up a model in the registry by its Ollama tag.

    Args:
        model_name: Exact Ollama tag (e.g. "qwen2.5-coder:3b")

    Returns:
        ModelProfile dict, or None if not in registry

    Usage:
        info = get_model_info("granite3.1-moe:3b")
        print(info["ram_gb"], info["best_for"])
    """
    return OLLAMA_MODEL_REGISTRY.get(model_name)


def list_model_registry(
    filter_best_for: Optional[str] = None,
    max_ram_gb:      Optional[float] = None,
) -> list[dict]:
    """
    Return all registry entries as a list of dicts (for API responses).

    Args:
        filter_best_for: Only return models recommended for this agent
                         ("planner" | "executor" | "reflector" | "vision_tool")
        max_ram_gb:      Only return models within this RAM limit

    Returns:
        List of model info dicts, sorted by RAM requirement

    React.js usage (GET /models):
        const models = await fetch('/models').then(r => r.json());
        models.filter(m => m.best_for.includes('planner'))
              .map(m => <ModelOption key={m.name} {...m} />)
    """
    entries = list(OLLAMA_MODEL_REGISTRY.values())

    if filter_best_for:
        entries = [e for e in entries if filter_best_for in e["best_for"]]

    if max_ram_gb is not None:
        entries = [e for e in entries if e["ram_gb"] <= max_ram_gb]

    # Sort by RAM (ascending — smallest first)
    entries.sort(key=lambda e: e["ram_gb"])
    return [dict(e) for e in entries]


def resolve_agent_models(
    model_map:  Optional[dict[str, str]] = None,
    provider:   Optional[str]            = None,
) -> dict[str, str]:
    """
    Resolve the final agent→model mapping for a run.

    Priority (first match wins per agent):
        1. model_map argument  (dynamic per-request override)
        2. OLLAMA_MODELS       (from env vars / global config)
        3. Hardcoded default   (qwen2.5:3b)

    Args:
        model_map: Optional dict overriding specific agents.
                   e.g. {"planner": "qwen2.5-coder:3b",
                         "executor": "granite3.1-moe:3b"}
        provider:  "ollama" | "groq" (defaults to LLM_PROVIDER env)

    Returns:
        Resolved {agent: model_name} dict for planner/executor/reflector

    Usage:
        # Standard run:
        models = resolve_agent_models()
        # → {"planner": "qwen2.5:3b", "executor": "qwen2.5:3b", ...}

        # Multi-model run:
        models = resolve_agent_models({
            "planner":   "qwen2.5-coder:3b",
            "executor":  "granite3.1-moe:3b",
            "reflector": "nemotron-mini",
        })
    """
    _provider = provider or os.getenv("LLM_PROVIDER", "ollama")
    base_map  = OLLAMA_MODELS if _provider == "ollama" else GROQ_MODELS
    override  = model_map or {}

    # Default model is nemotron-mini — best benchmark performer (V5 primary)
    _default = "nemotron-mini"
    return {
        "planner":   override.get("planner",   base_map.get("planner",   _default)),
        "executor":  override.get("executor",  base_map.get("executor",  _default)),
        "reflector": override.get("reflector", base_map.get("reflector", _default)),
    }


# ════════════════════════════════════════════════════════════
# LLM FACTORY — single construction point (enhanced for V4)
# ════════════════════════════════════════════════════════════

def llm_factory(
    agent:          str,
    provider:       Optional[str]            = None,
    groq_rotator:   Optional[GroqKeyRotator] = None,
    temperature:    Optional[float]          = None,
    model_override: Optional[str]            = None,
    model_map:      Optional[dict[str, str]] = None,
    num_ctx:        Optional[int]            = None,
) -> object:
    """
    Build and return a LangChain ChatModel for the given agent.

    The ONLY place LLMs are constructed in the entire system.
    Planner / Executor / Reflector all call this — never directly.

    Args:
        agent:          "planner" | "executor" | "reflector"
        provider:       "ollama" | "groq" (default: LLM_PROVIDER env)
        groq_rotator:   Shared GroqKeyRotator for key rotation (Groq only)
        temperature:    Override temperature (default: AGENT_TEMPERATURES)
        model_override: Force one specific model for this agent
        model_map:      Full per-agent override dict. If set, takes priority
                        over model_override for the specific agent key.

    Returns:
        LangChain ChatModel — ChatOllama or ChatGroq

    MODEL RESOLUTION ORDER:
        1. model_map[agent]   — per-request multi-model override
        2. model_override      — single model override
        3. OLLAMA_MODELS[agent]— env-configured per-agent model
        4. OLLAMA_MODEL env    — global env fallback
        5. "qwen2.5:3b"        — hardcoded default

    NOTE on GLM-OCR:
        GLM-OCR is NOT built here. It is a tool, not an agent LLM.
        Use glm_ocr_call() for image extraction.

    ADDING A NEW PROVIDER (for open-source developers):
        Add an elif branch below, then set LLM_PROVIDER=<name>:
            elif _provider == "openai":
                from langchain_openai import ChatOpenAI
                return ChatOpenAI(model=..., api_key=..., temperature=temp)

    MULTI-MODEL EXAMPLE (model_battle.py pattern):
        llm = llm_factory("planner",
                          model_map={"planner": "qwen2.5-coder:3b",
                                     "executor": "granite3.1-moe:3b"})
        # → uses qwen2.5-coder:3b for planner only
    """
    _provider = provider or os.getenv("LLM_PROVIDER", "ollama")
    temp      = temperature if temperature is not None else AGENT_TEMPERATURES.get(agent, 0.2)

    # Resolve model: model_map > model_override > per-agent env > global env > default
    if model_map and agent in model_map:
        _model_name = model_map[agent]
    elif model_override:
        _model_name = model_override
    else:
        _model_name = None  # will resolve per-provider below

    if _provider == "ollama":
        from langchain_ollama import ChatOllama
        model = _model_name or OLLAMA_MODELS.get(agent, os.getenv("OLLAMA_MODEL", "nemotron-mini"))
        # Build ChatOllama kwargs — num_ctx controls the context window.
        # graph.py passes agent-specific context sizes from AGENT_CONTEXT_WINDOWS.
        ollama_kwargs: dict = {
            "model":       model,
            "base_url":    os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            "temperature": temp,
        }
        if num_ctx is not None:
            # num_ctx sets Ollama's context window for this call.
            # Capped at CONTEXT_WINDOW_MAX to prevent OOM on small machines.
            _ctx = min(num_ctx, CONTEXT_WINDOW_MAX)
            ollama_kwargs["num_ctx"] = _ctx
        return ChatOllama(**ollama_kwargs)

    elif _provider == "groq":
        from langchain_groq import ChatGroq
        if groq_rotator is None:
            keys = _parse_groq_keys()
            if not keys:
                raise RuntimeError(
                    "GROQ_KEYS is required when LLM_PROVIDER=groq. Set in .env"
                )
            groq_rotator = GroqKeyRotator(keys)
        idx, api_key = groq_rotator.next_with_index()
        model        = _model_name or GROQ_MODELS.get(agent, "llama-3.3-70b-versatile")
        try:
            return ChatGroq(model=model, api_key=api_key, temperature=temp)
        except Exception as e:
            groq_rotator.record_error(idx)
            raise RuntimeError(f"ChatGroq key[{idx}] failed: {e}") from e

    elif _provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is required when LLM_PROVIDER=gemini. Set in .env"
            )
        model = _model_name or GEMINI_MODELS.get(agent, "gemini-2.0-flash-lite")
        try:
            return ChatGoogleGenerativeAI(
                model=model,
                google_api_key=api_key,
                temperature=temp,
                convert_system_message_to_human=True
            )
        except Exception as e:
            raise RuntimeError(f"ChatGoogleGenerativeAI failed: {e}") from e

    elif _provider == "openrouter":
        from langchain_openai import ChatOpenAI
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise RuntimeError(
                "OPENROUTER_API_KEY is required when LLM_PROVIDER=openrouter. Set in .env"
            )
        model = _model_name or OPENROUTER_MODELS.get(agent, "nvidia/llama-3.1-nemotron-70b")
        try:
            return ChatOpenAI(
                model=model,
                api_key=api_key,
                base_url="https://openrouter.ai/api/v1",
                temperature=temp,
                default_headers={
                    "HTTP-Referer": os.getenv("PROJECT_URL", "http://localhost"),
                    "X-Title": os.getenv("PROJECT_NAME", "NexaWorks HRMS")
                }
            )
        except Exception as e:
            raise RuntimeError(f"OpenRouter ChatOpenAI failed: {e}") from e

    else:
        raise ValueError(
            f"Unknown LLM_PROVIDER: '{_provider}'. Supported: 'ollama', 'groq', 'gemini', 'openrouter'.\n"
            f"To add a provider, add an elif branch in llm_factory() in config.py."
        )


# ════════════════════════════════════════════════════════════
# SYSTEM CONFIG — central singleton (V4 enhanced)
# ════════════════════════════════════════════════════════════

class SystemConfig:
    """
    Central configuration. Imported as `cfg` by all modules.

    ─────────────────────────────────────────────────────────
    COMPLETE ENV VARIABLE REFERENCE (V4)
    ─────────────────────────────────────────────────────────
    LLM_PROVIDER             = ollama | groq          (default: ollama)
    OLLAMA_BASE_URL          = http://localhost:11434
    OLLAMA_MODEL             = qwen2.5:3b              (global default)
    OLLAMA_PLANNER_MODEL     = qwen2.5-coder:3b        (per-agent)
    OLLAMA_EXECUTOR_MODEL    = granite3.1-moe:3b       (per-agent)
    OLLAMA_REFLECTOR_MODEL   = nemotron-mini           (per-agent)
    OLLAMA_FAST_MODEL        = qwen2.5-coder:1.5b      (role alias)
    OLLAMA_QUALITY_MODEL     = qwen2.5:7b              (role alias)
    OLLAMA_CODER_MODEL       = qwen2.5-coder:3b        (role alias)
    GROQ_KEYS                = gsk_k1,gsk_k2,...       (required for groq)
    GROQ_PLANNER_MODEL       = llama-3.3-70b-versatile
    GROQ_EXECUTOR_MODEL      = llama-3.3-70b-versatile
    GROQ_REFLECTOR_MODEL     = llama-3.3-70b-versatile
    GLM_OCR_MODE             = ollama | http
    GLM_OCR_OLLAMA_MODEL     = glm4v
    GLM_OCR_URL              = http://localhost:7860
    GLM_OCR_TIMEOUT          = 60
    GLM_OCR_ENABLED          = true | false
    PROJECT_NAME             = UniversalAgent
    PROJECT_VERSION          = 1.0.0
    SYSTEM_PROMPT            = "You are..."
    PLANNER_TEMP             = 0.3
    EXECUTOR_TEMP            = 0.1
    REFLECTOR_TEMP           = 0.2
    MAX_ITERATIONS           = 10
    MAX_REFLECTION_LOOPS     = 3
    DB_URL                   = sqlite:///./memory/json/agent.db
    DB_ECHO                  = false
    DB_POOL_SIZE             = 5
    EMBEDDING_MODEL          = all-MiniLM-L6-v2
    VECTOR_TOP_K             = 5
    SERVER_HOST              = 0.0.0.0
    SERVER_PORT              = 8000
    LOG_LEVEL                = INFO
    LOG_RETENTION_DAYS       = 30
    ─────────────────────────────────────────────────────────
    """

    # ── Project identity ─────────────────────────────────────
    PROJECT_NAME:        str = os.getenv("PROJECT_NAME",        "UniversalAgent")
    PROJECT_VERSION:     str = os.getenv("PROJECT_VERSION",     "1.5.0")
    PROJECT_DESCRIPTION: str = os.getenv("PROJECT_DESCRIPTION", "A universal AI agentic system.")
    SYSTEM_PROMPT: str = os.getenv(
        "SYSTEM_PROMPT",
        "You are an intelligent AI agent. Analyze tasks carefully, "
        "use available tools, and deliver accurate, well-reasoned responses."
    )

    # ── LLM provider ─────────────────────────────────────────
    # Provider chain priority: ollama → groq → gemini → openrouter
    PROVIDER: Literal["groq", "ollama", "gemini", "openrouter"] = os.getenv("LLM_PROVIDER", "ollama")  # type: ignore
    OLLAMA_BASE_URL: str  = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_MODELS:   dict = OLLAMA_MODELS           # per-agent map (env-resolved)
    GROQ_KEYS:       list = _parse_groq_keys()
    GROQ_MODELS:     dict = GROQ_MODELS
    GROQ_RETRY_ON_RATE_LIMIT: bool = (
        os.getenv("GROQ_RETRY_ON_RATE_LIMIT", "true").lower() == "true"
    )
    _groq_rotator: Optional[GroqKeyRotator] = None

    # ── Gemini (Google AI) ───────────────────────────────────
    GEMINI_API_KEY: str  = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODELS:  dict = GEMINI_MODELS

    # ── OpenRouter ────────────────────────────────────────────
    OPENROUTER_API_KEY: str  = os.getenv("OPENROUTER_API_KEY", "")
    OPENROUTER_MODELS:  dict = OPENROUTER_MODELS

    # ── V4: runtime model override (set per-request by graph.py) ─
    # When a /run request includes model_map, graph.py calls
    # cfg.set_agent_models() to apply for the duration of that run.
    _runtime_model_map: Optional[dict[str, str]] = None

    # ── GLM-OCR (unchanged from V3) ──────────────────────────
    GLM_OCR_MODE:         str  = GLM_OCR_MODE
    GLM_OCR_OLLAMA_MODEL: str  = GLM_OCR_OLLAMA_MODEL
    GLM_OCR_URL:          str  = GLM_OCR_URL
    GLM_OCR_TIMEOUT:      int  = GLM_OCR_TIMEOUT
    GLM_OCR_ENABLED:      bool = GLM_OCR_ENABLED

    # ── Execution ────────────────────────────────────────────
    AGENT_TEMPERATURES:   dict = AGENT_TEMPERATURES
    MAX_ITERATIONS:       int  = int(os.getenv("MAX_ITERATIONS",       "10"))
    MAX_REFLECTION_LOOPS: int  = int(os.getenv("MAX_REFLECTION_LOOPS", "3"))

    # ── Database ─────────────────────────────────────────────
    DB_URL:       str  = os.getenv("DB_URL", f"sqlite:///{MEMORY_JSON_DIR}/agent.db")
    DB_ECHO:      bool = os.getenv("DB_ECHO", "false").lower() == "true"
    DB_POOL_SIZE: int  = int(os.getenv("DB_POOL_SIZE", "5"))

    # ── Memory ───────────────────────────────────────────────
    EPISODIC_FILE:   Path = MEMORY_JSON_DIR / "episodic.jsonl"
    ENTITY_JSON_DIR: Path = MEMORY_JSON_DIR
    ENTITY_MD_DIR:   Path = MEMORY_MD_DIR
    VECTOR_INDEX:    Path = VECTOR_INDEX_DIR
    EMBEDDING_MODEL: str  = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
    VECTOR_TOP_K:    int  = int(os.getenv("VECTOR_TOP_K", "5"))
    MEMORY_JSON_DIR: Path = MEMORY_JSON_DIR
    MEMORY_MD_DIR:   Path = MEMORY_MD_DIR

    # ── Logging ──────────────────────────────────────────────
    LOG_JSON_DIR:       Path = LOG_JSON_DIR
    LOG_MD_DIR:         Path = LOG_MD_DIR
    LOG_LEVEL:          str  = os.getenv("LOG_LEVEL", "INFO")
    LOG_RETENTION_DAYS: int  = int(os.getenv("LOG_RETENTION_DAYS", "30"))

    # ── Server ───────────────────────────────────────────────
    SERVER_HOST: str = os.getenv("SERVER_HOST", "0.0.0.0")
    SERVER_PORT: int = int(os.getenv("SERVER_PORT", "8000"))

    # ── Skills ───────────────────────────────────────────────
    SKILLS_DIR:    Path = SKILLS_DIR
    SKILLS_MD_DIR: Path = SKILLS_MD_DIR
    BASE_DIR:      Path = BASE_DIR

    # ── Model registry ───────────────────────────────────────
    MODEL_REGISTRY: dict = OLLAMA_MODEL_REGISTRY

    # ── Methods ──────────────────────────────────────────────

    def groq_rotator(self) -> GroqKeyRotator:
        """Lazy-init shared GroqKeyRotator (all agents share one instance)."""
        if self._groq_rotator is None:
            if not self.GROQ_KEYS:
                raise RuntimeError("GROQ_KEYS required when LLM_PROVIDER=groq. Set in .env")
            self._groq_rotator = GroqKeyRotator(self.GROQ_KEYS)
        return self._groq_rotator

    def set_agent_models(self, model_map: Optional[dict[str, str]]) -> None:
        """
        Set a runtime model override for the current request.

        Called by graph.py when a /run request includes model_map.
        Thread-safety note: this is per-process, not per-thread.
        For true concurrent multi-model requests use separate processes.

        Args:
            model_map: {"planner": "qwen2.5-coder:3b",
                        "executor": "granite3.1-moe:3b",
                        "reflector": "nemotron-mini"}
                       or None to clear overrides.

        Usage (in graph.py):
            cfg.set_agent_models(state.get("model_map"))
            # ... run graph ...
            cfg.set_agent_models(None)  # clear after run
        """
        self._runtime_model_map = model_map

    def get_active_model_map(self) -> dict[str, str]:
        """
        Return the currently active agent→model mapping.

        Merges runtime overrides with env-configured defaults.

        Returns:
            {"planner": "...", "executor": "...", "reflector": "..."}

        Usage:
            models = cfg.get_active_model_map()
            print(f"Planner is using: {models['planner']}")
        """
        return resolve_agent_models(
            model_map = self._runtime_model_map,
            provider  = self.PROVIDER,
        )

    def get_llm(self, agent: str, model_override: Optional[str] = None):
        """
        Build the LLM for an agent role.

        Respects runtime model_map set via set_agent_models().

        Args:
            agent:          "planner" | "executor" | "reflector"
            model_override: Force one specific model (overrides everything)

        Returns:
            LangChain ChatModel

        Usage:
            llm = cfg.get_llm("planner")
            llm = cfg.get_llm("executor", model_override="granite3.1-moe:3b")
        """
        rotator = self.groq_rotator() if self.PROVIDER == "groq" else None
        # Use agent-specific context window (Ollama only; ignored by Groq)
        ctx = AGENT_CONTEXT_WINDOWS.get(agent)
        return llm_factory(
            agent          = agent,
            provider       = self.PROVIDER,
            groq_rotator   = rotator,
            model_override = model_override,
            model_map      = self._runtime_model_map,
            num_ctx        = ctx,
        )

    def get_model_info(self, model_name: str) -> Optional[ModelProfile]:
        """
        Look up a model in the registry.

        Args:
            model_name: Ollama tag (e.g. "granite3.1-moe:3b")

        Returns:
            ModelProfile or None
        """
        return get_model_info(model_name)

    def summary(self) -> dict:
        """Safe config summary for /health endpoint (no secrets)."""
        active_models = self.get_active_model_map()
        base: dict = {
            "project":              self.PROJECT_NAME,
            "version":              self.PROJECT_VERSION,
            "provider":             self.PROVIDER,
            "active_agent_models":  active_models,
            "max_iterations":       self.MAX_ITERATIONS,
            "max_reflection_loops": self.MAX_REFLECTION_LOOPS,
            "temperatures":         self.AGENT_TEMPERATURES,
            "embedding_model":      self.EMBEDDING_MODEL,
            "vector_top_k":         self.VECTOR_TOP_K,
            "db_url":               self._mask_db_url(self.DB_URL),
            "log_retention_days":   self.LOG_RETENTION_DAYS,
            "glm_ocr_enabled":      self.GLM_OCR_ENABLED,
            "glm_ocr_mode":         self.GLM_OCR_MODE,
            "registered_models":    len(self.MODEL_REGISTRY),
        }
        if self.PROVIDER == "ollama":
            base["ollama_url"] = self.OLLAMA_BASE_URL
        elif self.PROVIDER == "groq":
            base.update({
                "groq_models":    self.GROQ_MODELS,
                "groq_key_count": len(self.GROQ_KEYS),
                "groq_retry":     self.GROQ_RETRY_ON_RATE_LIMIT,
            })
            if self._groq_rotator:
                base["groq_key_stats"]   = self._groq_rotator.stats()
                base["groq_total_calls"] = self._groq_rotator.total_calls()
        return base

    @staticmethod
    def _mask_db_url(url: str) -> str:
        if "://" not in url:
            return url
        try:
            scheme, rest = url.split("://", 1)
            if "@" in rest:
                creds, host = rest.rsplit("@", 1)
                return f"{scheme}://{creds.split(':')[0]}:***@{host}"
            return url
        except Exception:
            return "***"


# ── Singleton ──────────────────────────────────────────────────
cfg = SystemConfig()
