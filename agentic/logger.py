# ============================================================
# logger.py — Structured Logging Utility
# ============================================================
# PURPOSE:
#   Provides a unified logging interface for all modules.
#   Writes to both JSON and Markdown log files in
#   ai-req-res-logging/json/ and ai-req-res-logging/md/
#
# USAGE:
#   from logger import get_logger, log_llm_call
#   log = get_logger("planner")
#   log.info("Planner started")
#   log_llm_call(agent="planner", prompt=..., response=...)
# ============================================================

import json
import datetime
import logging
import uuid
from pathlib import Path
from typing import Any, Optional

from config import LOG_JSON_DIR, LOG_MD_DIR


# ── Standard Python Logger ───────────────────────────────
def get_logger(name: str) -> logging.Logger:
    """
    Get a named logger with consistent formatting.

    Args:
        name: Logger name (e.g., "planner", "executor")

    Returns:
        A configured Python logger

    Usage:
        log = get_logger("my_module")
        log.info("Starting process")
        log.error("Something failed", exc_info=True)
    """
    logger = logging.getLogger(f"agentic.{name}")

    if not logger.handlers:
        handler   = logging.StreamHandler()
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        logger.propagate = False

    return logger


# ── LLM Call Logger ──────────────────────────────────────
def log_llm_call(
    agent:         str,
    prompt:        str | list,
    response:      str,
    metadata:      Optional[dict] = None,
    thinking:      Optional[str]  = None,
    parsed_output: Optional[Any]  = None,
    session_id:    Optional[str]  = None,
    provider:      Optional[str]  = None,
    model:         Optional[str]  = None,
    latency_ms:    Optional[float]= None,
) -> str:
    """
    Log a complete LLM call to both JSON and Markdown files.

    Args:
        agent:         "planner" | "executor" | "reflector"
        prompt:        Full prompt string or list of messages
        response:      Raw LLM response text
        metadata:      Extra key-value metadata
        thinking:      Agent's internal reasoning/thinking
        parsed_output: Structured output parsed from response
        session_id:    Session identifier
        provider:      "groq" | "ollama"
        model:         Model name used
        latency_ms:    Response latency in milliseconds

    Returns:
        The log entry ID (UUID)

    Example:
        log_llm_call(
            agent="planner",
            prompt="Plan the following task: ...",
            response="Step 1: ...",
            latency_ms=342.5
        )
    """
    log_id    = str(uuid.uuid4())[:8]
    timestamp = datetime.datetime.utcnow().isoformat() + "Z"
    date_str  = datetime.datetime.utcnow().strftime("%Y-%m-%d")

    # ── JSON Log ─────────────────────────────────────────
    json_entry = {
        "log_id":        log_id,
        "timestamp":     timestamp,
        "agent":         agent,
        "session_id":    session_id,
        "provider":      provider,
        "model":         model,
        "latency_ms":    latency_ms,
        "prompt":        prompt,
        "response":      response,
        "thinking":      thinking,
        "parsed_output": parsed_output,
        "metadata":      metadata or {},
    }

    json_file = LOG_JSON_DIR / f"{date_str}.jsonl"
    with open(json_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(json_entry, ensure_ascii=False) + "\n")

    # ── Markdown Log ─────────────────────────────────────
    md_lines = [
        f"## 🤖 LLM Call `{log_id}` — {agent.upper()}",
        "",
        f"| Field | Value |",
        f"|-------|-------|",
        f"| **Timestamp** | `{timestamp}` |",
        f"| **Agent** | `{agent}` |",
        f"| **Provider** | `{provider or 'unknown'}` |",
        f"| **Model** | `{model or 'unknown'}` |",
        f"| **Session** | `{session_id or 'none'}` |",
        f"| **Latency** | `{latency_ms:.1f} ms` |" if latency_ms else "| **Latency** | `unknown` |",
        "",
        "### 📥 Prompt",
        "```",
        (prompt if isinstance(prompt, str) else json.dumps(prompt, indent=2)),
        "```",
        "",
    ]

    if thinking:
        md_lines += [
            "### 💭 Thinking / Reasoning",
            "```",
            thinking,
            "```",
            "",
        ]

    md_lines += [
        "### 📤 Raw Response",
        "```",
        response,
        "```",
        "",
    ]

    if parsed_output:
        md_lines += [
            "### ✅ Parsed Output",
            "```json",
            json.dumps(parsed_output, indent=2, ensure_ascii=False),
            "```",
            "",
        ]

    if metadata:
        md_lines += [
            "### 🏷️ Metadata",
            "```json",
            json.dumps(metadata, indent=2, ensure_ascii=False),
            "```",
            "",
        ]

    md_lines.append("---\n")

    md_file = LOG_MD_DIR / f"{date_str}.md"
    with open(md_file, "a", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    return log_id


def log_graph_event(
    event_type: str,
    node:       str,
    data:       dict,
    session_id: Optional[str] = None,
):
    """
    Log a graph-level event (node entry, state transition, error).

    Args:
        event_type: "node_enter" | "node_exit" | "edge" | "error"
        node:       Node name
        data:       Event payload
        session_id: Session identifier
    """
    timestamp = datetime.datetime.utcnow().isoformat() + "Z"
    date_str  = datetime.datetime.utcnow().strftime("%Y-%m-%d")

    entry = {
        "timestamp":  timestamp,
        "event_type": event_type,
        "node":       node,
        "session_id": session_id,
        "data":       data,
    }

    json_file = LOG_JSON_DIR / f"graph_events_{date_str}.jsonl"
    with open(json_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
