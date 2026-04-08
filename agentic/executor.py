# ============================================================
# executor.py — Executor Agent Node
# ============================================================
# IMPROVED IN THIS VERSION:
#   + Dual memory writes on every step:
#       JSON: memory/json/executor_YYYY-MM-DD.jsonl (full + tool output)
#       MD:   memory/md/executor_steps.md (clean step outcomes)
#   + React.js developer guide: what each step emits
#   + ToolDispatcher: documented per-tool dispatch + error handling
#   + Final synthesis step clearly separated from analysis steps
#   + Working memory update documented (what keys get set per step)
#   + Safety: hard limits on tool output truncation for prompt safety
#   + Universal template: how to add domain tools to executor flow
#
# ════════════════════════════════════════════════════════════
# WHAT EXECUTOR DOES (for React.js developers)
# ════════════════════════════════════════════════════════════
#
#   INPUT (from AgentState):
#     state["plan"]               → the Planner's step list
#     state["current_step_index"] → which step to execute NOW
#     state["working_memory"]     → accumulated inter-step data
#     state["intermediate_results"] → previous step outputs
#
#   OUTPUT (partial AgentState — ONE step per invocation):
#     state["plan"]               → same list, step.status updated
#     state["current_step_index"] → incremented by 1
#     state["tool_calls"]         → new ToolCall appended
#     state["intermediate_results"] → new step result appended
#     state["working_memory"]     → updated with step output
#     state["final_answer"]       → set ONLY on last step
#     state["is_complete"]        → True ONLY on last step
#
#   REACT.JS VISIBILITY:
#     RunResponse.tool_calls = [
#       { tool_name: "calculator",
#         tool_input: { expression: "2400*0.15" },
#         tool_output: "360.0",
#         success: true,
#         error: null,
#         timestamp: "..." }
#     ]
#     // Show tool call history:
#     data.tool_calls.map(tc => (
#       <ToolBadge key={tc.timestamp}
#         name={tc.tool_name}
#         success={tc.success}
#         output={tc.tool_output}
#       />
#     ))
#
#   STREAMING (/stream) — node events during execution:
#     { type: "node_complete", node: "executor",
#       data: { step_index: 2, plan_steps: 3, is_complete: false } }
#     { type: "node_complete", node: "executor",
#       data: { step_index: 3, plan_steps: 3, is_complete: true } }
#
# ════════════════════════════════════════════════════════════
# ADAPTING EXECUTOR TO A NEW DOMAIN
# ════════════════════════════════════════════════════════════
#
#   The Executor is domain-agnostic. To add domain behavior:
#
#   1. Add domain skills to /skills/:
#        skills/fraud_risk_scorer.py
#      → The Planner will call: skill_call("fraud_risk_scorer", {...})
#      → The Executor's ToolDispatcher routes it automatically.
#
#   2. Inject domain metadata via /run metadata field:
#        { "query": "...", "metadata": { "amount": 9800 } }
#      → Available in wm.get("amount") inside the Executor.
#
#   3. For domain-specific synthesis (final step), customize
#      SYNTHESIS_PROMPT by adding domain output requirements:
#        "Always include a RISK_SCORE: X.XX in your answer."
#
# ============================================================

import json
import time
import datetime
from typing import Any, Optional

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.tools import BaseTool

from config import cfg
from state import AgentState, PlanStep, ToolCall
from tools import get_all_tools, get_tool_descriptions
from logger import get_logger, log_llm_call
from memory.working_memory import WorkingMemory

log = get_logger("executor")


# ════════════════════════════════════════════════════════════
# EXECUTOR PROMPTS
# ════════════════════════════════════════════════════════════

STEP_ANALYSIS_PROMPT = """{domain_context}

You are the EXECUTOR agent analyzing the result of one plan step.

## Current Plan
{plan_summary}

## Current Step
Step ID:     {step_id}
Description: {step_description}
Tool Used:   {step_tool}
Tool Args:   {step_args}

## Tool Result
{tool_result}

## Working Memory (accumulated context)
{working_memory}

## Previous Step Results
{intermediate_results}

## Instructions
- Analyze the tool result above.
- Extract the key information needed for the next steps.
- Be concise and factual. Do not hallucinate tool output.
- If the tool failed, note what went wrong and suggest a workaround.
"""

SYNTHESIS_PROMPT = """{domain_context}

You are the EXECUTOR agent writing the final answer to the user's request.

## User's Original Request
{user_query}

## All Step Results
{all_results}

## Working Memory (all accumulated data)
{working_memory}

## Instructions
- Write a comprehensive, well-structured final answer to the user.
- Base your answer ENTIRELY on the step results above.
- Be accurate, clear, and directly address the user's question.
- Do NOT add information not present in the step results.
- If domain-specific output format is required, follow it exactly.
"""


# ════════════════════════════════════════════════════════════
# TOOL DISPATCHER
# ════════════════════════════════════════════════════════════

class ToolDispatcher:
    """
    Routes tool calls from the plan to actual tool implementations.

    Builds a name→tool dict from get_all_tools() at init time.
    Handles both LangChain @tool functions and dynamic skill proxies.

    ── HOW TOOLS ARE CALLED ─────────────────────────────────

    Single-arg tools (most LangChain tools):
        tool.invoke(value_string)
        e.g., calculator.invoke("2400 * 0.15")

    Multi-arg tools:
        tool.invoke({"arg1": v1, "arg2": v2})
        e.g., memory_search.invoke({"query": "...", "top_k": 3})

    Skill proxy (skill_call tool):
        skill_call.invoke({"skill_name": "fraud_risk_scorer",
                           "input_json": '{"amount": 9800}'})

    ── ADDING NEW TOOLS ─────────────────────────────────────
        Option A: Add to tools.py with @tool decorator (built-in)
        Option B: Drop .py file in /skills/ (auto-discovered)
        Both are available via skill_call("skill_name", '{...}')

    ── REACT.JS VISIBILITY ──────────────────────────────────
        Each dispatch creates a ToolCallRecord in RunResponse.tool_calls:
        { tool_name, tool_input, tool_output, success, error, timestamp }
    """

    def __init__(self):
        self._tools: dict[str, BaseTool] = {
            t.name: t for t in get_all_tools()
        }
        log.debug(f"ToolDispatcher: {list(self._tools.keys())}")

    def call(self, tool_name: str, args: Optional[dict]) -> ToolCall:
        """
        Invoke a tool and return a ToolCall record.

        Args:
            tool_name: Exact name of the tool (from get_all_tools())
            args:      Dict of arguments, or None for no-arg tools

        Returns:
            ToolCall dict:
            {
              tool_name, tool_input, tool_output,
              success, error, timestamp
            }

        Error cases:
            Tool not found → success=False, error="Tool 'x' not found..."
            Tool exception → success=False, error="<ExceptionType>: msg"
        """
        ts = datetime.datetime.utcnow().isoformat() + "Z"

        if tool_name not in self._tools:
            msg = (
                f"Tool '{tool_name}' not found. "
                f"Available: {list(self._tools.keys())}"
            )
            log.warning(msg)
            return ToolCall(
                tool_name   = tool_name,
                tool_input  = args or {},
                tool_output = None,
                success     = False,
                error       = msg,
                timestamp   = ts,
            )

        tool   = self._tools[tool_name]
        input_ = args or {}

        try:
            t0 = time.time()
            # Single-value tools: unwrap the single arg
            if len(input_) == 1:
                output = tool.invoke(list(input_.values())[0])
            else:
                output = tool.invoke(input_)
            latency = (time.time() - t0) * 1000
            log.info(f"🔧 Tool '{tool_name}' OK | {latency:.0f}ms")
            return ToolCall(
                tool_name   = tool_name,
                tool_input  = input_,
                tool_output = output,
                success     = True,
                error       = None,
                timestamp   = ts,
            )
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
            log.error(f"Tool '{tool_name}' failed: {err}")
            return ToolCall(
                tool_name   = tool_name,
                tool_input  = input_,
                tool_output = None,
                success     = False,
                error       = err,
                timestamp   = ts,
            )


# ════════════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════════════

def _format_plan_summary(plan: list[PlanStep], current_idx: int) -> str:
    """Format the plan as a readable list for the prompt."""
    lines = []
    for i, step in enumerate(plan):
        marker = "→ " if i == current_idx else "  "
        emoji  = {"pending": "⬜", "running": "🔄", "done": "✅",
                  "failed": "❌"}.get(step.get("status", "pending"), "⬜")
        lines.append(f"{marker}{emoji} [{step['step_id']}] {step['description']}")
    return "\n".join(lines)


def _format_intermediate_results(results: list[dict]) -> str:
    """Format previous step results for prompt injection (last 5 only)."""
    if not results:
        return "No results yet."
    lines = []
    for r in results[-5:]:
        step_id = r.get("step_id", "?")
        result  = str(r.get("result", ""))[:300]
        lines.append(f"[{step_id}] {result}")
    return "\n".join(lines)


def _mark_step(plan: list[PlanStep], idx: int, status: str, result: Any) -> list[PlanStep]:
    """Return new plan with step[idx] status+result updated (immutable pattern)."""
    updated = [dict(s) for s in plan]
    if 0 <= idx < len(updated):
        updated[idx]["status"] = status
        updated[idx]["result"] = result
    return updated


# ════════════════════════════════════════════════════════════
# DUAL MEMORY WRITE HELPERS
# ════════════════════════════════════════════════════════════

def _write_json_memory(
    session_id:  str,
    step:        dict,
    tool_call:   Optional[ToolCall],
    analysis:    str,
    latency_ms:  float,
    is_final:    bool,
):
    """
    Write full step record to memory/json/ (technical warehouse).

    File: memory/json/executor_YYYY-MM-DD.jsonl
    Contains: tool input/output (full), analysis text, timing.
    Purpose: debugging, replay, audit. Full detail, no truncation.
    """
    date_str = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    path     = cfg.MEMORY_JSON_DIR / f"executor_{date_str}.jsonl"
    record   = {
        "timestamp":  datetime.datetime.utcnow().isoformat() + "Z",
        "session_id": session_id,
        "step_id":    step.get("step_id"),
        "description":step.get("description"),
        "tool":       step.get("tool"),
        "tool_input": step.get("args"),
        "tool_output":str(tool_call.get("tool_output", ""))[:2000] if tool_call else None,
        "tool_success":tool_call.get("success") if tool_call else None,
        "tool_error": tool_call.get("error") if tool_call else None,
        "analysis":   analysis,    # full analysis including raw LLM text
        "latency_ms": latency_ms,
        "is_final":   is_final,
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _write_md_memory(
    session_id: str,
    step:       dict,
    tool_call:  Optional[ToolCall],
    analysis:   str,
    is_final:   bool,
):
    """
    Write clean step outcome to memory/md/ (human-readable).

    File: memory/md/executor_steps.md
    Contains: step description, tool used, key outcome.
    NO raw tool output dumps. NO thinking traces. Human-readable.
    """
    path   = cfg.MEMORY_MD_DIR / "executor_steps.md"
    ts     = datetime.datetime.utcnow().isoformat() + "Z"
    status = "🏁 FINAL" if is_final else "📋 STEP"
    tool_str = f" (tool: `{step.get('tool')}`)" if step.get("tool") else ""
    tc_str = ""
    if tool_call:
        ok     = "✅" if tool_call.get("success") else "❌"
        output = str(tool_call.get("tool_output", ""))[:150]
        tc_str = f"\n  {ok} Tool output: {output}"

    lines = [
        f"\n### {status} `{step.get('step_id')}` | Session `{session_id}` | {ts}",
        f"**{step.get('description')}**{tool_str}{tc_str}",
        f"**Analysis:** {analysis[:200]}",
        "",
    ]
    with open(path, "a", encoding="utf-8") as f:
        f.write("\n".join(lines))


# ════════════════════════════════════════════════════════════
# LLM CALL HELPERS
# ════════════════════════════════════════════════════════════

def _run_step_analysis(
    state:       AgentState,
    step:        PlanStep,
    tool_result: str,
    wm:          WorkingMemory,
) -> str:
    """Call LLM to analyze one tool result and extract key information."""
    llm    = cfg.get_llm("executor")
    t_start = time.time()

    prompt = STEP_ANALYSIS_PROMPT.format(
        domain_context       = cfg.SYSTEM_PROMPT,
        plan_summary         = _format_plan_summary(
                                   state["plan"], state["current_step_index"]),
        step_id              = step["step_id"],
        step_description     = step["description"],
        step_tool            = step.get("tool") or "none",
        step_args            = json.dumps(step.get("args") or {}),
        working_memory       = wm.format_for_prompt(),
        intermediate_results = _format_intermediate_results(
                                   state.get("intermediate_results", [])),
        tool_result          = tool_result,
    )

    try:
        response   = llm.invoke(prompt)
        latency_ms = (time.time() - t_start) * 1000
        log_llm_call(
            agent      = "executor",
            prompt     = prompt,
            response   = response.content,
            session_id = state.get("session_id"),
            provider   = cfg.PROVIDER,
            latency_ms = latency_ms,
            metadata   = {"step_id": step["step_id"], "mode": "analysis"},
        )
        return response.content
    except Exception as e:
        log.error(f"Step analysis LLM failed: {e}")
        return f"[Analysis failed: {e}]\nTool result was: {tool_result[:300]}"


def _run_synthesis(state: AgentState, wm: WorkingMemory) -> str:
    """Call LLM to synthesize all step results into the final answer."""
    llm    = cfg.get_llm("executor")
    t_start = time.time()

    all_results = _format_intermediate_results(
        state.get("intermediate_results", [])
    )
    prompt = SYNTHESIS_PROMPT.format(
        domain_context = cfg.SYSTEM_PROMPT,
        user_query     = state.get("user_query", ""),
        all_results    = all_results,
        working_memory = wm.format_for_prompt(),
    )

    try:
        response   = llm.invoke(prompt)
        latency_ms = (time.time() - t_start) * 1000
        log_llm_call(
            agent      = "executor",
            prompt     = prompt,
            response   = response.content,
            session_id = state.get("session_id"),
            provider   = cfg.PROVIDER,
            latency_ms = latency_ms,
            metadata   = {"mode": "final_synthesis"},
        )
        return response.content
    except Exception as e:
        log.error(f"Synthesis LLM failed: {e}")
        return f"I encountered an error synthesizing the final answer: {e}"


# ════════════════════════════════════════════════════════════
# DISPATCHER SINGLETON
# ════════════════════════════════════════════════════════════
_dispatcher: Optional[ToolDispatcher] = None

def _get_dispatcher() -> ToolDispatcher:
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = ToolDispatcher()
    return _dispatcher


# ════════════════════════════════════════════════════════════
# EXECUTOR NODE — LangGraph entry point
# ════════════════════════════════════════════════════════════

def executor_node(state: AgentState) -> dict:
    """
    LangGraph node: Executor Agent

    Executes ONE plan step per invocation. LangGraph loops this
    node (via conditional edge) until is_complete=True.

    Called by:
        graph.py → workflow.add_node("executor", executor_node)

    Args:
        state: Current AgentState

    Returns:
        Partial AgentState update — merged by LangGraph:
        {
          "plan":                 [updated plan with step statuses],
          "current_step_index":  idx + 1,
          "tool_calls":          [new ToolCall appended],
          "intermediate_results":[new step result appended],
          "working_memory":      {updated scratch space},
          "is_complete":         True only on last step,
          "final_answer":        str only on last step,
          "execution_log":       [new entry appended],
        }

    ── REACT.JS: RunResponse fields populated ────────────────
        .tool_calls    → all tool invocations with inputs/outputs
        .plan          → plan with step statuses (pending/done/failed)
        .final_answer  → the synthesized answer (last step only)

    ── STREAMING: SSE events ─────────────────────────────────
        Each invocation emits:
        { type: "node_complete", node: "executor",
          data: { step_index: N, plan_steps: M, is_complete: bool } }
    """
    plan = state.get("plan", [])
    idx  = state.get("current_step_index", 0)

    # Guard: plan already complete
    if not plan or idx >= len(plan):
        log.info("Executor: no more steps → running final synthesis")
        wm     = WorkingMemory(state.get("working_memory", {}))
        answer = _run_synthesis(state, wm)
        return {
            "final_answer": answer,
            "is_complete":  True,
            "messages": [{"role": "assistant", "content": answer,
                          "name": None, "tool_call_id": None}],
            "execution_log": [{
                "node":      "executor",
                "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
                "status":    "forced_synthesis",
            }],
        }

    step       = plan[idx]
    is_last    = (idx == len(plan) - 1)
    sid        = state.get("session_id") or "no_session"
    wm         = WorkingMemory(state.get("working_memory", {}))
    dispatcher = _get_dispatcher()
    t_start    = time.time()

    log.info(
        f"⚡ Executor | step {idx+1}/{len(plan)} "
        f"[{step['step_id']}] {step['description'][:50]}"
    )

    # ── Execute tool ─────────────────────────────────────
    tool_call_record: Optional[ToolCall] = None
    tool_result_str = "No tool used for this step."

    if step.get("tool"):
        tool_call_record = dispatcher.call(step["tool"], step.get("args"))
        if tool_call_record["success"]:
            output = tool_call_record["tool_output"]
            tool_result_str = str(output)[:1500]
            wm.set(f"{step['step_id']}_output", output)
        else:
            tool_result_str = f"Tool error: {tool_call_record['error']}"
            wm.set(f"{step['step_id']}_error", tool_call_record["error"])

    # ── LLM: analysis or final synthesis ─────────────────
    if is_last:
        llm_text    = _run_synthesis(state, wm)
        final_ans   = llm_text
        is_complete = True
    else:
        llm_text    = _run_step_analysis(state, step, tool_result_str, wm)
        wm.set(f"{step['step_id']}_analysis", llm_text)
        final_ans   = None
        is_complete = False

    latency_ms  = (time.time() - t_start) * 1000
    step_status = (
        "done" if (not tool_call_record or tool_call_record["success"])
        else "failed"
    )

    # ── Update plan ──────────────────────────────────────
    updated_plan = _mark_step(plan, idx, step_status, llm_text[:500])

    # ── Dual memory write ────────────────────────────────
    _write_json_memory(sid, dict(step), tool_call_record,
                       llm_text, latency_ms, is_last)
    _write_md_memory(sid, dict(step), tool_call_record, llm_text, is_last)

    # ── Build state update ───────────────────────────────
    step_result = {
        "step_id":     step["step_id"],
        "description": step["description"],
        "tool":        step.get("tool"),
        "tool_success":tool_call_record["success"] if tool_call_record else None,
        "result":      llm_text[:800],
        "timestamp":   datetime.datetime.utcnow().isoformat() + "Z",
    }

    log.info(
        f"✅ Step {idx+1} | status={step_status} | {latency_ms:.0f}ms | "
        f"{'FINAL' if is_last else 'continuing'}"
    )

    update: dict = {
        "plan":                updated_plan,
        "current_step_index":  idx + 1,
        "intermediate_results":[step_result],
        "working_memory":      wm.to_state_dict(),
        "is_complete":         is_complete,
        "execution_log": [{
            "node":       "executor",
            "step_id":    step["step_id"],
            "timestamp":  datetime.datetime.utcnow().isoformat() + "Z",
            "status":     step_status,
            "latency_ms": latency_ms,
            "is_final":   is_last,
        }],
    }

    if tool_call_record:
        update["tool_calls"] = [tool_call_record]

    if final_ans:
        update["final_answer"] = final_ans
        update["messages"] = [{
            "role": "assistant", "content": final_ans,
            "name": None, "tool_call_id": None,
        }]

    return update
