# ============================================================
# tools.py — Built-in Tool Definitions
# ============================================================
# IMPROVED IN THIS VERSION:
#   + db_tool: SQLAlchemy-backed DB query tool, reads cfg.DB_URL
#     Works with SQLite/PostgreSQL/MySQL — zero code changes needed
#   + db_execute: write (INSERT/UPDATE/DELETE) counterpart to db_query
#   + get_tool_descriptions(): now includes db_tool and skill_call docs
#   + Full domain extension guide for each tool category
#   + Tool argument schemas documented for Planner's use
#   + All tools safe-guarded: no eval(), no shell injection
#   + web_search_placeholder: clear instructions for real integration
#
# ════════════════════════════════════════════════════════════
# TOOL CATALOG
# ════════════════════════════════════════════════════════════
#
#   Built-in (always available):
#     calculator          → safe math eval (no exec/eval)
#     current_datetime    → UTC timestamp
#     memory_search       → semantic vector search (RAG)
#     save_to_memory      → persist to entity or vector store
#     skill_call          → proxy to any /skills/ file
#     list_available_skills → list loaded skills
#     db_query            → SQL SELECT via cfg.DB_URL (SQLite/PG/MySQL)
#     db_execute          → SQL INSERT/UPDATE/DELETE
#     web_search_placeholder → stub (replace with real API)
#
#   Skill-provided (auto-discovered from /skills/):
#     fraud_risk_scorer   → example domain skill
#     (your_skill)        → any .py file in /skills/
#
# ════════════════════════════════════════════════════════════
# ADDING TOOLS FOR A NEW DOMAIN
# ════════════════════════════════════════════════════════════
#
#   Option A — New built-in tool (this file):
#     @tool
#     def risk_score_tool(transaction_data: str) -> str:
#         """Score a transaction for fraud risk."""
#         data = json.loads(transaction_data)
#         score = my_model(data)
#         return json.dumps({"risk_score": score})
#     # Then add to BUILTIN_TOOLS list at the bottom.
#
#   Option B — Skill file (recommended for domain tools):
#     Create /skills/risk_scorer.py with SKILL_METADATA + run()
#     → Auto-loaded, no tools.py changes needed
#     → Accessible via: skill_call("risk_scorer", '{"amount": 5000}')
#
#   Option C — External API as a tool:
#     @tool
#     def market_data(ticker: str) -> str:
#         """Fetch latest market data for a stock ticker."""
#         resp = requests.get(f"https://api.example.com/price/{ticker}")
#         return resp.json()["price"]
#
# ════════════════════════════════════════════════════════════
# PLANNER TOOL ARGUMENT FORMAT
# ════════════════════════════════════════════════════════════
#
#   When Planner references a tool in a plan step, it must use
#   the EXACT tool name and argument keys shown here:
#
#   calculator:           { "expression": "2400 * 0.15" }
#   current_datetime:     { "timezone": "UTC" }
#   memory_search:        { "query": "fraud TX001", "top_k": 5 }
#   save_to_memory:       { "key": "user_42", "value": "...", "memory_type": "entity" }
#   skill_call:           { "skill_name": "fraud_risk_scorer", "input_json": "{...}" }
#   list_available_skills:(no args)
#   db_query:             { "sql": "SELECT * FROM transactions WHERE amount > 9000" }
#   db_execute:           { "sql": "INSERT INTO flags(txn_id) VALUES ('TX001')" }
#
# ============================================================

import ast
import json
import math
import operator as op
import datetime
from typing import Any

from langchain_core.tools import tool

from logger import get_logger
import skill_loader as sl

log = get_logger("tools")


# ════════════════════════════════════════════════════════════
# SAFE MATH EVALUATOR
# ════════════════════════════════════════════════════════════

_SAFE_OPS = {
    ast.Add:  op.add,
    ast.Sub:  op.sub,
    ast.Mult: op.mul,
    ast.Div:  op.truediv,
    ast.Pow:  op.pow,
    ast.USub: op.neg,
    ast.Mod:  op.mod,
}

_SAFE_FUNCS = {
    "abs":   abs,
    "round": round,
    "sqrt":  math.sqrt,
    "log":   math.log,
    "log10": math.log10,
    "sin":   math.sin,
    "cos":   math.cos,
    "tan":   math.tan,
    "ceil":  math.ceil,
    "floor": math.floor,
}


def _safe_eval(node: ast.expr) -> float:
    """Recursively evaluate an AST node with only safe operations."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.BinOp):
        return _SAFE_OPS[type(node.op)](
            _safe_eval(node.left), _safe_eval(node.right)
        )
    if isinstance(node, ast.UnaryOp):
        return _SAFE_OPS[type(node.op)](_safe_eval(node.operand))
    if isinstance(node, ast.Call):
        fn = node.func.id if isinstance(node.func, ast.Name) else None
        if fn and fn in _SAFE_FUNCS:
            args = [_safe_eval(a) for a in node.args]
            return _SAFE_FUNCS[fn](*args)
    raise ValueError(f"Unsafe or unsupported expression: {ast.dump(node)}")


# ════════════════════════════════════════════════════════════
# BUILT-IN TOOLS
# ════════════════════════════════════════════════════════════

@tool
def calculator(expression: str) -> str:
    """
    Safely evaluate a mathematical expression. No code execution.

    Supports: +, -, *, /, **, %, abs, round, sqrt, log, log10,
              sin, cos, tan, ceil, floor

    Args:
        expression: Math expression string

    Returns:
        String result or error message

    Plan step args:  { "expression": "2400 * 0.15" }
    Examples:
        calculator("2 + 2")           → "4"
        calculator("sqrt(144)")       → "12.0"
        calculator("2400 * 0.15")     → "360.0"
        calculator("100 / (1+0.05)")  → "95.238..."
    """
    try:
        tree   = ast.parse(expression, mode="eval")
        result = _safe_eval(tree.body)
        return str(result)
    except Exception as e:
        return f"Calculator error: {e}"


@tool
def current_datetime(timezone: str = "UTC") -> str:
    """
    Return the current date and time.

    Args:
        timezone: Only "UTC" is currently supported

    Returns:
        ISO 8601 formatted datetime string

    Plan step args:  { "timezone": "UTC" }
    Example:         "2025-01-15T14:30:22.456789Z"
    """
    return datetime.datetime.utcnow().isoformat() + "Z"


@tool
def memory_search(query: str, top_k: int = 5) -> str:
    """
    Semantic search over the vector memory store (RAG).

    Searches all past Q&A pairs and seeded domain knowledge
    using sentence-transformer embeddings + FAISS.

    Args:
        query: Natural language search string
        top_k: Number of results (1-20, default 5)

    Returns:
        JSON array of { text, metadata, score } results

    Plan step args:  { "query": "fraud wire transfer offshore", "top_k": 3 }
    """
    try:
        from memory.vector_store import VectorMemoryStore
        results = VectorMemoryStore().search(query, top_k=top_k)
        return json.dumps(results, ensure_ascii=False)
    except Exception as e:
        log.warning(f"memory_search failed: {e}")
        return json.dumps({"error": str(e), "results": []})


@tool
def save_to_memory(key: str, value: str, memory_type: str = "entity") -> str:
    """
    Persist a key-value pair to long-term memory.

    Args:
        key:         Memory key (e.g., "user_42_risk", "project_context")
        value:       String content to store
        memory_type: "entity" (structured, .md + .json files)
                     "vector" (indexed for semantic search)

    Returns:
        "OK" on success, error message on failure

    Plan step args:
        { "key": "risk_assessment", "value": "High risk: score=0.87", "memory_type": "entity" }
    """
    try:
        if memory_type == "entity":
            from memory.entity_memory import EntityMemory
            EntityMemory().set(key, {"value": value, "stored_at":
                                     datetime.datetime.utcnow().isoformat() + "Z"})
            return "OK"
        elif memory_type == "vector":
            from memory.vector_store import VectorMemoryStore
            VectorMemoryStore().add_texts([value], metadatas=[{"key": key}])
            return "OK"
        else:
            return f"Error: unknown memory_type '{memory_type}' (use 'entity' or 'vector')"
    except Exception as e:
        return f"Error: {e}"


@tool
def skill_call(skill_name: str, input_json: str) -> str:
    """
    Call any registered skill by name with JSON input.

    Skills are auto-loaded from /skills/*.py at startup.
    Use list_available_skills() to see what's loaded.

    Args:
        skill_name: Exact name from SKILL_METADATA["name"]
        input_json: JSON string matching the skill's run() input spec

    Returns:
        JSON string of the skill's output dict

    Plan step args:
        {
          "skill_name": "fraud_risk_scorer",
          "input_json": "{\"amount\": 9800, \"country\": \"NG\", \"account_age_days\": 2}"
        }

    Output format: { "success": bool, "result": any, "error": str|null }
    """
    registry = sl.get_registry()
    try:
        input_data = json.loads(input_json)
    except json.JSONDecodeError as e:
        return json.dumps({"success": False, "error": f"Invalid JSON: {e}"})
    result = registry.call(skill_name, input_data)
    return json.dumps(result, ensure_ascii=False)


@tool
def list_available_skills() -> str:
    """
    List all skills currently loaded in the registry.

    Returns:
        JSON array of { name, description, version, file }

    Plan step args: (none)
    Use when you need to check if a specific skill is available.
    """
    registry = sl.get_registry()
    return json.dumps(registry.list_skills(), indent=2)


# ════════════════════════════════════════════════════════════
# DATABASE TOOLS — reads cfg.DB_URL (SQLite/PostgreSQL/MySQL)
# ════════════════════════════════════════════════════════════

@tool
def db_query(sql: str) -> str:
    """
    Execute a SQL SELECT query against the configured database.

    Database is configured via DB_URL in .env:
        SQLite:     sqlite:///./memory/json/agent.db    (default)
        PostgreSQL: postgresql://user:pass@host:5432/db
        MySQL:      mysql+pymysql://user:pass@host/db

    Args:
        sql: SQL SELECT statement (read-only)

    Returns:
        JSON array of row dicts, or error message

    Plan step args:
        { "sql": "SELECT amount, country FROM transactions WHERE amount > 9000 LIMIT 10" }

    Output example:
        [{"amount": 9800, "country": "NG"}, {"amount": 11000, "country": "RU"}]

    SECURITY: Only SELECT statements are executed by this tool.
              Use db_execute for writes.
    """
    try:
        from sqlalchemy import create_engine, text
        from config import cfg

        # Guard: only allow SELECT
        stripped = sql.strip().upper()
        if not stripped.startswith("SELECT") and not stripped.startswith("WITH"):
            return json.dumps({"error": "db_query only allows SELECT/WITH statements. Use db_execute for writes."})

        engine = create_engine(cfg.DB_URL, echo=cfg.DB_ECHO)
        with engine.connect() as conn:
            result = conn.execute(text(sql))
            rows   = [dict(row._mapping) for row in result]
        return json.dumps(rows, ensure_ascii=False, default=str)

    except ImportError:
        return json.dumps({"error": "SQLAlchemy not installed. Run: pip install sqlalchemy"})
    except Exception as e:
        log.error(f"db_query failed: {e}")
        return json.dumps({"error": str(e)})


@tool
def db_execute(sql: str) -> str:
    """
    Execute a SQL INSERT/UPDATE/DELETE against the configured database.

    Database is configured via DB_URL in .env (same as db_query).

    Args:
        sql: SQL DML statement (INSERT / UPDATE / DELETE)

    Returns:
        JSON with rowcount and status, or error message

    Plan step args:
        { "sql": "INSERT INTO fraud_flags (txn_id, score) VALUES ('TX001', 0.92)" }

    Output example:
        { "status": "ok", "rowcount": 1 }

    SECURITY: SELECT statements are blocked — use db_query for reads.
    """
    try:
        from sqlalchemy import create_engine, text
        from config import cfg

        stripped = sql.strip().upper()
        if stripped.startswith("SELECT") or stripped.startswith("WITH"):
            return json.dumps({"error": "db_execute does not allow SELECT. Use db_query."})

        engine = create_engine(cfg.DB_URL, echo=cfg.DB_ECHO)
        with engine.begin() as conn:
            result = conn.execute(text(sql))
        return json.dumps({"status": "ok", "rowcount": result.rowcount})

    except ImportError:
        return json.dumps({"error": "SQLAlchemy not installed. Run: pip install sqlalchemy"})
    except Exception as e:
        log.error(f"db_execute failed: {e}")
        return json.dumps({"error": str(e)})


@tool
def web_search_placeholder(query: str) -> str:
    """
    Placeholder for web search — not yet implemented.

    To enable real web search:
      1. Choose an API: SerpAPI, Tavily, DuckDuckGo, Brave Search
      2. Create /skills/web_search.py implementing their SDK
      3. Add your API key to .env (e.g., SERPAPI_KEY=...)
      4. Call via: skill_call("web_search", '{"query": "..."}')

    Args:
        query: Search query string

    Returns:
        Instruction message
    """
    return (
        f"[Web search not configured]\n"
        f"Query: '{query}'\n"
        f"To enable: create skills/web_search.py. "
        f"See skills/fraud_risk_scorer.py for the skill template."
    )


# ════════════════════════════════════════════════════════════
# GLM-OCR VISION TOOL
# ════════════════════════════════════════════════════════════
#
# GLM-OCR (https://github.com/zai-org/GLM-OCR) is a vision model
# used ONLY for image/document OCR extraction.
# It is NOT the reasoning LLM — agents (Planner/Executor/Reflector)
# still use qwen2.5 or groq for all reasoning tasks.
#
# This tool is called when the Planner includes a step like:
#   { "tool": "glm_ocr_extract",
#     "args": { "image_path": "/tmp/invoice.png",
#               "extraction_goal": "Extract total amount and date" } }
#
# SETUP:
#   Mode A (Ollama):  ollama pull glm4v
#                     GLM_OCR_MODE=ollama
#   Mode B (HTTP API): Run GLM-OCR server, GLM_OCR_MODE=http
#
# Plan step args:
#   { "image_path": "/path/to/image.png",
#     "extraction_goal": "Extract all invoice line items" }
#   OR
#   { "image_b64": "<base64 string>",
#     "extraction_goal": "Read the text on this form" }

@tool
def glm_ocr_extract(image_path: str = "", image_b64: str = "",
                    extraction_goal: str = "Extract all text from this image.") -> str:
    """
    Extract text from an image using GLM-OCR vision model.

    Use this tool when a plan step requires reading text from:
    - Photos of documents, invoices, receipts
    - Screenshots, scanned pages
    - Any image containing text

    Args:
        image_path:      Local file path to image (jpg/png/pdf)
        image_b64:       Base64-encoded image (alternative to path)
        extraction_goal: What to extract (e.g., "Get the total amount")

    Returns:
        Extracted text string from the image.
        Returns "ERROR: ..." if GLM-OCR is unavailable.

    Plan step args:
        { "image_path": "/tmp/invoice.jpg",
          "extraction_goal": "Extract vendor name, date, total amount" }

    NOTE: GLM-OCR must be available (Ollama glm4v or HTTP server).
          Check GLM_OCR_ENABLED and GLM_OCR_MODE in .env.
          If disabled, returns an informative error message.

    React.js — how to send image for OCR:
        // Step 1: upload image → POST /memory/vector/add or a file endpoint
        // Step 2: run agent with the image path in metadata:
        fetch('/run', {
          method: 'POST',
          body: JSON.stringify({
            query: "Read and summarize this invoice",
            metadata: { image_path: "/uploads/invoice.jpg" }
          })
        });
        // The agent will automatically call glm_ocr_extract() as a tool step
    """
    from config import glm_ocr_call, cfg

    if not cfg.GLM_OCR_ENABLED:
        return (
            "GLM-OCR is disabled (GLM_OCR_ENABLED=false). "
            "Enable it in .env and ensure the model is available."
        )

    if not image_path and not image_b64:
        return "ERROR: Provide either image_path or image_b64 argument."

    log.info(
        f"🔍 GLM-OCR: mode={cfg.GLM_OCR_MODE} | "
        f"model={cfg.GLM_OCR_OLLAMA_MODEL} | "
        f"goal='{extraction_goal[:60]}'"
    )

    result = glm_ocr_call(
        image_path = image_path or None,
        image_b64  = image_b64  or None,
        prompt     = extraction_goal,
        ollama_url = cfg.OLLAMA_BASE_URL,
    )

    if result.startswith("ERROR:"):
        log.warning(f"GLM-OCR failed: {result}")
    else:
        log.info(f"GLM-OCR extracted {len(result)} chars")

    return result


# ════════════════════════════════════════════════════════════
# MODEL REGISTRY TOOL (V4 new)
# ════════════════════════════════════════════════════════════

@tool
def get_available_models(role: str = "", max_ram_gb: float = 0) -> str:
    """
    List all Ollama models available in the registry.

    Use this tool when you need to know what models are registered
    and which are best suited for a given agent role.

    Args:
        role:       Filter by agent role: "planner" | "executor" |
                    "reflector" | "vision_tool" | "" (all models)
        max_ram_gb: Only list models requiring <= this many GB RAM.
                    Use 0 for no RAM filter.

    Returns:
        JSON string listing models with their metadata.

    Plan step args:
        { "role": "executor" }
        { "role": "planner", "max_ram_gb": 4.0 }

    Example output:
        [{"name": "granite3.1-moe:3b", "label": "Granite 3.1 MoE 3B",
          "params": "3B", "ram_gb": 2.5, "speed": "fast",
          "pull_cmd": "ollama pull granite3.1-moe:3b", ...}]
    """
    from config import list_model_registry
    models = list_model_registry(
        filter_best_for = role or None,
        max_ram_gb      = max_ram_gb if max_ram_gb > 0 else None,
    )
    return json.dumps(models, indent=2)


# ════════════════════════════════════════════════════════════
# TOOL REGISTRY
# ════════════════════════════════════════════════════════════

BUILTIN_TOOLS = [
    calculator,
    current_datetime,
    memory_search,
    save_to_memory,
    skill_call,
    list_available_skills,
    db_query,
    db_execute,
    glm_ocr_extract,          # GLM-OCR vision/OCR tool (kept from V3)
    get_available_models,     # V4: query the Ollama model registry
    web_search_placeholder,
]


def get_all_tools() -> list:
    """
    Return all built-in tools available to the Executor.

    Returns:
        List of LangChain BaseTool objects

    Usage:
        tools = get_all_tools()
        dispatcher = { t.name: t for t in tools }
    """
    return BUILTIN_TOOLS


def get_tool_descriptions() -> str:
    """
    Return a formatted string of all tools + their first-line doc.
    Injected into the Planner prompt so it knows what tools exist.

    Returns:
        Multi-line string: "- **tool_name**: description"

    Example output:
        - **calculator**: Safely evaluate a mathematical expression.
        - **memory_search**: Semantic search over the vector memory store.
        - **skill_call**: Call any registered skill by name with JSON input.
        - **db_query**: Execute a SQL SELECT query against the database.
    """
    lines = []
    for t in BUILTIN_TOOLS:
        first_line = (t.description or "").strip().splitlines()[0]
        lines.append(f"- **{t.name}**: {first_line}")

    # Also list loaded skills (so Planner can reference them by name)
    try:
        registry = sl.get_registry()
        if registry.names:
            lines.append("")
            lines.append("Skills (call via skill_call):")
            for skill in registry.list_skills():
                desc = (skill.get("description") or "").splitlines()[0][:80]
                lines.append(f"  - **{skill['name']}**: {desc}")
    except Exception:
        pass

    return "\n".join(lines)
