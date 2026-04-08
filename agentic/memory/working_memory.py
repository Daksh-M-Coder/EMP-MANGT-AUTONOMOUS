# ============================================================
# memory/working_memory.py — Working Memory
# ============================================================
# PURPOSE:
#   Manages short-term "working memory" within a single agent
#   run. Lives in the AgentState and is cleared between runs.
#   Provides scratch space for intermediate reasoning.
#
# ANALOGY:
#   - Episodic memory = long-term memory (JSONL files)
#   - Vector memory   = semantic memory (FAISS index)
#   - Entity memory   = declarative facts (.md/.json files)
#   - Working memory  = RAM / scratch pad (in AgentState dict)
#
# USE CASES:
#   - Store intermediate computation results
#   - Pass context between planning steps
#   - Track sub-task progress
#   - Buffer data between tool calls
# ============================================================

import datetime
from typing import Any, Optional

from logger import get_logger

log = get_logger("working_memory")


class WorkingMemory:
    """
    Lightweight in-memory key-value store for a single agent run.

    Wraps the 'working_memory' dict in AgentState so agents
    have a clean API for scratch-pad operations.

    Usage:
        wm = WorkingMemory(state["working_memory"])
        wm.set("transaction_amount", 5000)
        amount = wm.get("transaction_amount")
        wm.append_to_list("flagged_items", "T001")
    """

    def __init__(self, storage: Optional[dict] = None):
        """
        Args:
            storage: Reference to state["working_memory"] dict.
                     Pass None to create an isolated instance.
        """
        self._store: dict = storage if storage is not None else {}

    def set(self, key: str, value: Any) -> None:
        """
        Store a value under a key.

        Args:
            key:   String key
            value: Any JSON-serializable value

        Example:
            wm.set("current_risk_score", 0.87)
            wm.set("analysis_context", {"sector": "banking"})
        """
        self._store[key] = {
            "value":     value,
            "set_at":    datetime.datetime.utcnow().isoformat() + "Z",
        }

    def get(self, key: str, default: Any = None) -> Any:
        """
        Retrieve a value by key.

        Args:
            key:     String key
            default: Value to return if key not found

        Returns:
            The stored value, or default

        Example:
            score = wm.get("current_risk_score", 0.0)
        """
        entry = self._store.get(key)
        if entry is None:
            return default
        return entry.get("value", default)

    def append_to_list(self, key: str, item: Any) -> None:
        """
        Append an item to a list stored under key.
        Creates the list if it doesn't exist.

        Args:
            key:  String key
            item: Item to append

        Example:
            wm.append_to_list("flagged_ids", "TX_001")
            wm.append_to_list("flagged_ids", "TX_042")
            # wm.get("flagged_ids") -> ["TX_001", "TX_042"]
        """
        current = self.get(key, [])
        if not isinstance(current, list):
            current = [current]
        current.append(item)
        self.set(key, current)

    def increment(self, key: str, amount: float = 1) -> float:
        """
        Increment a numeric counter.

        Args:
            key:    String key
            amount: Amount to add (default 1)

        Returns:
            New value

        Example:
            wm.increment("api_call_count")
            wm.increment("total_cost", 0.002)
        """
        current = self.get(key, 0)
        new_val = current + amount
        self.set(key, new_val)
        return new_val

    def delete(self, key: str) -> bool:
        """
        Remove a key from working memory.

        Returns:
            True if deleted, False if not found
        """
        if key in self._store:
            del self._store[key]
            return True
        return False

    def clear(self) -> None:
        """Clear all working memory."""
        self._store.clear()

    def keys(self) -> list[str]:
        """Return all stored keys."""
        return list(self._store.keys())

    def snapshot(self) -> dict:
        """
        Return a clean snapshot of all current values (without metadata).

        Returns:
            Dict mapping key -> value

        Usage:
            snap = wm.snapshot()
            # inject into prompt as JSON context
        """
        return {k: v.get("value") for k, v in self._store.items()}

    def format_for_prompt(self) -> str:
        """
        Format working memory as a context block for LLM prompts.

        Returns:
            Formatted string suitable for prompt injection

        Example output:
            === Working Memory ===
            current_risk_score: 0.87
            flagged_ids: ["TX_001", "TX_042"]
            api_call_count: 3
        """
        snap = self.snapshot()
        if not snap:
            return "Working memory is empty."

        lines = ["=== Working Memory ==="]
        for k, v in snap.items():
            lines.append(f"  {k}: {v}")
        return "\n".join(lines)

    def update_from_state(self, state_dict: dict) -> None:
        """
        Sync working memory from a graph state dict.
        Called when a node receives a new state snapshot.

        Args:
            state_dict: The 'working_memory' field from AgentState
        """
        if isinstance(state_dict, dict):
            self._store.update(state_dict)

    def to_state_dict(self) -> dict:
        """
        Export working memory for storage in AgentState.

        Returns:
            The internal _store dict (reference, not copy)
        """
        return self._store

    def __contains__(self, key: str) -> bool:
        return key in self._store

    def __len__(self) -> int:
        return len(self._store)

    def __repr__(self) -> str:
        return f"WorkingMemory({len(self._store)} keys: {list(self._store.keys())})"
