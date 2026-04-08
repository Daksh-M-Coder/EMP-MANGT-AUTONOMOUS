# ============================================================
# planner.py — Planner Agent Node
# ============================================================
# IMPROVED IN THIS VERSION:
#   + Dual memory writes on every run:
#       JSON: memory/json/planner_YYYY-MM-DD.jsonl (full + thinking)
#       MD:   memory/md/planner_plans.md (clean step list only)
#   + React.js developer guide: what Planner emits in RunResponse
#   + Universal template: PLANNER_SYSTEM_PROMPT customization table
#   + _build_memory_context(): documents all three memory layers
#   + _parse_plan(): robust JSON extraction with fallback
#   + Reflection feedback injection for replan loops
#   + cfg.SYSTEM_PROMPT injected into every call (domain-aware)
#
# ════════════════════════════════════════════════════════════
# WHAT PLANNER DOES (for React.js developers)
# ════════════════════════════════════════════════════════════
#
#   INPUT  (from AgentState — set by server.py before graph.invoke):
#     state["user_query"]        → the user's request string
#     state["episodic_context"]  → past similar runs
#     state["vector_context"]    → RAG: semantically relevant memory
#     state["entity_context"]    → structured entity facts
#     state["reflections"]       → feedback from prior Reflector runs
#
#   OUTPUT (partial AgentState update — merged by LangGraph):
#     state["plan"]              → list of PlanStep dicts
#     state["current_step_index"] → reset to 0
#     state["thinking_traces"]   → raw planning reasoning (JSON layer only)
#     state["execution_log"]     → node timing record
#
#   REACT.JS VISIBILITY:
#     RunResponse.plan = [
#       { step_id: "step_001", description: "Search memory...",
#         tool: "memory_search", status: "done", result: "..." },
#       { step_id: "step_002", description: "Calculate risk...",
#         tool: "calculator",   status: "done", result: "..." },
#       { step_id: "step_003", description: "Synthesize answer",
#         tool: null,           status: "done", result: "..." }
#     ]
#     // Show plan as progress timeline:
#     plan.map(step => (
#       <StepRow key={step.step_id}
#         icon={step.status === 'done' ? '✅' : '⬜'}
#         label={step.description}
#         tool={step.tool}
#       />
#     ))
#
# ════════════════════════════════════════════════════════════
# ADAPTING PLANNER TO A NEW DOMAIN
# ════════════════════════════════════════════════════════════
#
#   Option A — .env only (recommended):
#     SYSTEM_PROMPT=You are a fraud detection AI.
#     Always include a step for risk scoring (tool: fraud_risk_scorer).
#     Always conclude with a binary FRAUD/LEGIT verdict.
#
#   Option B — edit PLANNER_SYSTEM_PROMPT below:
#     Add domain-specific planning rules in the ## Instructions block.
#     E.g., for trading: "Always include a market_data step first."
#     E.g., for HR: "Always include a resume_parse step before scoring."
#
#   Option C — new plan step requirements:
#     Change MAX_PLAN_STEPS below to allow longer plans.
#     Change the example JSON in the prompt to show domain steps.
#
# ============================================================

import json
import time
import datetime
from typing import Any

from langchain_core.messages import SystemMessage, HumanMessage

from config import cfg
from state import AgentState, PlanStep
from logger import get_logger, log_llm_call
from tools import get_tool_descriptions

log = get_logger("planner")

# ── Plan size limits ──────────────────────────────────────────
MAX_PLAN_STEPS = 8   # Hard cap — prevents over-planning
MIN_PLAN_STEPS = 1   # Always at least one step


# ════════════════════════════════════════════════════════════
# PLANNER SYSTEM PROMPT
# ════════════════════════════════════════════════════════════
# Customize this for your domain OR set SYSTEM_PROMPT in .env.
# The {domain_context} block is filled from cfg.SYSTEM_PROMPT.

PLANNER_SYSTEM_PROMPT = """{domain_context}

You are the PLANNER agent in a multi-agent AI system.

## Your Role
Decompose the user's request into a precise, executable step-by-step plan.
Each step must be specific, achievable, and use the right tool.

## Available Tools
{tool_descriptions}

## Planning Rules
1. Analyze the user's request carefully before writing any steps.
2. Create 2-6 steps (rarely more). Avoid over-planning.
3. For computation: always use the calculator tool. Never compute manually.
4. For memory lookup: use memory_search to retrieve relevant past info first.
5. The LAST step should ALWAYS be a synthesis/answer step with tool=null.
6. Never hallucinate tool names — use only tools from the list above.
7. Be specific: "Calculate 15% of 2400" not "Process the numbers".

## Memory Context (use this to avoid repeating past work)
{memory_context}

## Reflection Feedback (from previous attempt — incorporate this)
{reflection_feedback}

## Output Format
Respond with ONLY a JSON array. No text before or after the JSON.

Example for "What is 15% tip on $2400?":
```json
[
  {{
    "step_id":     "step_001",
    "description": "Calculate 15% of 2400 using calculator",
    "tool":        "calculator",
    "args":        {{"expression": "2400 * 0.15"}},
    "status":      "pending",
    "result":      null
  }},
  {{
    "step_id":     "step_002",
    "description": "Synthesize the tip amount into a clear answer",
    "tool":        null,
    "args":        null,
    "status":      "pending",
    "result":      null
  }}
]
```

Rules:
- step_id format: "step_001", "step_002", ...
- tool: must be from the Available Tools list, or null
- args: must match the tool's expected input exactly, or null
- status: always "pending" in the plan
- result: always null in the plan
"""


# ════════════════════════════════════════════════════════════
# MEMORY CONTEXT BUILDER
# ════════════════════════════════════════════════════════════

def _build_memory_context(state: AgentState) -> str:
    """
    Compile all three memory layers into a single context string
    for injection into the Planner prompt.

    Memory layers:
        episodic_context → past run summaries (from memory/md/)
        vector_context   → RAG snippets (from memory/md/vector_memory.md)
        entity_context   → entity facts (from memory/md/entity_*.md)

    Returns:
        Clean, prompt-ready string (no raw JSON, no thinking traces)
    """
    parts = []

    # ── Layer 1: Episodic ────────────────────────────────
    if state.get("episodic_context"):
        lines = ["### Past Similar Runs"]
        for ep in state["episodic_context"][-3:]:
            q   = (ep.get("user_query") or "?")[:80]
            ans = (ep.get("final_answer") or "no answer")[:100]
            ok  = "✅" if ep.get("is_complete") else "❌"
            lines.append(f"- {ok} Q: {q}")
            lines.append(f"     A: {ans}")
        parts.append("\n".join(lines))

    # ── Layer 2: Vector RAG ──────────────────────────────
    if state.get("vector_context"):
        lines = ["### Relevant Memory (RAG)"]
        for i, txt in enumerate(state["vector_context"][:5], 1):
            lines.append(f"  [{i}] {txt[:150]}")
        parts.append("\n".join(lines))

    # ── Layer 3: Entity facts ────────────────────────────
    if state.get("entity_context"):
        lines = ["### Known Entities"]
        for name, data in list(state["entity_context"].items())[:5]:
            if isinstance(data, dict):
                summary = ", ".join(f"{k}={v}" for k, v in list(data.items())[:4])
            else:
                summary = str(data)[:80]
            lines.append(f"  {name}: {summary}")
        parts.append("\n".join(lines))

    return "\n\n".join(parts) if parts else "No memory context available."


def _build_reflection_feedback(state: AgentState) -> str:
    """
    Format the latest Reflector feedback for replan context.
    Only used when the Planner is called for a second time (replan loop).
    """
    reflections = state.get("reflections", [])
    if not reflections:
        return "No prior reflection feedback — this is the first attempt."

    latest = reflections[-1]
    issues      = "\n".join(f"  - {i}" for i in latest.get("issues", [])) or "  None"
    suggestions = "\n".join(f"  - {s}" for s in latest.get("suggestions", [])) or "  None"
    return (
        f"Quality Score: {latest.get('quality_score', '?'):.2f}\n"
        f"Issues found:\n{issues}\n"
        f"Suggestions:\n{suggestions}\n"
        f"Feedback: {latest.get('feedback', '')}"
    )


# ════════════════════════════════════════════════════════════
# PLAN PARSER
# ════════════════════════════════════════════════════════════

def _parse_plan(raw_response: str) -> list[PlanStep]:
    """
    Parse the LLM's response into a validated list of PlanStep dicts.

    Handles:
      - Clean JSON arrays
      - JSON wrapped in ```json ... ``` code blocks
      - Partial/malformed JSON with best-effort recovery

    Falls back to a single synthesis step on parse failure so
    the pipeline never completely breaks.

    Args:
        raw_response: Raw string from the LLM

    Returns:
        List of PlanStep TypedDicts
    """
    text = raw_response.strip()

    # Strip code fences
    for marker in ["```json", "```"]:
        if marker in text:
            text = text.split(marker, 1)[-1].split("```")[0].strip()

    # Find outermost JSON array
    start = text.find("[")
    end   = text.rfind("]")
    if start != -1 and end != -1 and end > start:
        text = text[start:end + 1]

    try:
        raw_steps = json.loads(text)
        if not isinstance(raw_steps, list):
            raise ValueError(f"Expected JSON array, got {type(raw_steps).__name__}")

        steps = []
        for i, s in enumerate(raw_steps[:MAX_PLAN_STEPS]):
            if not isinstance(s, dict):
                continue
            steps.append(PlanStep(
                step_id     = s.get("step_id", f"step_{i+1:03d}"),
                description = s.get("description", f"Step {i+1}"),
                tool        = s.get("tool") or None,
                args        = s.get("args") or None,
                status      = "pending",
                result      = None,
            ))

        if not steps:
            raise ValueError("Parsed plan has no valid steps")

        return steps

    except (json.JSONDecodeError, ValueError) as e:
        log.error(f"Plan parse failed: {e} | raw='{raw_response[:200]}'")
        return [PlanStep(
            step_id     = "step_001",
            description = "Answer the user's request directly (plan parse failed)",
            tool        = None,
            args        = None,
            status      = "pending",
            result      = None,
        )]


# ════════════════════════════════════════════════════════════
# DUAL MEMORY WRITE HELPERS
# ════════════════════════════════════════════════════════════

def _write_json_memory(
    session_id:  str,
    user_query:  str,
    plan:        list,
    raw_thinking: str,
    latency_ms:  float,
    log_id:      str,
):
    """
    Write full planning record to memory/json/ (technical warehouse).

    File: memory/json/planner_YYYY-MM-DD.jsonl
    Contains: full thinking trace, raw response, parsed plan, timing.
    Purpose: debugging, audit, analytics. NEVER shown to users directly.
    """
    date_str = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    path     = cfg.MEMORY_JSON_DIR / f"planner_{date_str}.jsonl"
    record   = {
        "timestamp":   datetime.datetime.utcnow().isoformat() + "Z",
        "log_id":      log_id,
        "session_id":  session_id,
        "user_query":  user_query,
        "plan_steps":  len(plan),
        "plan":        [dict(s) for s in plan],
        "raw_thinking": raw_thinking,   # ← JSON layer gets full thinking
        "latency_ms":  latency_ms,
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _write_md_memory(
    session_id: str,
    user_query: str,
    plan:       list,
    latency_ms: float,
):
    """
    Write clean plan summary to memory/md/ (human-readable prompting).

    File: memory/md/planner_plans.md
    Contains: clean step list — NO thinking traces, NO raw JSON.
    Purpose: prompt injection, human review, frontend display.
    """
    path = cfg.MEMORY_MD_DIR / "planner_plans.md"
    ts   = datetime.datetime.utcnow().isoformat() + "Z"

    lines = [
        f"\n## Plan | Session `{session_id}` | {ts}",
        f"**Query:** {user_query[:120]}",
        f"**Steps:** {len(plan)} | **Latency:** {latency_ms:.0f}ms",
        "",
    ]
    for step in plan:
        tool_str = f" → `{step['tool']}`" if step.get("tool") else ""
        lines.append(f"- `{step['step_id']}` {step['description']}{tool_str}")
    lines.append("")

    with open(path, "a", encoding="utf-8") as f:
        f.write("\n".join(lines))


# ════════════════════════════════════════════════════════════
# PLANNER NODE — LangGraph entry point
# ════════════════════════════════════════════════════════════

def planner_node(state: AgentState) -> dict:
    """
    LangGraph node: Planner Agent

    Reads the user query + all memory context, calls the LLM to
    produce a structured JSON plan, parses it, writes to dual
    memory (JSON + MD), and returns a partial state update.

    Called by:
        graph.py → workflow.add_node("planner", planner_node)

    Args:
        state: Current AgentState (full merged state from LangGraph)

    Returns:
        Partial AgentState dict — LangGraph merges this into shared state:
        {
          "plan":               [list of PlanStep dicts],
          "current_step_index": 0,                    ← always reset to 0
          "thinking_traces":    [new trace appended],
          "execution_log":      [new log entry appended],
        }

    ── REACT.JS: what you see in RunResponse ────────────────
        RunResponse.plan = [
          { step_id: "step_001", description: "...", tool: "calculator",
            status: "done", result: "360.0" },
          { step_id: "step_002", description: "...", tool: null,
            status: "done", result: "The answer is..." }
        ]
        // Render as timeline:
        data.plan.map(step => <PlanStep {...step} />)

    ── STREAMING (/stream): node event ──────────────────────
        { type: "node_complete", node: "planner",
          data: { plan_steps: 3, is_complete: false, step_index: 0 } }
    """
    log.info(f"🧠 Planner | query='{state['user_query'][:60]}...'")
    t_start = time.time()

    # ── Build prompts ────────────────────────────────────
    memory_ctx   = _build_memory_context(state)
    refl_fb      = _build_reflection_feedback(state)
    tool_desc    = get_tool_descriptions()

    system_prompt = PLANNER_SYSTEM_PROMPT.format(
        domain_context      = cfg.SYSTEM_PROMPT,
        tool_descriptions   = tool_desc,
        memory_context      = memory_ctx,
        reflection_feedback = refl_fb,
    )
    human_prompt = (
        f"User Request: {state['user_query']}\n"
        f"Session ID:   {state.get('session_id', 'none')}\n"
        f"Current time: {datetime.datetime.utcnow().isoformat()}Z\n\n"
        "Generate a JSON plan to fulfill this request."
    )

    # ── LLM call ────────────────────────────────────────
    llm      = cfg.get_llm("planner")
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=human_prompt),
    ]

    try:
        response   = llm.invoke(messages)
        raw_text   = response.content
        latency_ms = (time.time() - t_start) * 1000

        plan = _parse_plan(raw_text)

        # ── Log LLM call (ai-req-res-logging/) ──────────
        log_id = log_llm_call(
            agent         = "planner",
            prompt        = [
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": human_prompt},
            ],
            response      = raw_text,
            parsed_output = [dict(s) for s in plan],
            session_id    = state.get("session_id"),
            provider      = cfg.PROVIDER,
            model         = (cfg.OLLAMA_MODELS.get("planner")
                             if cfg.PROVIDER == "ollama"
                             else cfg.GROQ_MODELS.get("planner")),
            latency_ms    = latency_ms,
            thinking      = raw_text,   # raw = thinking for planner
        )

        # ── Dual memory write ────────────────────────────
        sid = state.get("session_id") or "no_session"
        _write_json_memory(sid, state["user_query"], plan, raw_text, latency_ms, log_id)
        _write_md_memory(sid, state["user_query"], plan, latency_ms)

        log.info(
            f"✅ Planner | {len(plan)} steps | {latency_ms:.0f}ms | log_id={log_id}"
        )

        return {
            "plan":               plan,
            "current_step_index": 0,
            "thinking_traces": [{
                "agent":      "planner",
                "timestamp":  datetime.datetime.utcnow().isoformat() + "Z",
                "thinking":   raw_text,   # full thinking → JSON layer only
                "log_id":     log_id,
                "step_count": len(plan),
            }],
            "execution_log": [{
                "node":       "planner",
                "timestamp":  datetime.datetime.utcnow().isoformat() + "Z",
                "status":     "success",
                "latency_ms": latency_ms,
                "details":    {"plan_steps": len(plan)},
            }],
        }

    except Exception as e:
        latency_ms = (time.time() - t_start) * 1000
        err_msg    = f"Planner LLM error: {type(e).__name__}: {e}"
        log.error(err_msg, exc_info=True)

        fallback_plan = [PlanStep(
            step_id     = "step_001",
            description = f"Answer the request directly (planner failed: {e})",
            tool        = None,
            args        = None,
            status      = "pending",
            result      = None,
        )]
        return {
            "plan":               fallback_plan,
            "current_step_index": 0,
            "errors":             [err_msg],
            "execution_log": [{
                "node":       "planner",
                "timestamp":  datetime.datetime.utcnow().isoformat() + "Z",
                "status":     "error",
                "error":      err_msg,
                "latency_ms": latency_ms,
            }],
        }
