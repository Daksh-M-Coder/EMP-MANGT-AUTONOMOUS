# ============================================================
# memory/entity_memory.py — Entity Memory (.md files)
# ============================================================
# PURPOSE:
#   Stores structured knowledge about "entities" — people,
#   companies, concepts, or any domain-specific object.
#   Each entity gets its own .md file for human readability
#   and a corresponding .json for machine reading.
#
# STORAGE:
#   memory/md/<entity_name>.md   — human-readable markdown
#   memory/json/<entity_name>.json — structured JSON data
#
# DESIGN:
#   Entities are key-value stores with versioning.
#   Every update is appended (audit trail), not overwritten.
#
# EXAMPLES:
#   Fraud:      store entity "user_123" with risk_score, flags
#   HR:         store entity "candidate_alice" with resume data
#   Trading:    store entity "AAPL" with price history, signals
#   Personal:   store entity "preferences" with user settings
# ============================================================

import json
import datetime
from pathlib import Path
from typing import Any, Optional

from config import cfg
from logger import get_logger

log = get_logger("entity_memory")


class EntityMemory:
    """
    File-based entity memory store.

    Each entity is identified by a string name/key and stores
    arbitrary JSON-serializable data. Both .md (human) and
    .json (machine) representations are maintained.

    Usage:
        em = EntityMemory()
        em.set("user_alice", {"risk_score": 0.2, "flags": []})
        data = em.get("user_alice")
        em.update("user_alice", {"flags": ["suspicious_login"]})
    """

    def __init__(
        self,
        json_dir: Optional[Path] = None,
        md_dir:   Optional[Path] = None,
    ):
        self.json_dir = json_dir or cfg.MEMORY_JSON_DIR
        self.md_dir   = md_dir   or cfg.MEMORY_MD_DIR
        self.json_dir.mkdir(parents=True, exist_ok=True)
        self.md_dir.mkdir(parents=True, exist_ok=True)

    def _json_path(self, name: str) -> Path:
        safe = name.replace("/", "_").replace("\\", "_")
        return self.json_dir / f"entity_{safe}.json"

    def _md_path(self, name: str) -> Path:
        safe = name.replace("/", "_").replace("\\", "_")
        return self.md_dir / f"entity_{safe}.md"

    def set(self, name: str, data: Any, description: str = "") -> None:
        """
        Create or completely replace an entity's data.

        Args:
            name:        Entity identifier (e.g., "user_alice", "AAPL")
            data:        Any JSON-serializable data
            description: Optional human-readable description

        Example:
            em.set("user_alice", {
                "risk_score": 0.15,
                "account_age_days": 730,
                "country": "US"
            })
        """
        ts = datetime.datetime.utcnow().isoformat() + "Z"
        record = {
            "entity_name": name,
            "description": description,
            "data":        data,
            "created_at":  ts,
            "updated_at":  ts,
            "version":     1,
            "history":     [{"timestamp": ts, "data": data, "action": "create"}],
        }

        self._write_json(name, record)
        self._write_md(name, record)
        log.info(f"Entity created/replaced: '{name}'")

    def get(self, name: str) -> Optional[Any]:
        """
        Retrieve the current data for an entity.

        Args:
            name: Entity identifier

        Returns:
            The entity's data dict, or None if not found

        Example:
            alice = em.get("user_alice")
            if alice:
                print(alice["risk_score"])
        """
        json_path = self._json_path(name)
        if not json_path.exists():
            return None

        with open(json_path, "r", encoding="utf-8") as f:
            record = json.load(f)
        return record.get("data")

    def get_full_record(self, name: str) -> Optional[dict]:
        """
        Retrieve the full entity record including history.

        Args:
            name: Entity identifier

        Returns:
            Full record dict with history, or None if not found
        """
        json_path = self._json_path(name)
        if not json_path.exists():
            return None
        with open(json_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def update(self, name: str, partial_data: dict) -> bool:
        """
        Merge partial_data into the existing entity data.
        If entity doesn't exist, creates it.

        Args:
            name:         Entity identifier
            partial_data: Dict of fields to update/add

        Returns:
            True if updated existing entity, False if created new

        Example:
            em.update("user_alice", {"risk_score": 0.85, "flags": ["wire_fraud"]})
        """
        existing = self.get_full_record(name)
        ts = datetime.datetime.utcnow().isoformat() + "Z"

        if not existing:
            self.set(name, partial_data)
            return False

        # Merge
        current_data = existing.get("data", {})
        if isinstance(current_data, dict) and isinstance(partial_data, dict):
            merged = {**current_data, **partial_data}
        else:
            merged = partial_data

        existing["data"]       = merged
        existing["updated_at"] = ts
        existing["version"]    = existing.get("version", 1) + 1
        existing.setdefault("history", []).append({
            "timestamp": ts,
            "data":      partial_data,
            "action":    "update",
        })

        self._write_json(name, existing)
        self._write_md(name, existing)
        log.info(f"Entity updated: '{name}' -> v{existing['version']}")
        return True

    def delete(self, name: str) -> bool:
        """
        Delete an entity and its files.

        Args:
            name: Entity identifier

        Returns:
            True if deleted, False if not found
        """
        json_path = self._json_path(name)
        md_path   = self._md_path(name)
        deleted   = False
        if json_path.exists():
            json_path.unlink()
            deleted = True
        if md_path.exists():
            md_path.unlink()
            deleted = True
        if deleted:
            log.info(f"Entity deleted: '{name}'")
        return deleted

    def list_entities(self) -> list[str]:
        """
        Return names of all stored entities.

        Returns:
            Sorted list of entity names
        """
        return sorted(
            p.stem.removeprefix("entity_")
            for p in self.json_dir.glob("entity_*.json")
        )

    def load_all(self) -> dict[str, Any]:
        """
        Load all entity data into a single dict.

        Returns:
            Dict mapping entity_name -> data

        Usage (for prompt context):
            context = em.load_all()
            # inject context["user_alice"] into prompt
        """
        result = {}
        for name in self.list_entities():
            data = self.get(name)
            if data is not None:
                result[name] = data
        return result

    def format_for_prompt(self, names: Optional[list[str]] = None) -> str:
        """
        Format entity data as context for LLM prompts.

        Args:
            names: Specific entity names to include.
                   If None, includes all entities.

        Returns:
            Formatted string block for prompt injection

        Example output:
            === Entity: user_alice ===
            risk_score: 0.85
            flags: wire_fraud, suspicious_login
        """
        entity_names = names or self.list_entities()
        if not entity_names:
            return "No entity memory available."

        lines = []
        for name in entity_names:
            data = self.get(name)
            if data is None:
                continue
            lines.append(f"=== Entity: {name} ===")
            if isinstance(data, dict):
                for k, v in data.items():
                    lines.append(f"  {k}: {v}")
            else:
                lines.append(f"  {data}")
            lines.append("")
        return "\n".join(lines) if lines else "No entity memory available."

    # ── Private helpers ───────────────────────────────────

    def _write_json(self, name: str, record: dict):
        """Write the JSON record file."""
        path = self._json_path(name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)

    def _write_md(self, name: str, record: dict):
        """Write the Markdown entity file."""
        ts      = record.get("updated_at", "?")
        version = record.get("version", 1)
        desc    = record.get("description", "")
        data    = record.get("data", {})
        history = record.get("history", [])

        lines = [
            f"# Entity: `{name}`",
            "",
            f"> {desc}" if desc else "",
            f"**Last Updated:** {ts}  |  **Version:** v{version}",
            "",
            "## Current Data",
            "```json",
            json.dumps(data, indent=2, ensure_ascii=False),
            "```",
            "",
            "## Change History",
        ]
        for h in history[-10:]:  # Last 10 changes
            lines.append(f"- **{h['timestamp']}** ({h.get('action','?')}): "
                         f"{str(h.get('data', ''))[:100]}")
        lines.append("")

        path = self._md_path(name)
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))


# ── Convenience key-value interface ──────────────────────
class SimpleKVMemory:
    """
    Simplified string key-value wrapper around EntityMemory.
    Useful for working memory patterns.

    Usage:
        kv = SimpleKVMemory()
        kv.set("current_task", "Analyze transaction T001")
        task = kv.get("current_task")
    """

    def __init__(self):
        self._em = EntityMemory()

    def set(self, key: str, value: str) -> None:
        self._em.set(key, {"value": value, "type": "string"})

    def get(self, key: str) -> Optional[str]:
        data = self._em.get(key)
        if data and isinstance(data, dict):
            return data.get("value")
        return None

    def all(self) -> dict[str, str]:
        result = {}
        for name in self._em.list_entities():
            val = self.get(name)
            if val is not None:
                result[name] = val
        return result
