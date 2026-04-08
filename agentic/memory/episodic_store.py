# ============================================================
# memory/episodic_store.py — Episodic Memory (JSONL)
# ============================================================
# PURPOSE:
#   Stores and retrieves episodic memories — records of past
#   agent runs, decisions, and outcomes. Acts as a long-term
#   data warehouse of all agent activity.
#
# STORAGE:
#   JSON: memory/json/episodic.jsonl — one JSON object per line
#   MD:   memory/md/episodic_summary.md — human-readable log
#
# EPISODIC MEMORY STRUCTURE:
#   Each episode is a snapshot of a completed agent run with:
#   - session_id, timestamp, user_query
#   - full plan, tool calls, reflections
#   - final_answer, success status
#   - thinking traces
#
# USE IN PROMPTS:
#   Retrieved episodes are injected as context so agents can
#   learn from past runs ("Last time we tried X, it failed because...")
# ============================================================

import json
import datetime
from pathlib import Path
from typing import Any, Optional

from config import cfg
from logger import get_logger

log = get_logger("episodic_store")


class EpisodicStore:
    """
    Append-only JSONL store for agent run episodes.

    Thread Safety:
        File writes use line-by-line appends (atomic on most
        POSIX systems for small writes). For high concurrency,
        add a threading.Lock.

    Usage:
        store = EpisodicStore()
        store.save_episode(state)
        episodes = store.get_recent(n=5)
    """

    def __init__(
        self,
        json_path: Optional[Path] = None,
        md_path:   Optional[Path] = None,
    ):
        self.json_path = json_path or cfg.EPISODIC_FILE
        self.md_path   = md_path   or (cfg.ENTITY_DIR / "episodic_summary.md")
        self.json_path.parent.mkdir(parents=True, exist_ok=True)
        self.md_path.parent.mkdir(parents=True, exist_ok=True)

    def save_episode(self, state: dict) -> str:
        """
        Persist a completed agent run as an episode.

        Args:
            state: The final AgentState dict after graph execution

        Returns:
            episode_id (str)

        Example:
            episode_id = store.save_episode(final_state)
        """
        episode_id = (
            f"ep_{datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_"
            f"{(state.get('session_id') or 'nosess')[:8]}"
        )

        episode = {
            "episode_id":      episode_id,
            "timestamp":       datetime.datetime.utcnow().isoformat() + "Z",
            "session_id":      state.get("session_id"),
            "user_query":      state.get("user_query"),
            "plan":            state.get("plan", []),
            "tool_calls":      state.get("tool_calls", []),
            "reflections":     state.get("reflections", []),
            "final_answer":    state.get("final_answer"),
            "is_complete":     state.get("is_complete", False),
            "errors":          state.get("errors", []),
            "thinking_traces": state.get("thinking_traces", []),
            "started_at":      state.get("started_at"),
            "reflection_count":state.get("reflection_count", 0),
        }

        # ── Write JSON ───────────────────────────────────
        with open(self.json_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(episode, ensure_ascii=False) + "\n")

        # ── Write MD summary ─────────────────────────────
        self._append_md_summary(episode)

        log.info(f"Episode saved: {episode_id}")
        return episode_id

    def _append_md_summary(self, episode: dict):
        """Append a human-readable summary to the MD file."""
        ts        = episode["timestamp"]
        query     = episode.get("user_query", "—")
        answer    = (episode.get("final_answer") or "—")[:200]
        errors    = episode.get("errors", [])
        n_tools   = len(episode.get("tool_calls", []))
        n_steps   = len(episode.get("plan", []))
        success   = "✅" if episode.get("is_complete") else "❌"

        lines = [
            f"\n## {success} Episode `{episode['episode_id']}`",
            f"**Time:** {ts}  |  **Session:** {episode.get('session_id', '—')}",
            "",
            f"**Query:** {query}",
            "",
            f"**Steps Planned:** {n_steps}  |  **Tools Called:** {n_tools}  "
            f"|  **Reflections:** {episode.get('reflection_count', 0)}",
            "",
            f"**Final Answer:**",
            f"> {answer}",
            "",
        ]
        if errors:
            lines.append(f"**Errors:** {'; '.join(errors[:3])}")
            lines.append("")
        lines.append("---")

        with open(self.md_path, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

    def get_recent(self, n: int = 5) -> list[dict]:
        """
        Return the N most recent episodes.

        Args:
            n: Number of episodes to return (default 5)

        Returns:
            List of episode dicts, newest last

        Usage:
            recent = store.get_recent(3)
            for ep in recent:
                print(ep["user_query"], ep["final_answer"])
        """
        if not self.json_path.exists():
            return []

        episodes = []
        with open(self.json_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        episodes.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

        return episodes[-n:] if len(episodes) > n else episodes

    def get_by_session(self, session_id: str) -> list[dict]:
        """
        Return all episodes for a given session ID.

        Args:
            session_id: The session identifier

        Returns:
            List of matching episode dicts
        """
        if not self.json_path.exists():
            return []

        matches = []
        with open(self.json_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        ep = json.loads(line)
                        if ep.get("session_id") == session_id:
                            matches.append(ep)
                    except json.JSONDecodeError:
                        continue
        return matches

    def search_by_query(self, keyword: str, limit: int = 10) -> list[dict]:
        """
        Simple keyword search across episode queries.

        Args:
            keyword: Keyword to search for (case-insensitive)
            limit:   Max results

        Returns:
            List of matching episodes

        Note:
            For semantic search use VectorMemoryStore instead.
        """
        if not self.json_path.exists():
            return []

        kw      = keyword.lower()
        results = []
        with open(self.json_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        ep = json.loads(line)
                        if kw in (ep.get("user_query") or "").lower():
                            results.append(ep)
                            if len(results) >= limit:
                                break
                    except json.JSONDecodeError:
                        continue
        return results

    def format_for_prompt(self, episodes: list[dict]) -> str:
        """
        Format episodes as a context block for LLM prompts.

        Args:
            episodes: List of episode dicts

        Returns:
            Formatted string ready to inject into a prompt

        Example output:
            === Past Episode (2025-01-15) ===
            Query: Analyze transaction TX001
            Outcome: SUCCESS
            Answer: The transaction is flagged as high-risk...
        """
        if not episodes:
            return "No relevant past episodes found."

        lines = []
        for ep in episodes:
            status = "SUCCESS" if ep.get("is_complete") else "INCOMPLETE"
            answer = (ep.get("final_answer") or "No answer")[:300]
            lines.append(
                f"=== Past Episode ({ep.get('timestamp', '?')[:10]}) ===\n"
                f"Query: {ep.get('user_query', '?')}\n"
                f"Outcome: {status}\n"
                f"Answer: {answer}\n"
            )
        return "\n".join(lines)

    def count(self) -> int:
        """Return total number of stored episodes."""
        if not self.json_path.exists():
            return 0
        count = 0
        with open(self.json_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    count += 1
        return count
