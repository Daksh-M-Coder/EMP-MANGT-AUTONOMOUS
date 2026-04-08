# ============================================================
# server.py — FastAPI HTTP Server  V5 (STABLE)
# ============================================================
# IMPROVED IN THIS VERSION:
#   + Every endpoint has a FULL documentation block:
#       - Exact request JSON with real-world example
#       - Exact response JSON with every field explained
#       - React.js fetch snippet + TypeScript interface
#       - React hook pattern for each endpoint
#   + POST /run    — full pipeline with metadata injection
#   + GET  /stream — SSE streaming, complete event catalogue
#   + GET  /health — config + skill + graph status (safe)
#   + GET/POST /skills + /skills/reload
#   + Full memory API: episodic, entities, vector add/search
#   + GET /logs — JSON and Markdown retrieval with date filter
#   + DELETE /memory/entity/{name}
#   + POST /memory/vector/add — seed domain knowledge
#   + Universal template guide at top — use for ANY project
#   + All Pydantic models documented as TypeScript interfaces
#   + CORS fully configured for React dev (localhost:3000/5173)
#
# ════════════════════════════════════════════════════════════
# UNIVERSAL TEMPLATE GUIDE — Reuse for any domain project
# ════════════════════════════════════════════════════════════
#
#   This server.py is 100% domain-agnostic.
#   To use it for Fraud / HR / Trading / PersonalAssistant:
#
#   1. Change .env only:
#        PROJECT_NAME=FraudGuard
#        SYSTEM_PROMPT=You are a fraud detection AI...
#        DB_URL=postgresql://user:pass@host/frauddb
#
#   2. Add skills to /skills/:
#        skills/fraud_scorer.py
#        skills/md_skills/fraud_playbook.md
#
#   3. No server.py changes needed. The /run endpoint passes
#      domain metadata via working_memory automatically:
#        {
#          "query": "Is TX001 fraudulent?",
#          "metadata": { "amount": 9800, "country": "NG" }
#        }
#      → metadata injected into state["working_memory"]
#      → Executor reads it via wm.get("amount")
#
#   4. One React component works for ALL domains:
#        const AgentPanel = ({ projectName }) => {
#          const [answer, setAnswer] = useState('');
#          const [loading, setLoading] = useState(false);
#          const run = async (query, metadata = {}) => {
#            setLoading(true);
#            const res = await fetch(`${API_BASE}/run`, {
#              method: 'POST',
#              headers: { 'Content-Type': 'application/json' },
#              body: JSON.stringify({ query, session_id: sid, metadata })
#            });
#            const data = await res.json();
#            setAnswer(data.final_answer);
#            setLoading(false);
#          };
#          return <div><input onSubmit={run} /><p>{answer}</p></div>;
#        };
#
# ════════════════════════════════════════════════════════════
# REACT TYPESCRIPT INTERFACES — Copy into your frontend types.ts
# ════════════════════════════════════════════════════════════
#
#   // ── Request ──────────────────────────────────────────
#   interface RunRequest {
#     query: string;                    // required, 1-10000 chars
#     session_id?: string;              // optional; auto-generated if absent
#     metadata?: Record<string, any>;  // domain context → working_memory
#   }
#
#   // ── Plan Step ─────────────────────────────────────────
#   interface PlanStep {
#     step_id:     string;              // "step_001", "step_002"
#     description: string;             // human-readable step goal
#     tool:        string | null;      // tool name or null
#     status:      "pending"|"running"|"done"|"failed";
#     result:      string | null;      // truncated step output
#   }
#
#   // ── Tool Call ─────────────────────────────────────────
#   interface ToolCallRecord {
#     tool_name:   string;
#     tool_input:  Record<string, any>;
#     tool_output: string | null;
#     success:     boolean;
#     error:       string | null;
#     timestamp:   string;             // ISO 8601
#   }
#
#   // ── Reflection ────────────────────────────────────────
#   interface ReflectionRecord {
#     quality_score:    number;        // 0.0 (bad) – 1.0 (perfect)
#     issues:           string[];
#     suggestions:      string[];
#     approved:         boolean;
#     needs_replanning: boolean;
#     feedback:         string;
#   }
#
#   // ── Run Response ──────────────────────────────────────
#   interface RunResponse {
#     session_id:       string;
#     episode_id:       string | null;
#     final_answer:     string | null;
#     is_complete:      boolean;
#     plan:             PlanStep[];
#     tool_calls:       ToolCallRecord[];
#     reflections:      ReflectionRecord[];
#     reflection_count: number;
#     errors:           string[];
#     started_at:       string | null;
#     completed_at:     string | null;
#     duration_ms:      number | null;
#   }
#
#   // ── SSE Stream Events (for GET /stream) ───────────────
#   type AgentEvent =
#     | { type: "started";      session_id: string; timestamp: string }
#     | { type: "node_complete"; node: string; timestamp: string; data: {
#           plan_steps: number; is_complete: boolean; step_index: number;
#         }}
#     | { type: "final";        final_answer: string; episode_id: string;
#                               duration_ms: number; is_complete: boolean }
#     | { type: "error";        error: string };
#
# ============================================================

import asyncio
import datetime
import json
import uuid
import threading
from typing import AsyncIterator, Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from config import cfg
from graph import build_graph, get_graph, load_memory_context, save_episode_after_run
from state import create_initial_state
from skill_loader import get_registry, reload_skills
from logger import get_logger

log = get_logger("server")


# ════════════════════════════════════════════════════════════
# PYDANTIC MODELS — Contracts between backend and React.js
# ════════════════════════════════════════════════════════════

class RunRequest(BaseModel):
    """
    POST /run  &  GET /stream — Request body

    TypeScript:
        interface RunRequest {
          query:      string;
          session_id?: string;
          metadata?:  Record<string, any>;
        }

    Examples:
        // Minimal:
        { "query": "What is 15% of 2400?" }

        // With session (memory continuity across turns):
        { "query": "Follow up on that", "session_id": "sess_abc123" }

        // Fraud detection + domain metadata:
        {
          "query": "Is this transaction fraudulent?",
          "session_id": "sess_fraud_001",
          "metadata": {
            "transaction_id": "TX001",
            "amount": 9800,
            "country": "NG",
            "account_age_days": 2,
            "is_new_device": true,
            "hour_of_day": 3
          }
        }

        // HR assistant:
        {
          "query": "Should we advance this candidate?",
          "metadata": { "candidate_id": "C042", "role": "senior_eng" }
        }

        // Trading:
        {
          "query": "Should we buy AAPL today?",
          "metadata": { "ticker": "AAPL", "portfolio_value": 100000 }
        }

        // V4 Multi-model run — different model per agent:
        {
          "query": "Analyze this transaction for fraud",
          "model_map": {
            "planner":   "qwen2.5-coder:3b",
            "executor":  "granite3.1-moe:3b",
            "reflector": "nemotron-mini"
          }
        }

        // V4 Override just one agent (others use env defaults):
        {
          "query": "Calculate compound interest",
          "model_map": { "executor": "deepseek-r1:1.5b" }
        }
    """
    query:      str                       = Field(..., min_length=1, max_length=10000)
    session_id: Optional[str]             = Field(None, description="Auto-generated if absent")
    metadata:   Optional[dict]            = Field(None, description="Injected into working_memory")
    model_map:  Optional[dict[str, str]]  = Field(
        None,
        description=(
            "V4: Per-agent model override for this run only. "
            "Keys: 'planner' | 'executor' | 'reflector'. "
            "Values: Ollama model tags (e.g. 'qwen2.5-coder:3b'). "
            "Missing keys use env-configured defaults. "
            "GET /models to see all available model tags."
        ),
    )


class StepResult(BaseModel):
    step_id:     str
    description: str
    tool:        Optional[str] = None
    status:      str
    result:      Optional[str] = None


class ToolCallRecord(BaseModel):
    tool_name:   str
    tool_input:  dict
    tool_output: Optional[str] = None
    success:     bool
    error:       Optional[str] = None
    timestamp:   str


class ReflectionRecord(BaseModel):
    quality_score:    float
    issues:           list[str]
    suggestions:      list[str]
    approved:         bool
    needs_replanning: bool
    feedback:         str


class RunResponse(BaseModel):
    """
    POST /run — Response body

    TypeScript:
        interface RunResponse { ... }  // see header comments

    React usage:
        const data: RunResponse = await response.json();
        // Main answer:
        <p>{data.final_answer}</p>
        // Plan progress bar:
        const done = data.plan.filter(s => s.status === 'done').length;
        <progress value={done} max={data.plan.length} />
        // Quality score:
        <Badge score={data.reflections[0]?.quality_score} />
        // Duration:
        <span>{data.duration_ms?.toFixed(0)}ms</span>
    """
    session_id:         str
    episode_id:         Optional[str]          = None
    final_answer:       Optional[str]          = None
    is_complete:        bool                   = False
    plan:               list[StepResult]       = []
    tool_calls:         list[ToolCallRecord]   = []
    reflections:        list[ReflectionRecord] = []
    reflection_count:   int                    = 0
    errors:             list[str]              = []
    started_at:         Optional[str]          = None
    completed_at:       Optional[str]          = None
    duration_ms:        Optional[float]        = None
    active_model_map:   Optional[dict]         = None   # V4: which model ran each agent


class VectorSearchRequest(BaseModel):
    """POST /memory/vector/search — Request"""
    query: str = Field(..., min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)


class VectorAddRequest(BaseModel):
    """POST /memory/vector/add — Request"""
    texts:     list[str]             = Field(..., min_items=1)
    metadatas: Optional[list[dict]]  = None


class HealthResponse(BaseModel):
    status:       str
    timestamp:    str
    config:       dict
    skills_count: int
    graph_ready:  bool


# ════════════════════════════════════════════════════════════
# FASTAPI APP
# ════════════════════════════════════════════════════════════

app = FastAPI(
    title       = f"{cfg.PROJECT_NAME} — Universal LangGraph Agent API",
    description = (
        "Production-grade multi-agent system: Planner + Executor + Reflector. "
        "Adaptable to any domain by changing only .env and /skills/."
    ),
    version  = cfg.PROJECT_VERSION,
    docs_url = "/docs",
    redoc_url= "/redoc",
)

# ── CORS — allow React dev servers ────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins     = ["http://localhost:3000", "http://localhost:5173", "*"],
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)


# ── Startup ───────────────────────────────────────────────────
@app.on_event("startup")
async def startup_event():
    log.info(f"🚀 Starting {cfg.PROJECT_NAME} v{cfg.PROJECT_VERSION} (V5 stable)")
    log.info(f"   Provider:  {cfg.PROVIDER}")
    # Show which model each agent is using — critical for debugging
    active = cfg.get_active_model_map()
    log.info(f"   Planner:   {active['planner']}")
    log.info(f"   Executor:  {active['executor']}")
    log.info(f"   Reflector: {active['reflector']}")
    log.info(f"   Max iter:  {cfg.MAX_ITERATIONS} | Max reflect: {cfg.MAX_REFLECTION_LOOPS}")
    registry = get_registry()
    log.info(f"   Skills:    {len(registry)} → {registry.names}")
    _ = get_graph()
    log.info(f"   Graph:     compiled ✅")
    log.info(f"🌐 Docs: http://{cfg.SERVER_HOST}:{cfg.SERVER_PORT}/docs | "
             f"Models: http://{cfg.SERVER_HOST}:{cfg.SERVER_PORT}/models")


# ── Internal pipeline runner ──────────────────────────────────
async def _run_agent(request: RunRequest) -> tuple[dict, str]:
    """
    Run the full Planner→Executor→Reflector pipeline asynchronously.

    V4: Uses invoke_with_model_map() so model_map in RunRequest
    is respected — each agent can use a different Ollama model.
    """
    from graph import invoke_with_model_map

    session_id = request.session_id or f"sess_{uuid.uuid4().hex[:8]}"
    memory_ctx = load_memory_context(request.query, session_id)
    initial    = create_initial_state(
        user_query       = request.query,
        session_id       = session_id,
        episodic_context = memory_ctx["episodic_context"],
        vector_context   = memory_ctx["vector_context"],
        entity_context   = memory_ctx["entity_context"],
    )
    if request.metadata:
        import datetime as _dt
        ts = _dt.datetime.utcnow().isoformat() + "Z"
        initial["working_memory"] = {
            k: {"value": v, "set_at": ts}
            for k, v in request.metadata.items()
        }

    model_map = request.model_map if hasattr(request, "model_map") else None
    loop      = asyncio.get_event_loop()
    final     = await loop.run_in_executor(
        None,
        lambda: invoke_with_model_map(initial, model_map),
    )
    return final, session_id


# ════════════════════════════════════════════════════════════
# ENDPOINT: POST /run
# ════════════════════════════════════════════════════════════

@app.post("/run", response_model=RunResponse)
async def run_agent(request: RunRequest) -> RunResponse:
    """
    ════════════════════════════════════════════════════════════
    POST /run — Run the full agent pipeline (synchronous result)
    ════════════════════════════════════════════════════════════

    Triggers: Planner → Executor (loop) → Reflector (loop) → END
    Blocks until the pipeline finishes; returns the full result.
    For real-time progress use GET /stream instead.

    ── REQUEST JSON ─────────────────────────────────────────
    {
      "query":      "What is 15% of 2400?",      // required
      "session_id": "sess_abc123",               // optional
      "metadata":   { "currency": "USD" }        // optional
    }

    ── RESPONSE JSON ────────────────────────────────────────
    {
      "session_id":       "sess_abc123",
      "episode_id":       "ep_20250115_143022_sess_abc",
      "final_answer":     "15% of 2400 is 360.",
      "is_complete":      true,
      "plan": [
        { "step_id": "step_001", "description": "Calculate 15% of 2400",
          "tool": "calculator", "status": "done", "result": "360.0" }
      ],
      "tool_calls": [
        { "tool_name": "calculator", "tool_input": { "expression": "2400*0.15" },
          "tool_output": "360.0", "success": true, "error": null,
          "timestamp": "2025-01-15T14:30:22Z" }
      ],
      "reflections": [
        { "quality_score": 0.95, "issues": [], "suggestions": [],
          "approved": true, "needs_replanning": false,
          "feedback": "Answer is correct and complete." }
      ],
      "reflection_count": 1,
      "errors":           [],
      "started_at":       "2025-01-15T14:30:20Z",
      "completed_at":     "2025-01-15T14:30:24Z",
      "duration_ms":      4231.5
    }

    ── REACT.JS USAGE ───────────────────────────────────────
    // Basic hook:
    const useAgent = () => {
      const [result, setResult] = useState(null);
      const [loading, setLoading] = useState(false);
      const [error,   setError]   = useState(null);

      const run = async (query, sessionId, metadata = {}) => {
        setLoading(true);
        setError(null);
        try {
          const res = await fetch('/run', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({ query, session_id: sessionId, metadata }),
          });
          if (!res.ok) throw new Error(await res.text());
          const data = await res.json();
          setResult(data);
          return data;
        } catch (err) {
          setError(err.message);
        } finally {
          setLoading(false);
        }
      };
      return { result, loading, error, run };
    };

    // Usage in component:
    const { result, loading, run } = useAgent();
    <button onClick={() => run("Analyze TX001", sessionId, { amount: 9800 })}>
      {loading ? 'Thinking...' : 'Ask'}
    </button>
    {result && <Answer text={result.final_answer} score={result.reflections[0]?.quality_score} />}

    ── ADAPTING FOR NEW PROJECTS ─────────────────────────────
    // Fraud detection — pass transaction data in metadata:
    run("Is this transaction suspicious?", sid, {
      amount: 9800, country: "NG", account_age_days: 2
    });

    // Trading — pass market context in metadata:
    run("Should we buy AAPL?", sid, {
      ticker: "AAPL", rsi: 35, volume_ratio: 1.8
    });

    // HR — pass candidate profile in metadata:
    run("Evaluate this candidate", sid, {
      candidate_id: "C042", role: "senior_engineer", years_exp: 7
    });
    """
    t_start = datetime.datetime.utcnow()
    try:
        final, session_id = await _run_agent(request)
        episode_id        = save_episode_after_run(final)
        t_end             = datetime.datetime.utcnow()
        duration_ms       = (t_end - t_start).total_seconds() * 1000

        plan_items = [
            StepResult(
                step_id     = s.get("step_id", "?"),
                description = s.get("description", ""),
                tool        = s.get("tool"),
                status      = s.get("status", "?"),
                result      = str(s.get("result", ""))[:500] if s.get("result") else None,
            )
            for s in (final.get("plan") or [])
        ]
        tool_items = [
            ToolCallRecord(
                tool_name   = tc.get("tool_name", "?"),
                tool_input  = tc.get("tool_input", {}),
                tool_output = str(tc.get("tool_output", ""))[:500],
                success     = tc.get("success", False),
                error       = tc.get("error"),
                timestamp   = tc.get("timestamp", ""),
            )
            for tc in (final.get("tool_calls") or [])
        ]
        reflection_items = [
            ReflectionRecord(
                quality_score    = r.get("quality_score", 0.0),
                issues           = r.get("issues", []),
                suggestions      = r.get("suggestions", []),
                approved         = r.get("approved", False),
                needs_replanning = r.get("needs_replanning", False),
                feedback         = r.get("feedback", ""),
            )
            for r in (final.get("reflections") or [])
        ]
        return RunResponse(
            session_id        = session_id,
            episode_id        = episode_id,
            final_answer      = final.get("final_answer"),
            is_complete       = final.get("is_complete", False),
            plan              = plan_items,
            tool_calls        = tool_items,
            reflections       = reflection_items,
            reflection_count  = final.get("reflection_count", 0),
            errors            = final.get("errors", []),
            started_at        = final.get("started_at"),
            completed_at      = t_end.isoformat() + "Z",
            duration_ms       = duration_ms,
            active_model_map  = cfg.get_active_model_map(),  # V4: which model ran each agent
        )
    except Exception as e:
        log.error(f"/run failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ════════════════════════════════════════════════════════════
# ENDPOINT: GET /stream
# ════════════════════════════════════════════════════════════

@app.get("/stream")
async def stream_agent(
    query:      str           = Query(..., description="User query"),
    session_id: Optional[str] = Query(None, description="Session ID"),
):
    """
    ════════════════════════════════════════════════════════════
    GET /stream — Stream agent execution as Server-Sent Events
    ════════════════════════════════════════════════════════════

    Use this instead of POST /run when you want real-time progress
    (streaming node completions as the graph executes).

    ── QUERY PARAMS ─────────────────────────────────────────
    ?query=What+is+2%2B2&session_id=sess_abc

    ── SSE EVENT CATALOGUE ──────────────────────────────────
    Each event is: "data: <JSON>\\n\\n"

    Event 1 — started:
    { "type": "started", "session_id": "sess_abc", "timestamp": "..." }

    Event 2-N — node_complete (one per graph node execution):
    {
      "type":      "node_complete",
      "node":      "planner",          // or "executor" or "reflector"
      "timestamp": "...",
      "data": {
        "plan_steps":  3,
        "is_complete": false,
        "step_index":  1
      }
    }

    Event N+1 — final (last event):
    {
      "type":         "final",
      "session_id":   "sess_abc",
      "episode_id":   "ep_20250115_...",
      "final_answer": "The answer is 42.",
      "is_complete":  true,
      "duration_ms":  3241.5,
      "timestamp":    "..."
    }

    Error event (on failure):
    { "type": "error", "error": "Timeout: agent took too long" }

    ── REACT.JS — EventSource (simple) ──────────────────────
    const streamAgent = (query, sessionId, onEvent, onFinal) => {
      const params = new URLSearchParams({ query, session_id: sessionId });
      const es = new EventSource(`/stream?${params}`);

      es.onmessage = (e) => {
        const event = JSON.parse(e.data);
        onEvent(event);                        // update progress UI
        if (event.type === 'final') {
          onFinal(event.final_answer);         // set answer
          es.close();
        }
        if (event.type === 'error') {
          console.error(event.error);
          es.close();
        }
      };
      es.onerror = () => es.close();
      return () => es.close();                 // cleanup function
    };

    // React component:
    const [nodes, setNodes] = useState([]);
    const [answer, setAnswer] = useState('');
    const cleanup = streamAgent(
      query, sessionId,
      (event) => {
        if (event.type === 'node_complete')
          setNodes(prev => [...prev, event.node]);
      },
      (ans) => setAnswer(ans)
    );
    // Call cleanup() on unmount

    ── REACT.JS — fetch + ReadableStream (advanced) ─────────
    const res = await fetch(`/stream?query=${encodeURIComponent(q)}`);
    const reader = res.body.getReader();
    const dec = new TextDecoder();
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      const lines = dec.decode(value).split('\\n');
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const event = JSON.parse(line.slice(6));
          dispatch(agentEvent(event));
        }
      }
    }
    """
    async def event_generator() -> AsyncIterator[str]:
        sid     = session_id or f"sess_{uuid.uuid4().hex[:8]}"
        t_start = datetime.datetime.utcnow()

        def sse(data: dict) -> str:
            return f"data: {json.dumps(data)}\n\n"

        yield sse({"type": "started", "session_id": sid,
                   "timestamp": t_start.isoformat() + "Z"})

        try:
            memory_ctx = load_memory_context(query, sid)
            initial    = create_initial_state(
                user_query       = query,
                session_id       = sid,
                episodic_context = memory_ctx["episodic_context"],
                vector_context   = memory_ctx["vector_context"],
                entity_context   = memory_ctx["entity_context"],
            )
            graph = get_graph()
            loop  = asyncio.get_event_loop()
            queue = asyncio.Queue()

            def _stream_thread():
                try:
                    for chunk in graph.stream(initial):
                        for node_name, update in chunk.items():
                            loop.call_soon_threadsafe(
                                queue.put_nowait, {"node": node_name, "update": update}
                            )
                    loop.call_soon_threadsafe(queue.put_nowait, None)
                except Exception as exc:
                    loop.call_soon_threadsafe(queue.put_nowait, {"error": str(exc)})

            threading.Thread(target=_stream_thread, daemon=True).start()

            tracked = initial.copy()
            while True:
                item = await asyncio.wait_for(queue.get(), timeout=120.0)
                if item is None:
                    break
                if "error" in item:
                    yield sse({"type": "error", "error": item["error"]})
                    return

                node_name = item["node"]
                for k, v in item["update"].items():
                    if isinstance(v, list) and isinstance(tracked.get(k), list):
                        tracked[k] = tracked[k] + v
                    else:
                        tracked[k] = v

                yield sse({
                    "type":      "node_complete",
                    "node":      node_name,
                    "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
                    "data": {
                        "plan_steps":  len(tracked.get("plan", [])),
                        "is_complete": tracked.get("is_complete", False),
                        "step_index":  tracked.get("current_step_index", 0),
                    }
                })
                await asyncio.sleep(0)

            episode_id = save_episode_after_run(tracked)
            t_end      = datetime.datetime.utcnow()
            yield sse({
                "type":         "final",
                "session_id":   sid,
                "episode_id":   episode_id,
                "final_answer": tracked.get("final_answer", ""),
                "is_complete":  tracked.get("is_complete", False),
                "duration_ms":  (t_end - t_start).total_seconds() * 1000,
                "timestamp":    t_end.isoformat() + "Z",
            })
        except asyncio.TimeoutError:
            yield sse({"type": "error", "error": "Timeout: agent exceeded 120s"})
        except Exception as exc:
            log.error(f"/stream error: {exc}", exc_info=True)
            yield sse({"type": "error", "error": str(exc)})

    return StreamingResponse(
        event_generator(),
        media_type = "text/event-stream",
        headers    = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ════════════════════════════════════════════════════════════
# ENDPOINT: GET /health
# ════════════════════════════════════════════════════════════

@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """
    ════════════════════════════════════════════════════════════
    GET /health — System health and configuration summary
    ════════════════════════════════════════════════════════════

    ── RESPONSE JSON ────────────────────────────────────────
    {
      "status":       "ok",
      "timestamp":    "2025-01-15T14:30:00Z",
      "skills_count": 3,
      "graph_ready":  true,
      "config": {
        "project":              "FraudGuard",
        "version":              "1.0.0",
        "provider":             "groq",
        "max_iterations":       10,
        "max_reflection_loops": 3,
        "temperatures":         { "planner": 0.3, "executor": 0.1, "reflector": 0.2 },
        "db_url":               "postgresql://user:***@host:5432/frauddb",
        "groq_key_count":       4,
        "groq_key_stats": [
          { "key_index": 0, "calls": 42, "errors": 1, "key_tail": "...abc1" }
        ]
      }
    }

    ── REACT.JS USAGE ───────────────────────────────────────
    // Startup check:
    const { status, config, skills_count } = await fetch('/health').then(r => r.json());
    if (status !== 'ok') showAlert('Agent offline');

    // Display key rotation stats:
    config.groq_key_stats?.map(k => (
      <KeyRow key={k.key_index}
        index={k.key_index} calls={k.calls} errors={k.errors} />
    ))
    """
    try:
        registry = get_registry()
        graph_ok = get_graph() is not None
        return HealthResponse(
            status       = "ok",
            timestamp    = datetime.datetime.utcnow().isoformat() + "Z",
            config       = cfg.summary(),
            skills_count = len(registry),
            graph_ready  = graph_ok,
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


# ════════════════════════════════════════════════════════════
# ENDPOINT: GET /skills
# ════════════════════════════════════════════════════════════

@app.get("/skills")
async def list_skills():
    """
    ════════════════════════════════════════════════════════════
    GET /skills — List all loaded skills (Python + Markdown)
    ════════════════════════════════════════════════════════════

    ── RESPONSE JSON ────────────────────────────────────────
    [
      { "name": "fraud_risk_scorer", "description": "Scores fraud risk.",
        "version": "1.0.0", "file": ".../skills/fraud_risk_scorer.py" },
      { "name": "fraud_playbook", "description": "Fraud investigation guide.",
        "version": "md", "file": ".../skills/md_skills/fraud_playbook.md" }
    ]

    ── REACT.JS USAGE ───────────────────────────────────────
    const skills = await fetch('/skills').then(r => r.json());
    skills.map(s => <SkillBadge key={s.name} name={s.name} desc={s.description} />)
    """
    return get_registry().list_skills()


# ════════════════════════════════════════════════════════════
# ENDPOINT: POST /skills/reload
# ════════════════════════════════════════════════════════════

@app.post("/skills/reload")
async def reload_all_skills():
    """
    ════════════════════════════════════════════════════════════
    POST /skills/reload — Hot-reload all skills (no restart)
    ════════════════════════════════════════════════════════════

    Drop a new .py or .md file into /skills/ then call this endpoint.
    The server picks it up immediately without restarting.

    ── RESPONSE JSON ────────────────────────────────────────
    { "status": "ok", "skills_loaded": 3, "skill_names": ["fraud_risk_scorer", ...] }

    ── REACT.JS USAGE ───────────────────────────────────────
    const reload = async () => {
      const res = await fetch('/skills/reload', { method: 'POST' });
      const data = await res.json();
      setSkillCount(data.skills_loaded);
      toast(`Loaded ${data.skills_loaded} skills`);
    };
    """
    from skill_loader import skill_registry
    registry = reload_skills(skill_registry or get_registry())
    return {"status": "ok", "skills_loaded": len(registry), "skill_names": registry.names}


# ════════════════════════════════════════════════════════════
# ENDPOINT: GET /models  (V4 new)
# ════════════════════════════════════════════════════════════

@app.get("/models")
async def list_models(
    role:       Optional[str]   = Query(None,  description="Filter: planner|executor|reflector|vision_tool"),
    max_ram_gb: Optional[float] = Query(None,  description="Max RAM in GB (e.g. 4.0)"),
    provider:   str             = Query("ollama", description="'ollama' (only option for now)"),
):
    """
    ════════════════════════════════════════════════════════════
    GET /models — List all models in the registry
    ════════════════════════════════════════════════════════════

    Returns every model in OLLAMA_MODEL_REGISTRY with its
    metadata: RAM requirements, speed, quality, best use cases,
    and the exact ollama pull command.

    ── QUERY PARAMS ─────────────────────────────────────────
    ?role=planner                  → models best for Planner
    ?role=executor                 → models best for Executor
    ?role=reflector                → models best for Reflector
    ?max_ram_gb=4.0                → models needing ≤ 4 GB RAM
    ?role=executor&max_ram_gb=3.0  → combine filters

    ── RESPONSE JSON ────────────────────────────────────────
    [
      {
        "name":       "qwen2.5-coder:3b",
        "label":      "Qwen2.5-Coder 3B",
        "params":     "3B",
        "ram_gb":     2.3,
        "speed":      "fast",
        "quality":    "great",
        "strengths":  ["code", "structured JSON", "tool calling"],
        "best_for":   ["planner", "executor"],
        "pull_cmd":   "ollama pull qwen2.5-coder:3b",
        "notes":      "Best-in-class for structured output..."
      },
      { "name": "granite3.1-moe:3b", ... },
      { "name": "nemotron-mini", ... }
    ]

    ── REACT.JS USAGE ───────────────────────────────────────
    // Fetch all models:
    const models = await fetch('/models').then(r => r.json());

    // Fetch only Executor-suitable models ≤ 4 GB:
    const models = await fetch('/models?role=executor&max_ram_gb=4').then(r => r.json());

    // TypeScript interface:
    interface ModelInfo {
      name:      string;    // Ollama tag — use in model_map
      label:     string;    // Display name
      params:    string;    // "1.5B", "3B", etc.
      ram_gb:    number;    // RAM required
      speed:     string;    // "ultra-fast" | "fast" | "medium" | "slow"
      quality:   string;    // "basic" | "good" | "great" | "excellent"
      strengths: string[];
      best_for:  string[];  // ["planner", "executor", "reflector"]
      pull_cmd:  string;    // "ollama pull <n>"
      notes:     string;
    }

    // Model picker component:
    const ModelPicker = ({ role, onSelect }) => {
      const [models, setModels] = useState([]);
      useEffect(() => {
        fetch(`/models?role=${role}`).then(r => r.json()).then(setModels);
      }, [role]);
      return (
        <select onChange={e => onSelect(e.target.value)}>
          {models.map(m => (
            <option key={m.name} value={m.name}>
              {m.label} ({m.params}, {m.ram_gb}GB, {m.speed})
            </option>
          ))}
        </select>
      );
    };

    // Multi-model run (use selected models in POST /run):
    const runMultiModel = async (query, plannerModel, executorModel) => {
      const res = await fetch('/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query,
          model_map: {
            planner:   plannerModel,   // e.g. "qwen2.5-coder:3b"
            executor:  executorModel,  // e.g. "granite3.1-moe:3b"
            reflector: "nemotron-mini"
          }
        })
      });
      const data = await res.json();
      console.log('Used models:', data.active_model_map);
    };

    ── CURRENT ACTIVE CONFIG ─────────────────────────────────
    To see which models are currently active for each agent,
    check GET /health → config.active_agent_models
    """
    from config import list_model_registry
    models = list_model_registry(
        filter_best_for = role,
        max_ram_gb      = max_ram_gb,
    )
    return {
        "models":       models,
        "total":        len(models),
        "active_config": cfg.get_active_model_map(),
        "tip": "Use model 'name' field in POST /run → model_map to run with specific models.",
    }


# ════════════════════════════════════════════════════════════
# ENDPOINT: GET /memory/episodic
# ════════════════════════════════════════════════════════════

@app.get("/memory/episodic")
async def get_episodic_memory(
    n:          int           = Query(default=5, ge=1, le=50),
    session_id: Optional[str] = Query(None),
):
    """
    ════════════════════════════════════════════════════════════
    GET /memory/episodic — Retrieve recent agent run episodes
    ════════════════════════════════════════════════════════════

    ── QUERY PARAMS ─────────────────────────────────────────
    ?n=5                         → last 5 episodes (default)
    ?n=10&session_id=sess_abc    → last 10 for one session

    ── RESPONSE JSON ────────────────────────────────────────
    [
      {
        "episode_id":       "ep_20250115_143022_sess_abc",
        "timestamp":        "2025-01-15T14:30:22Z",
        "session_id":       "sess_abc",
        "user_query":       "What is 15% of 2400?",
        "final_answer":     "15% of 2400 is 360.",
        "is_complete":      true,
        "reflection_count": 1
      }
    ]

    ── REACT.JS USAGE ───────────────────────────────────────
    const history = await fetch('/memory/episodic?n=10').then(r => r.json());
    <SessionHistory items={history.map(ep => ({
      id:     ep.episode_id,
      query:  ep.user_query,
      answer: ep.final_answer,
      date:   new Date(ep.timestamp).toLocaleString()
    }))} />
    """
    from memory.episodic_store import EpisodicStore
    store = EpisodicStore()
    if session_id:
        return store.get_by_session(session_id)[-n:]
    return store.get_recent(n)


# ════════════════════════════════════════════════════════════
# ENDPOINT: GET /memory/entities
# ════════════════════════════════════════════════════════════

@app.get("/memory/entities")
async def get_entity_memory():
    """
    ════════════════════════════════════════════════════════════
    GET /memory/entities — Get all entity memory entries
    ════════════════════════════════════════════════════════════

    ── RESPONSE JSON ────────────────────────────────────────
    {
      "user_alice": { "risk_score": 0.85, "flags": ["wire_fraud"] },
      "AAPL":       { "price": 195.2, "signal": "buy" },
      "preferences":{ "theme": "dark", "lang": "en" }
    }

    ── REACT.JS USAGE ───────────────────────────────────────
    const entities = await fetch('/memory/entities').then(r => r.json());
    Object.entries(entities).map(([name, data]) => (
      <EntityCard key={name} name={name} data={JSON.stringify(data, null, 2)} />
    ))
    """
    from memory.entity_memory import EntityMemory
    return EntityMemory().load_all()


# ════════════════════════════════════════════════════════════
# ENDPOINT: DELETE /memory/entity/{name}
# ════════════════════════════════════════════════════════════

@app.delete("/memory/entity/{name}")
async def delete_entity(name: str):
    """
    ════════════════════════════════════════════════════════════
    DELETE /memory/entity/{name} — Remove an entity from memory
    ════════════════════════════════════════════════════════════

    ── RESPONSE JSON ────────────────────────────────────────
    { "deleted": true, "name": "user_alice" }

    ── REACT.JS USAGE ───────────────────────────────────────
    const deleteEntity = async (name) => {
      await fetch(`/memory/entity/${encodeURIComponent(name)}`, { method: 'DELETE' });
      setEntities(prev => { const e = {...prev}; delete e[name]; return e; });
    };
    """
    from memory.entity_memory import EntityMemory
    deleted = EntityMemory().delete(name)
    return {"deleted": deleted, "name": name}


# ════════════════════════════════════════════════════════════
# ENDPOINT: POST /memory/vector/search
# ════════════════════════════════════════════════════════════

@app.post("/memory/vector/search")
async def vector_search(request: VectorSearchRequest):
    """
    ════════════════════════════════════════════════════════════
    POST /memory/vector/search — Semantic search in vector memory
    ════════════════════════════════════════════════════════════

    ── REQUEST JSON ─────────────────────────────────────────
    { "query": "wire fraud offshore transfer", "top_k": 5 }

    ── RESPONSE JSON ────────────────────────────────────────
    [
      {
        "text":     "Transaction T001: $9800 to offshore flagged",
        "metadata": { "type": "transaction", "id": "T001" },
        "score":    0.23
      }
    ]

    Lower score = more similar (L2 distance).

    ── REACT.JS USAGE ───────────────────────────────────────
    const search = async (query) => {
      const res = await fetch('/memory/vector/search', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ query, top_k: 5 }),
      });
      const results = await res.json();
      setSearchResults(results);
    };
    <SearchResults items={searchResults.map(r => ({
      text:  r.text,
      score: r.score.toFixed(3),
    }))} />
    """
    try:
        from memory.vector_store import VectorMemoryStore
        return VectorMemoryStore().search(request.query, top_k=request.top_k)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ════════════════════════════════════════════════════════════
# ENDPOINT: POST /memory/vector/add
# ════════════════════════════════════════════════════════════

@app.post("/memory/vector/add")
async def vector_add(request: VectorAddRequest):
    """
    ════════════════════════════════════════════════════════════
    POST /memory/vector/add — Seed domain knowledge into memory
    ════════════════════════════════════════════════════════════

    Use this at startup (or via an admin panel) to pre-load
    domain-specific facts into the RAG vector store.

    ── REQUEST JSON ─────────────────────────────────────────
    {
      "texts": [
        "Transaction T001: $9800 wire to offshore. Flagged.",
        "User U42: 3 prior fraud flags on account."
      ],
      "metadatas": [
        { "type": "transaction", "id": "T001" },
        { "type": "user_flag",   "user": "U42" }
      ]
    }

    ── RESPONSE JSON ────────────────────────────────────────
    { "status": "ok", "added": 2, "total_vectors": 158 }

    ── REACT.JS USAGE (admin panel) ─────────────────────────
    const seedKnowledge = async (texts) => {
      const res = await fetch('/memory/vector/add', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ texts }),
      });
      const { added, total_vectors } = await res.json();
      toast(`Added ${added} entries. Total: ${total_vectors}`);
    };
    """
    try:
        from memory.vector_store import VectorMemoryStore
        vs  = VectorMemoryStore()
        ids = vs.add_texts(request.texts, request.metadatas)
        return {"status": "ok", "added": len(ids), "total_vectors": vs.size}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ════════════════════════════════════════════════════════════
# ENDPOINT: GET /logs
# ════════════════════════════════════════════════════════════

@app.get("/logs")
async def get_logs(
    date:   Optional[str] = Query(None, description="YYYY-MM-DD (default: today)"),
    format: str           = Query(default="json", description="'json' or 'md'"),
    type:   str           = Query(default="llm",  description="'llm' or 'graph_events'"),
):
    """
    ════════════════════════════════════════════════════════════
    GET /logs — Retrieve log files for debugging / audit
    ════════════════════════════════════════════════════════════

    ── QUERY PARAMS ─────────────────────────────────────────
    ?format=md                    → today's Markdown LLM log
    ?format=json                  → today's JSONL LLM log
    ?date=2025-01-15&format=md    → specific date, MD format
    ?type=graph_events            → graph routing event log

    ── REACT.JS — Markdown log viewer ───────────────────────
    const today = new Date().toISOString().split('T')[0];
    const md = await fetch(`/logs?date=${today}&format=md`).then(r => r.text());
    // Render with react-markdown:
    <ReactMarkdown>{md}</ReactMarkdown>

    ── REACT.JS — JSONL log parser ──────────────────────────
    const jsonl = await fetch(`/logs?date=${today}&format=json`).then(r => r.text());
    const entries = jsonl.split('\\n').filter(Boolean).map(JSON.parse);
    entries.map(e => <LogEntry key={e.log_id} agent={e.agent}
                                latency={e.latency_ms} ts={e.timestamp} />)
    """
    import aiofiles
    if date is None:
        date = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    if format == "md":
        log_file = cfg.LOG_MD_DIR / f"{date}.md"
    else:
        prefix   = "graph_events_" if type == "graph_events" else ""
        log_file = cfg.LOG_JSON_DIR / f"{prefix}{date}.jsonl"

    if not log_file.exists():
        raise HTTPException(status_code=404, detail=f"No log for date={date} type={type}")

    async with aiofiles.open(log_file, "r", encoding="utf-8") as f:
        content = await f.read()

    media_type = "text/markdown" if format == "md" else "application/x-ndjson"
    return StreamingResponse(iter([content]), media_type=media_type)


# ════════════════════════════════════════════════════════════
# DEV ENTRY POINT
# ════════════════════════════════════════════════════════════

if __name__ == "__main__":
    uvicorn.run(
        "server:app",
        host      = cfg.SERVER_HOST,
        port      = cfg.SERVER_PORT,
        reload    = True,
        log_level = cfg.LOG_LEVEL.lower(),
    )
