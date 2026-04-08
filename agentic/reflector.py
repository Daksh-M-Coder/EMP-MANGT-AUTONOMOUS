# ============================================================
# reflector.py — Reflector Agent Node
# ============================================================
# IMPROVED IN THIS VERSION:
#   + Dual memory writes on every reflection:
#       JSON: memory/json/reflector_YYYY-MM-DD.jsonl (full + raw scores)
#       MD:   memory/md/reflector_scores.md (clean scorecards)
#   + React.js developer guide: ReflectionRecord in RunResponse
#   + Quality scorecard with 5 dimensions documented
#   + Force-approve path fully documented (max loops safety valve)
#   + Universal template: domain-specific evaluation criteria guide
#   + _parse_reflection(): robust with fallback to auto-approve
#   + cfg.SYSTEM_PROMPT injected for domain-aware evaluation
#
# ════════════════════════════════════════════════════════════
# WHAT REFLECTOR DOES (for React.js developers)
# ════════════════════════════════════════════════════════════
#
#   INPUT (from AgentState):
#     state["user_query"]      → original request to evaluate against
#     state["final_answer"]    → the Executor's proposed answer
#     state["plan"]            → the plan that was executed
#     state["tool_calls"]      → all tool invocations
#     state["reflection_count"]→ how many times we've reflected
#     state["errors"]          → any errors during execution
#
#   OUTPUT (partial AgentState):
#     state["reflections"]     → new ReflectionResult appended
#     state["reflection_count"]→ incremented by 1
#     state["is_complete"]     → True if approved
#     state["execution_log"]   → new entry appended
#
#   REACT.JS VISIBILITY — RunResponse.reflections:
#     [
#       {
#         quality_score:    0.92,          // 0.0-1.0
#         issues:           [],            // problems found
#         suggestions:      ["Add units"], // improvements
#         approved:         true,          // route to END
#         needs_replanning: false,         // route to Planner
#         feedback:         "Correct and well-structured."
#       }
#     ]
#
#   // Render quality badge:
#   const score = data.reflections[0]?.quality_score ?? 0;
#   <QualityBadge
#     score={score}
#     color={score >= 0.8 ? 'green' : score >= 0.6 ? 'yellow' : 'red'}
#     label={`${(score * 100).toFixed(0)}%`}
#   />
#   // Show issues:
#   data.reflections.flatMap(r => r.issues).map(issue => (
#     <Issue key={issue} text={issue} />
#   ))
#
# ════════════════════════════════════════════════════════════
# ADAPTING REFLECTOR TO A NEW DOMAIN
# ════════════════════════════════════════════════════════════
#
#   Option A — .env system prompt:
#     SYSTEM_PROMPT=You are a fraud AI. Approve only if risk_score is present.
#     → Reflector will check for risk_score in its domain-aware evaluation.
#
#   Option B — add custom evaluation criteria below:
#     In REFLECTOR_SYSTEM_PROMPT, add to "## Evaluation Criteria":
#       "6. **Domain Compliance**: Does the answer include a risk_score 0.0-1.0?"
#
#   Option C — lower the approval threshold:
#     APPROVAL_THRESHOLD = 0.60  (below, change it here)
#     For strict domains like medical/legal, raise it to 0.85.
#
# ════════════════════════════════════════════════════════════
# ROUTING DECISIONS (emitted in execution_log)
# ════════════════════════════════════════════════════════════
#
#   approved=True           → graph routes to END ✅
#   needs_replanning=True   → graph routes to PLANNER 🔄
#   approved=False, no repl → graph routes to EXECUTOR ↩️ (retry)
#   max loops reached       → force-approve → END (safety)
#
# ============================================================

import json
import time
import datetime
from typing import Any

from langchain_core.messages import SystemMessage, HumanMessage

from config import cfg
from state import AgentState, ReflectionResult
from logger import get_logger, log_llm_call

log = get_logger("reflector")

# ── Quality threshold — answers below this are NOT approved ──
APPROVAL_THRESHOLD = 0.70   # Change for your domain (0.60 lenient, 0.85 strict)


# ════════════════════════════════════════════════════════════
# REFLECTOR SYSTEM PROMPT
# ════════════════════════════════════════════════════════════

REFLECTOR_SYSTEM_PROMPT = """{domain_context}

You are the REFLECTOR agent — an impartial quality evaluator for AI responses.

## User's Original Request
{user_query}

## Agent's Proposed Final Answer
{final_answer}

## Execution Plan That Was Followed
{plan_summary}

## Tools Called
{tools_summary}

## Errors During Execution
{errors_summary}

## Reflection Loop Info
This is reflection #{reflection_count} of maximum {max_reflections}.
{"⚠️ LAST REFLECTION — set approved=true regardless of quality." if forced else ""}

## Evaluation Criteria (score each 0.0-1.0)
1. **Completeness**: Does the answer fully address the user's request?
2. **Accuracy**:     Are all facts, calculations, and statements correct?
3. **Clarity**:      Is the response well-structured and easy to understand?
4. **Tool Usage**:   Were the right tools called with the right arguments?
5. **Honesty**:      Does it avoid hallucinating unverified information?

## Scoring Rules
- quality_score = weighted average of the 5 dimensions above
- approved = true if quality_score >= {threshold} AND no critical issues
- needs_replanning = true ONLY if the approach was fundamentally wrong
  (wrong tools, misunderstood the task, completely off-track)
- If reflection #{reflection_count} = {max_reflections}: approved=true always

## Output Format
Respond with ONLY a JSON object. No text outside the JSON.

```json
{{
  "quality_score": 0.92,
  "issues": [],
  "suggestions": ["Could include units in the answer"],
  "approved": true,
  "needs_replanning": false,
  "feedback": "The calculation is correct and the answer is clear.",
  "dimension_scores": {{
    "completeness": 0.95,
    "accuracy":     0.90,
    "clarity":      0.90,
    "tool_usage":   0.95,
    "honesty":      0.90
  }}
}}
```
"""


# ════════════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════════════

def _format_plan_summary(plan: list) -> str:
    if not plan:
        return "No plan was generated."
    lines = []
    for step in plan:
        emoji = {"done": "✅", "failed": "❌", "pending": "⬜"}.get(
            step.get("status", "?"), "?"
        )
        lines.append(f"  {emoji} [{step.get('step_id','?')}] {step.get('description','?')}")
    return "\n".join(lines)


def _format_tools_summary(tool_calls: list) -> str:
    if not tool_calls:
        return "No tools were called."
    lines = []
    for tc in tool_calls:
        ok     = "✅" if tc.get("success") else "❌"
        output = str(tc.get("tool_output", ""))[:100]
        lines.append(f"  {ok} {tc.get('tool_name','?')} → {output}")
    return "\n".join(lines)


# ════════════════════════════════════════════════════════════
# REFLECTION PARSER
# ════════════════════════════════════════════════════════════

def _parse_reflection(
    raw_response:   str,
    forced_approve: bool = False,
) -> ReflectionResult:
    """
    Parse the LLM's JSON reflection into a ReflectionResult dict.

    Safety behaviors:
        - Strips ```json code fences before parsing
        - Falls back to auto-approve on parse failure (prevent stuck graph)
        - Respects forced_approve=True when max loops reached
        - Caps quality_score to [0.0, 1.0]

    Args:
        raw_response:   Raw LLM response string
        forced_approve: If True, override to approved=True

    Returns:
        ReflectionResult TypedDict
    """
    text = raw_response.strip()

    for marker in ["```json", "```"]:
        if marker in text:
            text = text.split(marker, 1)[-1].split("```")[0].strip()

    start = text.find("{")
    end   = text.rfind("}")
    if start != -1 and end != -1:
        text = text[start:end + 1]

    try:
        data  = json.loads(text)
        score = max(0.0, min(1.0, float(data.get("quality_score", 0.5))))
        return ReflectionResult(
            quality_score    = score,
            issues           = data.get("issues", []),
            suggestions      = data.get("suggestions", []),
            approved         = bool(data.get("approved", False)) or forced_approve,
            needs_replanning = bool(data.get("needs_replanning", False)) and not forced_approve,
            feedback         = str(data.get("feedback", "")),
        )
    except (json.JSONDecodeError, ValueError, TypeError) as e:
        log.error(f"Reflection parse failed: {e}\nRaw: {raw_response[:200]}")
        return ReflectionResult(
            quality_score    = 0.6,
            issues           = [f"Reflection parse error: {e}"],
            suggestions      = [],
            approved         = True,   # auto-approve to unblock graph
            needs_replanning = False,
            feedback         = "Reflection could not be parsed — auto-approved.",
        )


# ════════════════════════════════════════════════════════════
# DUAL MEMORY WRITE HELPERS
# ════════════════════════════════════════════════════════════

def _write_json_memory(
    session_id:   str,
    user_query:   str,
    reflection:   ReflectionResult,
    raw_thinking: str,
    latency_ms:   float,
    log_id:       str,
    loop_num:     int,
):
    """
    Write full reflection record to memory/json/ (technical warehouse).

    File: memory/json/reflector_YYYY-MM-DD.jsonl
    Contains: full raw response (thinking), all dimension scores, timing.
    Purpose: analytics, tuning, debugging. Full detail.
    """
    date_str = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    path     = cfg.MEMORY_JSON_DIR / f"reflector_{date_str}.jsonl"
    record   = {
        "timestamp":    datetime.datetime.utcnow().isoformat() + "Z",
        "log_id":       log_id,
        "session_id":   session_id,
        "user_query":   user_query,
        "loop":         loop_num,
        "quality_score":reflection["quality_score"],
        "approved":     reflection["approved"],
        "needs_replanning": reflection["needs_replanning"],
        "issues":       reflection["issues"],
        "suggestions":  reflection["suggestions"],
        "feedback":     reflection["feedback"],
        "raw_thinking": raw_thinking,   # full raw response → JSON layer only
        "latency_ms":   latency_ms,
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _write_md_memory(
    session_id:  str,
    user_query:  str,
    reflection:  ReflectionResult,
    loop_num:    int,
):
    """
    Write clean quality scorecard to memory/md/ (human-readable).

    File: memory/md/reflector_scores.md
    Contains: score badge, decision, issues, feedback.
    NO raw thinking, NO JSON blobs. Human-readable only.
    """
    path    = cfg.MEMORY_MD_DIR / "reflector_scores.md"
    ts      = datetime.datetime.utcnow().isoformat() + "Z"
    score   = reflection["quality_score"]
    badge   = "🟢" if score >= 0.8 else ("🟡" if score >= 0.6 else "🔴")
    decision = "✅ APPROVED" if reflection["approved"] else (
               "🔄 REPLAN"  if reflection["needs_replanning"] else "↩️ RETRY")
    issues_str = "\n".join(f"  - {i}" for i in reflection["issues"]) or "  None"

    lines = [
        f"\n## {badge} Reflection #{loop_num} | Session `{session_id}` | {ts}",
        f"**Query:** {user_query[:100]}",
        f"**Score:** {score:.2f} ({score*100:.0f}%)  |  **Decision:** {decision}",
        f"**Feedback:** {reflection['feedback']}",
        f"**Issues:**\n{issues_str}",
        "",
    ]
    with open(path, "a", encoding="utf-8") as f:
        f.write("\n".join(lines))


# ════════════════════════════════════════════════════════════
# REFLECTOR NODE — LangGraph entry point
# ════════════════════════════════════════════════════════════

def reflector_node(state: AgentState) -> dict:
    """
    LangGraph node: Reflector Agent

    Evaluates the Executor's final_answer against the user_query
    and returns a quality assessment. The graph uses this to decide:
      - END (approved=True)
      - Back to Planner (needs_replanning=True)
      - Back to Executor (retry)

    Called by:
        graph.py → workflow.add_node("reflector", reflector_node)

    Args:
        state: Current AgentState

    Returns:
        Partial AgentState update:
        {
          "reflections":      [new ReflectionResult appended],
          "reflection_count": current + 1,
          "is_complete":      True if approved,
          "thinking_traces":  [raw reasoning appended],
          "execution_log":    [new entry appended],
        }

    ── REACT.JS: RunResponse.reflections ────────────────────
        data.reflections.map((r, i) => (
          <ReflectionCard key={i}
            score={r.quality_score}
            approved={r.approved}
            issues={r.issues}
            feedback={r.feedback}
          />
        ))

    ── STREAMING: SSE event ─────────────────────────────────
        { type: "node_complete", node: "reflector",
          data: { is_complete: true } }    // when approved
    """
    reflection_count = state.get("reflection_count", 0)
    max_reflections  = cfg.MAX_REFLECTION_LOOPS
    forced_approve   = (reflection_count >= max_reflections - 1)
    sid              = state.get("session_id") or "no_session"

    log.info(
        f"🪞 Reflector | loop {reflection_count+1}/{max_reflections} | "
        f"forced={forced_approve}"
    )

    # ── Force-approve shortcut ───────────────────────────
    if forced_approve:
        log.warning(
            f"⚠️  Max reflections ({max_reflections}) reached — force-approving"
        )
        forced_result = ReflectionResult(
            quality_score    = 0.7,
            issues           = ["Max reflection loops reached — auto-approved"],
            suggestions      = [],
            approved         = True,
            needs_replanning = False,
            feedback         = f"Auto-approved after {max_reflections} reflection loops.",
        )
        _write_md_memory(sid, state.get("user_query","?"),
                         forced_result, reflection_count + 1)
        return {
            "reflections":      [forced_result],
            "reflection_count": reflection_count + 1,
            "is_complete":      True,
            "execution_log": [{
                "node":      "reflector",
                "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
                "status":    "force_approved",
                "loop":      reflection_count + 1,
            }],
        }

    # ── Build prompt ─────────────────────────────────────
    final_answer = state.get("final_answer") or "[No answer generated]"
    system_prompt = REFLECTOR_SYSTEM_PROMPT.format(
        domain_context   = cfg.SYSTEM_PROMPT,
        user_query       = state.get("user_query", ""),
        final_answer     = final_answer[:2000],
        plan_summary     = _format_plan_summary(state.get("plan", [])),
        tools_summary    = _format_tools_summary(state.get("tool_calls", [])),
        errors_summary   = "; ".join(state.get("errors", [])) or "None",
        reflection_count = reflection_count + 1,
        max_reflections  = max_reflections,
        forced           = forced_approve,
        threshold        = APPROVAL_THRESHOLD,
    )

    # ── LLM call ─────────────────────────────────────────
    llm     = cfg.get_llm("reflector")
    t_start = time.time()

    try:
        response   = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content="Evaluate and return your JSON assessment."),
        ])
        raw_text   = response.content
        latency_ms = (time.time() - t_start) * 1000

        reflection = _parse_reflection(raw_text, forced_approve=forced_approve)

        # ── Log LLM call ─────────────────────────────────
        log_id = log_llm_call(
            agent         = "reflector",
            prompt        = [
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": "Evaluate the agent response."},
            ],
            response      = raw_text,
            parsed_output = dict(reflection),
            session_id    = sid,
            provider      = cfg.PROVIDER,
            model         = (cfg.OLLAMA_MODELS.get("reflector")
                             if cfg.PROVIDER == "ollama"
                             else cfg.GROQ_MODELS.get("reflector")),
            latency_ms    = latency_ms,
            thinking      = raw_text,
        )

        # ── Dual memory write ─────────────────────────────
        _write_json_memory(
            sid, state.get("user_query","?"), reflection,
            raw_text, latency_ms, log_id, reflection_count + 1
        )
        _write_md_memory(sid, state.get("user_query","?"),
                         reflection, reflection_count + 1)

        decision = (
            "APPROVED ✅"      if reflection["approved"] else
            "NEEDS REPLAN 🔄"  if reflection["needs_replanning"] else
            "RETRY ↩️"
        )
        log.info(
            f"🪞 Reflection #{reflection_count+1}: "
            f"score={reflection['quality_score']:.2f} | "
            f"{decision} | {latency_ms:.0f}ms"
        )
        if reflection["issues"]:
            log.info(f"   Issues: {'; '.join(reflection['issues'][:3])}")

        return {
            "reflections":      [reflection],
            "reflection_count": reflection_count + 1,
            "is_complete":      reflection["approved"],
            "thinking_traces": [{
                "agent":     "reflector",
                "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
                "thinking":  raw_text,      # raw → JSON layer only
                "log_id":    log_id,
                "score":     reflection["quality_score"],
                "approved":  reflection["approved"],
                "loop":      reflection_count + 1,
            }],
            "execution_log": [{
                "node":       "reflector",
                "timestamp":  datetime.datetime.utcnow().isoformat() + "Z",
                "status":     "approved" if reflection["approved"] else "rejected",
                "latency_ms": latency_ms,
                "details": {
                    "score":            reflection["quality_score"],
                    "needs_replanning": reflection["needs_replanning"],
                    "loop":             reflection_count + 1,
                },
            }],
        }

    except Exception as e:
        latency_ms = (time.time() - t_start) * 1000
        err_msg    = f"Reflector LLM error: {type(e).__name__}: {e}"
        log.error(err_msg, exc_info=True)

        # Auto-approve on error to prevent stuck graph
        fallback = ReflectionResult(
            quality_score    = 0.5,
            issues           = [err_msg],
            suggestions      = [],
            approved         = True,
            needs_replanning = False,
            feedback         = f"Reflector failed — auto-approving: {e}",
        )
        return {
            "reflections":      [fallback],
            "reflection_count": reflection_count + 1,
            "is_complete":      True,
            "errors":           [err_msg],
            "execution_log": [{
                "node":       "reflector",
                "timestamp":  datetime.datetime.utcnow().isoformat() + "Z",
                "status":     "error",
                "error":      err_msg,
                "latency_ms": latency_ms,
            }],
        }
