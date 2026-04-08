# ============================================================
# state.py — LangGraph Graph State Definition
# ============================================================
# PURPOSE:
#   Defines the shared state that flows through the entire
#   LangGraph execution. Every node (planner, executor,
#   reflector) reads from and writes to this state.
#
# DESIGN PRINCIPLE:
#   State is immutable between nodes — each node returns a
#   *partial* dict that LangGraph merges. Use Annotated +
#   operator.add for list fields (append semantics).
#
# HOW TO EXTEND FOR A NEW PROJECT:
#   Add new fields to AgentState. For example, for fraud:
#     risk_score: float
#     flagged_transactions: list[dict]
#   For HR:
#     candidate_profile: dict
#     job_requirements: dict
# ============================================================

from __future__ import annotations

import operator
from typing import Annotated, Any, Optional
from typing_extensions import TypedDict


class Message(TypedDict):
    """
    A single message in the conversation history.

    Fields:
        role:    "user" | "assistant" | "system" | "tool"
        content: The text content of the message
        name:    Optional sender name (for tool results)
        tool_call_id: Optional tool call reference
    """
    role:         str
    content:      str
    name:         Optional[str]
    tool_call_id: Optional[str]


class ToolCall(TypedDict):
    """
    A record of a tool/skill invocation.

    Fields:
        tool_name:  Name of the tool called
        tool_input: Arguments passed to the tool (dict)
        tool_output: Result returned by the tool
        success:    Whether the call succeeded
        error:      Error message if failed
        timestamp:  ISO timestamp of the call
    """
    tool_name:   str
    tool_input:  dict
    tool_output: Any
    success:     bool
    error:       Optional[str]
    timestamp:   str


class PlanStep(TypedDict):
    """
    A single step in the planner's execution plan.

    Fields:
        step_id:     Unique identifier (e.g., "step_001")
        description: Human-readable description of the step
        tool:        Tool/skill to call (optional)
        args:        Arguments for the tool (optional)
        status:      "pending" | "running" | "done" | "failed"
        result:      Output after execution
    """
    step_id:     str
    description: str
    tool:        Optional[str]
    args:        Optional[dict]
    status:      str
    result:      Optional[Any]


class ReflectionResult(TypedDict):
    """
    Output from the Reflector agent.

    Fields:
        quality_score:   0.0–1.0 quality rating
        issues:          List of identified issues
        suggestions:     List of improvement suggestions
        approved:        True if result is acceptable
        needs_replanning: True if Planner should run again
        feedback:        Human-readable feedback string
    """
    quality_score:    float
    issues:           list[str]
    suggestions:      list[str]
    approved:         bool
    needs_replanning: bool
    feedback:         str


class AgentState(TypedDict):
    """
    ============================================================
    MASTER GRAPH STATE — flows through every LangGraph node
    ============================================================

    This is the single shared state object. LangGraph passes
    this between Planner → Executor → Reflector nodes.

    Fields with Annotated[list, operator.add] use APPEND
    semantics — each node adds to the list without overwriting.

    Fields without Annotated use OVERWRITE semantics — the
    last write wins.

    ── Core Task ────────────────────────────────────────────
    """

    # The original user request (never changes)
    user_query: str

    # Optional session ID for multi-turn conversations
    session_id: Optional[str]

    # Conversation messages (append-only)
    messages: Annotated[list[Message], operator.add]

    # ── Planning ─────────────────────────────────────────
    # The Planner's current execution plan
    plan: list[PlanStep]

    # Index of the currently executing plan step
    current_step_index: int

    # ── Execution ────────────────────────────────────────
    # Log of all tool calls made (append-only)
    tool_calls: Annotated[list[ToolCall], operator.add]

    # Intermediate results from executor (append-only)
    intermediate_results: Annotated[list[dict], operator.add]

    # ── Reflection ───────────────────────────────────────
    # History of all reflection results (append-only)
    reflections: Annotated[list[ReflectionResult], operator.add]

    # Count of reflection loops (prevents infinite cycling)
    reflection_count: int

    # ── Final Output ─────────────────────────────────────
    # The final answer/response to return to the user
    final_answer: Optional[str]

    # Whether the task is complete
    is_complete: bool

    # ── Memory Context ───────────────────────────────────
    # Episodic memories retrieved for this session
    episodic_context: list[dict]

    # Vector-searched relevant memories (RAG)
    vector_context: list[str]

    # Entity data retrieved for this session
    entity_context: dict[str, Any]

    # Working memory: scratch space for in-flight reasoning
    working_memory: dict[str, Any]

    # ── Metadata ─────────────────────────────────────────
    # Error accumulator (append-only)
    errors: Annotated[list[str], operator.add]

    # Thinking/reasoning traces from each agent (append-only)
    thinking_traces: Annotated[list[dict], operator.add]

    # Full audit trail of node executions (append-only)
    execution_log: Annotated[list[dict], operator.add]

    # ISO timestamp when the run started
    started_at: Optional[str]


def create_initial_state(
    user_query: str,
    session_id: Optional[str] = None,
    entity_context: Optional[dict] = None,
    episodic_context: Optional[list] = None,
    vector_context: Optional[list] = None,
) -> AgentState:
    """
    Factory function: create a fresh AgentState for a new run.

    Args:
        user_query:       The user's request string
        session_id:       Optional session ID for continuity
        entity_context:   Pre-loaded entity memory (optional)
        episodic_context: Pre-loaded episodic memories (optional)
        vector_context:   Pre-loaded RAG context (optional)

    Returns:
        A fully initialized AgentState dict

    Example:
        state = create_initial_state(
            user_query="Analyze this transaction for fraud",
            session_id="sess_abc123"
        )
    """
    import datetime
    return AgentState(
        user_query=user_query,
        session_id=session_id,
        messages=[
            Message(role="user", content=user_query, name=None, tool_call_id=None)
        ],
        plan=[],
        current_step_index=0,
        tool_calls=[],
        intermediate_results=[],
        reflections=[],
        reflection_count=0,
        final_answer=None,
        is_complete=False,
        episodic_context=episodic_context or [],
        vector_context=vector_context or [],
        entity_context=entity_context or {},
        working_memory={},
        errors=[],
        thinking_traces=[],
        execution_log=[],
        started_at=datetime.datetime.utcnow().isoformat() + "Z",
    )
