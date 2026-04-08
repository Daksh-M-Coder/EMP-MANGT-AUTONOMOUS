# ============================================================
# graph.py — LangGraph Workflow Assembly  V5 (STABLE)
# ============================================================
# IMPROVED IN THIS VERSION:
#   + Full graph topology ASCII diagram with node descriptions
#   + React.js integration guide: how the graph maps to API calls
#   + Detailed edge routing documentation with decision tables
#   + load_memory_context(): documents all three memory layers
#   + save_episode_after_run(): dual-format (JSON + MD) save
#   + log_graph_event() calls on every edge decision for audit
#   + Universal template guide: adapting the graph to new domains
#   + Safety valves documented: MAX_ITERATIONS, MAX_REFLECTION_LOOPS
#   + get_graph() singleton with lazy init pattern
#
# ════════════════════════════════════════════════════════════
# GRAPH TOPOLOGY
# ════════════════════════════════════════════════════════════
#
#   ┌─────────┐      ┌──────────────┐      ┌─────────────────┐
#   │  START  │─────▶│   PLANNER    │─────▶│    EXECUTOR     │
#   └─────────┘      │ temp=0.3     │      │ temp=0.1        │
#                    │ Decomposes   │      │ Executes steps  │
#                    │ task into    │      │ one at a time,  │
#                    │ plan steps   │      │ calls tools     │
#                    └──────────────┘      └───────┬─────────┘
#                           ▲                      │
#                           │                 more steps?
#                    [needs_replanning]        │        │
#                           │               yes        no
#                    ┌──────┴───────┐        │        │
#                    │   REFLECTOR  │◀───────┘        │
#                    │ temp=0.2     │◀────────────────┘
#                    │ Scores 0-1   │
#                    │ Decides:     │
#                    │ approve /    │
#                    │ retry /      │
#                    │ replan       │
#                    └──────┬───────┘
#                           │
#              ┌────────────┼──────────────┐
#         [approved]    [retry]    [needs_replanning]
#              │             │              │
#           ┌──▼──┐    EXECUTOR        PLANNER
#           │ END │    (re-synthesize)  (new plan)
#           └─────┘
#
# ════════════════════════════════════════════════════════════
# EDGE ROUTING DECISION TABLE
# ════════════════════════════════════════════════════════════
#
#   After EXECUTOR:
#   ─────────────────────────────────────────────────────────
#   is_complete=True  OR  idx >= len(plan)  → REFLECTOR
#   n_executions >= MAX_ITERATIONS          → REFLECTOR (safety)
#   else                                    → EXECUTOR  (next step)
#
#   After REFLECTOR:
#   ─────────────────────────────────────────────────────────
#   reflection_count >= MAX_REFLECTION_LOOPS → END       (safety)
#   reflection["approved"] = True            → END       (✅ done)
#   reflection["needs_replanning"] = True    → PLANNER   (new plan)
#   else (approved=False, no replan)         → EXECUTOR  (retry)
#
# ════════════════════════════════════════════════════════════
# REACT.JS INTEGRATION — How graph maps to API calls
# ════════════════════════════════════════════════════════════
#
#   The graph is NEVER called directly from React.
#   React → HTTP → server.py → graph.invoke() → return.
#
#   Simple call (blocks until done):
#     POST /run → graph.invoke(state) → RunResponse JSON
#
#   Streaming call (real-time node events):
#     GET /stream → graph.stream(state) → SSE events:
#       { type: "node_complete", node: "planner", ... }
#       { type: "node_complete", node: "executor", ... }
#       { type: "node_complete", node: "reflector", ... }
#       { type: "final", final_answer: "...", duration_ms: 3241 }
#
# ════════════════════════════════════════════════════════════
# ADAPTING THE GRAPH TO A NEW DOMAIN
# ════════════════════════════════════════════════════════════
#
#   To add a new node (e.g., "risk_scorer" for fraud):
#
#     # 1. Create a function in a new file risk_scorer.py:
#     def risk_scorer_node(state: AgentState) -> dict:
#         score = my_risk_model(state["working_memory"])
#         return {"working_memory": {**state["working_memory"],
#                                    "risk_score": {"value": score}}}
#
#     # 2. Add to workflow in build_graph():
#     workflow.add_node("risk_scorer", risk_scorer_node)
#     workflow.add_edge("planner", "risk_scorer")      # runs after planner
#     workflow.add_edge("risk_scorer", "executor")     # then executor
#
#   To change the graph topology just edit build_graph() below.
#   The state (AgentState) carries ALL data between nodes.
#
# ============================================================

import datetime
from typing import Literal, Optional

from langgraph.graph import StateGraph, START, END

from config import cfg
from state import AgentState
from planner import planner_node
from executor import executor_node
from reflector import reflector_node
from logger import get_logger, log_graph_event

log = get_logger("graph")


# ════════════════════════════════════════════════════════════
# CONTEXT WINDOW MANAGEMENT  (V5 new)
# ════════════════════════════════════════════════════════════
#
# WHY: Small models (nemotron-mini, granite MoE) have limited context.
#      We start with a small window for the Planner (fewer tokens needed),
#      grow it for the Executor as step results accumulate, and give the
#      Reflector a moderate window to evaluate the final answer.
#
# HOW: graph.py calls estimate_prompt_tokens() before each node and
#      optionally truncates the accumulated context to stay within limits.
#      The actual num_ctx is passed to llm_factory via cfg.get_llm(),
#      which sets it as the Ollama num_ctx parameter.
#
# CONTEXT SIZES (from config.py AGENT_CONTEXT_WINDOWS):
#   planner:   4096  — query + memory snippets + tool list
#   executor:  8192  — grows by CONTEXT_EXPAND_PER_STEP each step
#   reflector: 4096  — final answer + plan summary

from config import AGENT_CONTEXT_WINDOWS, CONTEXT_WINDOW_MAX

# How many tokens to add per completed executor step (rough estimate)
CONTEXT_EXPAND_PER_STEP: int = 512

def estimate_prompt_tokens(text: str) -> int:
    """
    Rough token count estimate: ~4 characters per token (English).

    This is a heuristic, not exact. Good enough for deciding when
    to truncate context before sending to the LLM.

    Args:
        text: Any string (prompt, context snippet, answer)

    Returns:
        Estimated token count (integer)
    """
    return max(1, len(text) // 4)


def get_executor_context_size(step_index: int) -> int:
    """
    Return the dynamic context window size for the Executor.

    Grows by CONTEXT_EXPAND_PER_STEP tokens per completed step,
    capped at CONTEXT_WINDOW_MAX to prevent OOM.

    Args:
        step_index: current_step_index from AgentState (0-based)

    Returns:
        Context window size in tokens

    Example:
        step 0 → 8192  (base)
        step 1 → 8704  (+512)
        step 3 → 9728  (+1536)
        cap    → 16384 (CONTEXT_WINDOW_MAX)
    """
    base    = AGENT_CONTEXT_WINDOWS.get("executor", 8192)
    dynamic = base + (step_index * CONTEXT_EXPAND_PER_STEP)
    return min(dynamic, CONTEXT_WINDOW_MAX)


def truncate_to_token_limit(text: str, max_tokens: int) -> str:
    """
    Truncate a string to approximately max_tokens tokens.

    Uses the 4-chars-per-token heuristic. Adds a clear marker
    at the truncation point so the LLM knows context was cut.

    Args:
        text:       Input string to truncate
        max_tokens: Maximum token count to allow

    Returns:
        Original string (if within limit) or truncated string
        with "[...context truncated for length...]" marker

    Usage in planner.py / executor.py:
        safe_context = truncate_to_token_limit(memory_context, 1500)
    """
    char_limit = max_tokens * 4
    if len(text) <= char_limit:
        return text
    truncated = text[:char_limit]
    # Cut at last newline to avoid splitting mid-sentence
    last_nl = truncated.rfind("\n")
    if last_nl > char_limit // 2:
        truncated = truncated[:last_nl]
    return truncated + "\n[...context truncated for length...]"


# ════════════════════════════════════════════════════════════
# EDGE ROUTING FUNCTIONS
# ════════════════════════════════════════════════════════════

def route_after_executor(state: AgentState) -> Literal["reflector", "executor"]:
    """
    Conditional edge: decides next node after EXECUTOR runs.

    ── DECISION LOGIC ───────────────────────────────────────
    Condition 1: is_complete=True            → reflector
      The Executor flagged the task as finished (final synthesis done).

    Condition 2: current_step_index >= len(plan) → reflector
      We've moved past the last step (index overrun guard).

    Condition 3: n_executions >= MAX_ITERATIONS  → reflector
      Safety valve — prevents runaway infinite loops.
      Logs a warning when triggered.

    Condition 4: (none of the above)            → executor
      More plan steps remain — loop back for the next one.

    ── STATE FIELDS READ ────────────────────────────────────
    state["plan"]                  → to know total step count
    state["current_step_index"]    → to know which step we're on
    state["is_complete"]           → executor's "done" signal
    state["execution_log"]         → to count executor iterations

    ── REACT.JS VISIBILITY ──────────────────────────────────
    When streaming (/stream), every routing decision emits a
    "node_complete" SSE event with:
      { node: "executor", data: { step_index: N, is_complete: bool } }
    Frontend can show a step progress bar using step_index / plan_steps.

    Args:
        state: Current AgentState

    Returns:
        "reflector" | "executor"
    """
    plan         = state.get("plan", [])
    idx          = state.get("current_step_index", 0)
    done         = state.get("is_complete", False)
    exec_logs    = [l for l in state.get("execution_log", [])
                    if l.get("node") == "executor"]
    n_executions = len(exec_logs)

    if n_executions >= cfg.MAX_ITERATIONS:
        log.warning(
            f"⚠️  MAX_ITERATIONS={cfg.MAX_ITERATIONS} reached — "
            f"forcing to reflector"
        )
        log_graph_event("edge", "executor→reflector",
                        {"reason": "max_iterations", "count": n_executions},
                        state.get("session_id"))
        return "reflector"

    if done or idx >= len(plan):
        log.info(f"Executor→Reflector | step={idx}/{len(plan)} is_complete={done}")
        log_graph_event("edge", "executor→reflector",
                        {"reason": "done", "step": idx, "n_steps": len(plan)},
                        state.get("session_id"))
        return "reflector"

    log.info(f"Executor→Executor (loop) | step={idx}/{len(plan)}")
    log_graph_event("edge", "executor→executor",
                    {"step": idx, "n_steps": len(plan)},
                    state.get("session_id"))
    return "executor"


def route_after_reflector(
    state: AgentState,
) -> Literal["__end__", "planner", "executor"]:
    """
    Conditional edge: decides next node after REFLECTOR runs.

    ── DECISION TABLE ───────────────────────────────────────
    reflection_count >= MAX_REFLECTION_LOOPS  → END   (safety cap)
    reflection["approved"] = True             → END   (✅ accepted)
    reflection["needs_replanning"] = True     → PLANNER (new plan)
    else (approved=F, no replan)              → EXECUTOR (retry)

    ── STATE FIELDS READ ────────────────────────────────────
    state["reflections"]       → list of ReflectionResult dicts
    state["reflection_count"]  → how many reflection loops ran

    ── REACT.JS VISIBILITY ──────────────────────────────────
    When streaming, the "node_complete" event for "reflector" carries:
      { node: "reflector", data: { is_complete: bool } }
    The final "final" event carries is_complete=true on approval.

    Args:
        state: Current AgentState

    Returns:
        "__end__" | "planner" | "executor"
    """
    reflections      = state.get("reflections", [])
    reflection_count = state.get("reflection_count", 0)
    max_reflect      = cfg.MAX_REFLECTION_LOOPS

    if not reflections:
        log.warning("Reflector: no reflections found → routing to END")
        return "__end__"

    if reflection_count >= max_reflect:
        log.info(f"Reflector→END (max loops={reflection_count}/{max_reflect})")
        log_graph_event("edge", "reflector→end",
                        {"reason": "max_loops", "count": reflection_count},
                        state.get("session_id"))
        return "__end__"

    latest = reflections[-1]

    if latest.get("approved"):
        score = latest.get("quality_score", 0)
        log.info(f"Reflector→END ✅ approved | score={score:.2f}")
        log_graph_event("edge", "reflector→end",
                        {"reason": "approved", "score": score},
                        state.get("session_id"))
        return "__end__"

    if latest.get("needs_replanning"):
        log.info(f"Reflector→Planner 🔄 needs_replanning | "
                 f"issues={latest.get('issues', [])}")
        log_graph_event("edge", "reflector→planner",
                        {"reason": "needs_replanning",
                         "issues": latest.get("issues", [])},
                        state.get("session_id"))
        return "planner"

    score = latest.get("quality_score", 0)
    log.info(f"Reflector→Executor ↩️ retry | score={score:.2f}")
    log_graph_event("edge", "reflector→executor",
                    {"reason": "retry", "score": score},
                    state.get("session_id"))
    return "executor"


# ════════════════════════════════════════════════════════════
# GRAPH BUILDER
# ════════════════════════════════════════════════════════════

def build_graph() -> StateGraph:
    """
    Assemble and compile the LangGraph StateGraph.

    Returns:
        CompiledGraph — has .invoke(), .stream(), .astream() methods

    ── HOW INVOKE WORKS ─────────────────────────────────────
        result = graph.invoke(initial_state)
        # Runs all nodes synchronously until END
        # Returns the final merged AgentState dict

    ── HOW STREAM WORKS ─────────────────────────────────────
        for chunk in graph.stream(initial_state):
            for node_name, state_update in chunk.items():
                print(f"Node '{node_name}' completed")
        # Yields one dict per node execution: { node_name: update }

    ── REACT.JS DOES NOT CALL THIS DIRECTLY ─────────────────
        React → POST /run    → _run_agent() → graph.invoke()
        React → GET  /stream → event_generator() → graph.stream()
        See server.py for the full HTTP contract.

    ── ADDING NEW NODES (domain extension) ──────────────────
        def my_node(state: AgentState) -> dict:
            return {"working_memory": {...}}

        workflow.add_node("my_node", my_node)
        workflow.add_edge("planner", "my_node")
        workflow.add_edge("my_node", "executor")
        # Remove: workflow.add_edge("planner", "executor")
    """
    log.info("Building LangGraph workflow...")
    workflow = StateGraph(AgentState)

    # ── Nodes ─────────────────────────────────────────────
    # Each is a Python function: (AgentState) → partial dict
    workflow.add_node("planner",   planner_node)
    workflow.add_node("executor",  executor_node)
    workflow.add_node("reflector", reflector_node)

    # ── Edges ─────────────────────────────────────────────
    workflow.add_edge(START, "planner")         # Entry point
    workflow.add_edge("planner", "executor")    # Planner always → Executor

    # Executor → loop back OR go to reflector
    workflow.add_conditional_edges(
        "executor",
        route_after_executor,
        {"executor": "executor", "reflector": "reflector"},
    )

    # Reflector → END, replan, or retry
    workflow.add_conditional_edges(
        "reflector",
        route_after_reflector,
        {"__end__": END, "planner": "planner", "executor": "executor"},
    )

    compiled = workflow.compile()
    log.info(
        f"✅ Graph compiled | nodes=[planner,executor,reflector] | "
        f"MAX_ITER={cfg.MAX_ITERATIONS} | MAX_REFLECT={cfg.MAX_REFLECTION_LOOPS}"
    )
    return compiled


# ════════════════════════════════════════════════════════════
# MULTI-MODEL RUN HELPER (V4 new)
# ════════════════════════════════════════════════════════════

def invoke_with_model_map(
    state:     dict,
    model_map: Optional[dict[str, str]] = None,
) -> dict:
    """
    Run the graph with a per-agent model override for this run only.

    This is the V4 multi-model entry point. Different agents can
    use different Ollama models in a single pipeline run.

    HOW IT WORKS:
        1. cfg.set_agent_models(model_map) — activates overrides
        2. graph.invoke(state)             — runs Planner/Executor/Reflector
           Each agent calls cfg.get_llm(agent) which now respects the map.
        3. cfg.set_agent_models(None)      — clears overrides after run

    Args:
        state:     Initial AgentState dict (from create_initial_state)
        model_map: Per-agent model override dict.
                   Keys: "planner", "executor", "reflector"
                   Values: Ollama model tags from OLLAMA_MODEL_REGISTRY
                   Missing keys use env-configured defaults.

    Returns:
        Final merged AgentState dict

    Examples:
        # All three agents use different models:
        result = invoke_with_model_map(state, {
            "planner":   "qwen2.5-coder:3b",
            "executor":  "granite3.1-moe:3b",
            "reflector": "nemotron-mini",
        })

        # Only override executor (planner + reflector use defaults):
        result = invoke_with_model_map(state, {
            "executor": "deepseek-r1:1.5b",
        })

        # Standard run (no overrides):
        result = invoke_with_model_map(state)

    React.js — how to trigger multi-model run:
        POST /run  {
          "query": "...",
          "model_map": {
            "planner":   "qwen2.5-coder:3b",
            "executor":  "granite3.1-moe:3b",
            "reflector": "nemotron-mini"
          }
        }
        # server.py reads model_map from RunRequest and passes here

    Logging:
        The active model map is logged at run start and stored in
        execution_log entries so you can trace which model ran each step.
    """
    graph = get_graph()

    # Apply model overrides for this run
    cfg.set_agent_models(model_map)

    if model_map:
        resolved = cfg.get_active_model_map()
        log.info(
            f"🎯 Multi-model run | "
            f"planner={resolved['planner']} | "
            f"executor={resolved['executor']} | "
            f"reflector={resolved['reflector']}"
        )
    else:
        log.info("Running with default model configuration")

    try:
        final_state = graph.invoke(state)
    finally:
        # Always clear overrides — even on exception
        cfg.set_agent_models(None)

    return final_state


# ════════════════════════════════════════════════════════════
# MEMORY CONTEXT LOADER
# ════════════════════════════════════════════════════════════

def load_memory_context(query: str, session_id: str = None) -> dict:
    """
    Pre-load all three memory layers before graph.invoke().

    ── THREE MEMORY LAYERS ──────────────────────────────────

    1. EPISODIC MEMORY (memory/json/episodic.jsonl)
       What: Records of past agent runs for this session.
       Used: Injected as "past context" into Planner prompt.
       JSON file:  memory/json/episodic.jsonl  (full records + thinking)
       MD file:    memory/md/episodic_summary.md (clean summaries)

    2. VECTOR MEMORY (FAISS index in memory/vector_index/)
       What: Semantic RAG search over all past Q&A + domain knowledge.
       Used: Top-K relevant snippets injected into Planner prompt.
       JSON log:   memory/json/vector_YYYY-MM-DD.jsonl (addition events)
       MD index:   memory/md/vector_memory.md  (text snippets, no embeddings)

    3. ENTITY MEMORY (memory/json/entity_*.json + memory/md/entity_*.md)
       What: Structured facts about named entities (users, companies, etc.)
       Used: Loaded as key-value context for the Executor.
       JSON file:  memory/json/entity_<n>.json (full record + history)
       MD file:    memory/md/entity_<n>.md  (clean fact sheet)

    Args:
        query:      User's query string (for vector RAG search)
        session_id: Session identifier (for episodic lookup)

    Returns:
        {
          "episodic_context": [list of episode dicts],
          "vector_context":   [list of relevant text strings],
          "entity_context":   { entity_name: data_dict, ... }
        }

    Usage:
        memory = load_memory_context(query, session_id)
        state  = create_initial_state(query, **memory)
        result = graph.invoke(state)
    """
    episodic_context: list = []
    vector_context:   list = []
    entity_context:   dict = {}

    # ── Layer 1: Episodic ────────────────────────────────
    try:
        from memory.episodic_store import EpisodicStore
        store = EpisodicStore()
        if session_id:
            episodic_context = store.get_by_session(session_id)[-3:]
        else:
            episodic_context = store.get_recent(3)
        log.debug(f"Episodic: loaded {len(episodic_context)} episodes")
    except Exception as e:
        log.warning(f"Episodic load failed: {e}")

    # ── Layer 2: Vector RAG ──────────────────────────────
    try:
        from memory.vector_store import VectorMemoryStore
        vs             = VectorMemoryStore()
        vector_context = vs.search_texts(query, top_k=cfg.VECTOR_TOP_K)
        log.debug(f"Vector RAG: {len(vector_context)} results for '{query[:40]}'")
    except Exception as e:
        log.warning(f"Vector search failed: {e}")

    # ── Layer 3: Entity ──────────────────────────────────
    try:
        from memory.entity_memory import EntityMemory
        entity_context = EntityMemory().load_all()
        log.debug(f"Entity: loaded {len(entity_context)} entities")
    except Exception as e:
        log.warning(f"Entity load failed: {e}")

    return {
        "episodic_context": episodic_context,
        "vector_context":   vector_context,
        "entity_context":   entity_context,
    }


# ════════════════════════════════════════════════════════════
# EPISODE SAVER
# ════════════════════════════════════════════════════════════

def save_episode_after_run(final_state: AgentState) -> str:
    """
    Persist the completed run to all memory layers.

    ── WHAT GETS SAVED WHERE ────────────────────────────────

    memory/json/episodic.jsonl (APPEND):
      Full episode record including:
        - user_query, final_answer, plan, tool_calls
        - reflections with quality scores
        - thinking_traces (raw LLM reasoning — JSON layer only)
        - errors, started_at, reflection_count
      Never deleted. Full technical record.

    memory/md/episodic_summary.md (APPEND):
      Clean summary:
        - Query, final answer (truncated)
        - Step count, tool count, reflection count
        - Success/failure status + emoji
      NO thinking traces. NO raw JSON. Human-readable only.

    memory/vector_index/ (FAISS index update):
      Indexes the Q&A pair for future RAG:
        "Query: <user_query>\\nAnswer: <final_answer[:500]>"
      Metadata: { episode_id, session_id, type: "qa_pair" }

    Args:
        final_state: The fully merged AgentState after graph END

    Returns:
        episode_id string (e.g. "ep_20250115_143022_sess_abc")

    React.js:
        // episode_id is returned in every RunResponse and final SSE event:
        const { episode_id } = await fetch('/run', {...}).then(r => r.json());
        // Use it to retrieve this specific episode later:
        const history = await fetch(`/memory/episodic?session_id=${sid}`).then(r=>r.json());
    """
    from memory.episodic_store import EpisodicStore

    store      = EpisodicStore()
    episode_id = store.save_episode(dict(final_state))

    # Also index the Q&A in vector memory for future RAG
    try:
        if final_state.get("final_answer"):
            from memory.vector_store import VectorMemoryStore
            vs = VectorMemoryStore()
            vs.add_texts(
                [
                    f"Query: {final_state['user_query']}\n"
                    f"Answer: {final_state['final_answer'][:500]}"
                ],
                metadatas=[{
                    "episode_id": episode_id,
                    "session_id": final_state.get("session_id") or "",
                    "type":       "qa_pair",
                }]
            )
    except Exception as e:
        log.warning(f"Vector indexing after run failed: {e}")

    return episode_id


# ════════════════════════════════════════════════════════════
# SINGLETON
# ════════════════════════════════════════════════════════════

_graph = None

def get_graph():
    """
    Return the singleton compiled graph (lazy initialization).

    Thread-safe: LangGraph graphs are stateless — the same compiled
    graph object handles concurrent requests safely.

    For standard runs:
        graph = get_graph()
        result = graph.invoke(initial_state)

    For multi-model runs (V4):
        result = invoke_with_model_map(initial_state, {
            "planner":   "qwen2.5-coder:3b",
            "executor":  "granite3.1-moe:3b",
            "reflector": "nemotron-mini",
        })
    """
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph
