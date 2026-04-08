# ============================================================
# skill_loader.py — Dynamic Skill Loader
# ============================================================
# IMPROVED IN THIS VERSION:
#   + Loads BOTH Python (.py) AND Anthropic-style Markdown (.md) skills
#   + MD skills: read SKILL_METADATA from YAML front-matter block,
#     expose the markdown content as "instructions" for LLM use
#   + SkillRegistry.call() normalizes output format for both types
#   + get_md_skill_context(): formats all MD skills into prompt context
#   + Hot reload: reload_skills() replaces registry in-place (no restart)
#   + Robust error isolation: one bad skill never breaks others
#   + ensure_example_skill() + ensure_example_md_skill() for first-run
#   + Detailed loading log per skill (name, version, type, file)
#
# ════════════════════════════════════════════════════════════
# SKILL TYPES
# ════════════════════════════════════════════════════════════
#
#   TYPE 1 — Python Skill (.py in /skills/)
#   ─────────────────────────────────────────────────────────
#   Best for: calculations, API calls, data processing
#   Contract:
#     SKILL_METADATA = {
#         "name":        "my_skill",
#         "description": "What it does",
#         "version":     "1.0.0",
#         "author":      "Name",
#     }
#     def run(input: dict) -> dict:
#         return { "success": True, "result": ..., "error": None }
#
#   Called via:  skill_call("my_skill", '{"key": "value"}')
#
#   TYPE 2 — Markdown Skill (.md in /skills/md_skills/)
#   ─────────────────────────────────────────────────────────
#   Best for: domain knowledge, rules, playbooks, guidelines
#   Format:
#     ---
#     name: fraud_playbook
#     description: Step-by-step fraud investigation guide
#     version: 1.0.0
#     author: Security Team
#     ---
#     # Fraud Investigation Playbook
#     ## When to Flag a Transaction
#     - Amount > $9000 in a single transfer...
#     ## Risk Scoring Rules
#     ...
#
#   Called via: get_md_skill_context("fraud_playbook")
#   Injected into Planner/Executor prompts as domain context.
#
# ════════════════════════════════════════════════════════════
# ADAPTING FOR A NEW PROJECT
# ════════════════════════════════════════════════════════════
#
#   Fraud Detection:
#     skills/fraud_risk_scorer.py    ← Python: score transactions
#     skills/md_skills/fraud_rules.md ← MD: investigation guide
#
#   HR Assistant:
#     skills/resume_parser.py        ← Python: parse resume text
#     skills/md_skills/hr_criteria.md ← MD: evaluation criteria
#
#   Trading:
#     skills/price_fetcher.py        ← Python: fetch market data
#     skills/md_skills/trading_rules.md ← MD: trading strategy
#
# ============================================================

import importlib.util
import sys
import json
import traceback
from pathlib import Path
from typing import Any, Callable, Optional

from config import cfg
from logger import get_logger

log = get_logger("skill_loader")


# ════════════════════════════════════════════════════════════
# SKILL REGISTRY
# ════════════════════════════════════════════════════════════

class SkillRegistry:
    """
    In-memory registry of all loaded skills (Python + Markdown).

    Each entry (Python skill):
        {
            "name":        str,       # from SKILL_METADATA
            "description": str,
            "version":     str,
            "author":      str,
            "type":        "python",
            "callable":    Callable,  # the run() function
            "file":        str,       # source path
        }

    Each entry (Markdown skill):
        {
            "name":         str,      # from YAML front-matter
            "description":  str,
            "version":      str,
            "author":       str,
            "type":         "markdown",
            "instructions": str,      # full markdown content (no front-matter)
            "callable":     None,     # MD skills are context, not callable
            "file":         str,
        }
    """

    def __init__(self):
        self._skills: dict[str, dict] = {}

    def register(self, entry: dict):
        """Register a skill. Overwrites if same name exists (hot-reload safe)."""
        name = entry["name"]
        self._skills[name] = entry
        skill_type = entry.get("type", "python")
        log.info(
            f"✅ Skill registered: [{skill_type}] '{name}' "
            f"v{entry.get('version','?')} ← {Path(entry['file']).name}"
        )

    def get(self, name: str) -> Optional[dict]:
        """Retrieve a skill entry by name. Returns None if not found."""
        return self._skills.get(name)

    def list_skills(self) -> list[dict]:
        """
        Return a safe summary list of all registered skills.

        React.js usage (GET /skills):
            [
              { "name": "fraud_risk_scorer", "description": "...",
                "version": "1.0.0", "type": "python", "file": "..." },
              { "name": "fraud_playbook",    "description": "...",
                "version": "1.0.0", "type": "markdown", "file": "..." }
            ]
        """
        return [
            {
                "name":        s["name"],
                "description": s["description"],
                "version":     s.get("version", "?"),
                "type":        s.get("type", "python"),
                "file":        s["file"],
            }
            for s in self._skills.values()
        ]

    def call(self, name: str, input_data: dict) -> dict:
        """
        Invoke a Python skill by name.

        Args:
            name:       Skill name (must be type=python)
            input_data: Dict of arguments

        Returns:
            { "success": bool, "result": Any, "error": str|None }

        Note: Markdown skills cannot be "called" — use
              get_md_skill_context() to inject their content.
        """
        skill = self.get(name)
        if not skill:
            return {
                "success": False, "result": None,
                "error": f"Skill '{name}' not found. Loaded: {self.names}",
            }

        if skill.get("type") == "markdown":
            return {
                "success": True,
                "result":  skill.get("instructions", ""),
                "error":   None,
                "_note":   "This is a Markdown skill — content returned as instructions.",
            }

        fn = skill.get("callable")
        if not callable(fn):
            return {"success": False, "result": None,
                    "error": f"Skill '{name}' has no callable run() function."}

        try:
            result = fn(input_data)
            if not isinstance(result, dict):
                result = {"success": True, "result": result, "error": None}
            result.setdefault("success", True)
            result.setdefault("error", None)
            return result
        except Exception as e:
            tb = traceback.format_exc()
            log.error(f"Skill '{name}' raised exception:\n{tb}")
            return {
                "success": False, "result": None,
                "error": f"{type(e).__name__}: {e}",
            }

    def get_md_skill_context(self, name: str) -> Optional[str]:
        """
        Return the markdown instructions for an MD skill.

        Args:
            name: Skill name

        Returns:
            Markdown string, or None if not found / not an MD skill

        Usage (injecting into a prompt):
            playbook = registry.get_md_skill_context("fraud_playbook")
            if playbook:
                system_prompt += f"\\n\\n## Domain Playbook\\n{playbook}"
        """
        skill = self.get(name)
        if skill and skill.get("type") == "markdown":
            return skill.get("instructions", "")
        return None

    def all_md_context(self) -> str:
        """
        Return all Markdown skill content concatenated.
        Used to inject all domain playbooks into Planner/Executor prompts.

        Returns:
            Single string with all MD skill content separated by headers
        """
        parts = []
        for s in self._skills.values():
            if s.get("type") == "markdown":
                parts.append(
                    f"### Skill: {s['name']}\n"
                    f"_{s.get('description', '')}_\n\n"
                    f"{s.get('instructions', '')}"
                )
        return "\n\n---\n\n".join(parts) if parts else ""

    @property
    def names(self) -> list[str]:
        return list(self._skills.keys())

    @property
    def python_skills(self) -> list[str]:
        return [n for n, s in self._skills.items() if s.get("type") == "python"]

    @property
    def md_skills(self) -> list[str]:
        return [n for n, s in self._skills.items() if s.get("type") == "markdown"]

    def __len__(self):
        return len(self._skills)

    def __repr__(self):
        return (f"SkillRegistry({len(self)} skills: "
                f"{len(self.python_skills)} python, {len(self.md_skills)} markdown)")


# ════════════════════════════════════════════════════════════
# PYTHON SKILL LOADER
# ════════════════════════════════════════════════════════════

def _load_python_skill(filepath: Path) -> Optional[dict]:
    """
    Load a single .py skill file and return its registry entry.

    Validates:
        - File must define SKILL_METADATA dict
        - File must define run(input: dict) -> dict function

    Args:
        filepath: Path to the .py file

    Returns:
        Registry entry dict, or None if loading/validation failed
    """
    module_name = f"skills.{filepath.stem}"
    try:
        spec   = importlib.util.spec_from_file_location(module_name, filepath)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        if not hasattr(module, "SKILL_METADATA"):
            log.warning(f"⚠️  Skip '{filepath.name}': missing SKILL_METADATA dict")
            return None
        if not hasattr(module, "run"):
            log.warning(f"⚠️  Skip '{filepath.name}': missing run(input: dict) -> dict")
            return None

        meta = module.SKILL_METADATA
        return {
            "name":        meta.get("name", filepath.stem),
            "description": meta.get("description", "No description"),
            "version":     meta.get("version", "0.0.1"),
            "author":      meta.get("author", "unknown"),
            "type":        "python",
            "callable":    module.run,
            "module":      module,
            "file":        str(filepath),
        }
    except Exception:
        log.error(f"❌ Failed to load Python skill '{filepath.name}':\n"
                  f"{traceback.format_exc()}")
        return None


# ════════════════════════════════════════════════════════════
# MARKDOWN SKILL LOADER
# ════════════════════════════════════════════════════════════

def _parse_yaml_frontmatter(content: str) -> tuple[dict, str]:
    """
    Parse YAML front-matter from a markdown file.

    Expected format:
        ---
        name: skill_name
        description: What this skill does
        version: 1.0.0
        author: Someone
        ---
        # Rest of markdown content...

    Args:
        content: Full file content string

    Returns:
        (metadata_dict, body_string)
        If no front-matter found, returns ({}, full_content)
    """
    content = content.strip()
    if not content.startswith("---"):
        return {}, content

    # Find closing ---
    end = content.find("---", 3)
    if end == -1:
        return {}, content

    front_matter = content[3:end].strip()
    body         = content[end + 3:].strip()

    # Simple line-by-line YAML parser (no PyYAML dependency)
    meta = {}
    for line in front_matter.splitlines():
        line = line.strip()
        if ":" in line:
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key:
                meta[key] = val

    return meta, body


def _load_md_skill(filepath: Path) -> Optional[dict]:
    """
    Load a single .md skill file and return its registry entry.

    The markdown content (after front-matter) becomes the "instructions"
    field — injected into LLM prompts as domain context.

    Args:
        filepath: Path to the .md file

    Returns:
        Registry entry dict, or None if loading failed
    """
    try:
        content      = filepath.read_text(encoding="utf-8")
        meta, body   = _parse_yaml_frontmatter(content)

        if not body.strip():
            log.warning(f"⚠️  Skip '{filepath.name}': empty content after front-matter")
            return None

        name = meta.get("name") or filepath.stem

        return {
            "name":         name,
            "description":  meta.get("description", "Markdown skill guide"),
            "version":      meta.get("version",     "md"),
            "author":       meta.get("author",      "unknown"),
            "type":         "markdown",
            "instructions": body,
            "callable":     None,    # MD skills are context, not callable
            "file":         str(filepath),
        }
    except Exception:
        log.error(f"❌ Failed to load MD skill '{filepath.name}':\n"
                  f"{traceback.format_exc()}")
        return None


# ════════════════════════════════════════════════════════════
# MAIN LOADER
# ════════════════════════════════════════════════════════════

def load_all_skills(
    py_dir: Optional[Path] = None,
    md_dir: Optional[Path] = None,
) -> SkillRegistry:
    """
    Discover and load ALL skills from Python + Markdown directories.

    Scan order:
        1. py_dir/*.py  → Python skills (default: cfg.SKILLS_DIR)
        2. md_dir/*.md  → Markdown skills (default: cfg.SKILLS_MD_DIR)

    Args:
        py_dir: Directory for Python skill files
        md_dir: Directory for Markdown skill files

    Returns:
        Populated SkillRegistry

    Usage:
        registry = load_all_skills()
        print(registry.names)
        result = registry.call("fraud_risk_scorer", {"amount": 9800})
        context = registry.all_md_context()
    """
    _py_dir = py_dir or cfg.SKILLS_DIR
    _md_dir = md_dir or cfg.SKILLS_MD_DIR
    registry = SkillRegistry()

    # ── Load Python skills ───────────────────────────────
    py_files = sorted(_py_dir.glob("*.py")) if _py_dir.exists() else []
    for fp in py_files:
        if fp.name.startswith("_"):
            continue
        entry = _load_python_skill(fp)
        if entry:
            registry.register(entry)

    # ── Load Markdown skills ─────────────────────────────
    md_files = sorted(_md_dir.glob("*.md")) if _md_dir.exists() else []
    for fp in md_files:
        if fp.name.startswith("_"):
            continue
        entry = _load_md_skill(fp)
        if entry:
            registry.register(entry)

    log.info(
        f"Skill loading complete: {len(registry)} total | "
        f"{len(registry.python_skills)} python [{', '.join(registry.python_skills) or 'none'}] | "
        f"{len(registry.md_skills)} markdown [{', '.join(registry.md_skills) or 'none'}]"
    )
    return registry


def reload_skills(
    registry: SkillRegistry,
    py_dir: Optional[Path] = None,
    md_dir: Optional[Path] = None,
) -> SkillRegistry:
    """
    Hot-reload all skills into an existing registry (no server restart).

    Replaces the registry's internal dict in-place so all existing
    references to the registry object stay valid.

    Args:
        registry: The existing SkillRegistry to repopulate
        py_dir:   Override Python skills directory
        md_dir:   Override Markdown skills directory

    Returns:
        The same registry object, now repopulated

    Usage (from running server):
        from skill_loader import get_registry, reload_skills
        reload_skills(get_registry())
        # Or via HTTP: POST /skills/reload
    """
    log.info("🔄 Hot-reloading all skills...")
    new_reg          = load_all_skills(py_dir, md_dir)
    registry._skills = new_reg._skills
    log.info(f"Hot-reload complete: {len(registry)} skills")
    return registry


# ════════════════════════════════════════════════════════════
# EXAMPLE SKILL GENERATORS (first-run scaffolding)
# ════════════════════════════════════════════════════════════

_EXAMPLE_PY_SKILL = '''# skills/example_skill.py
# ── Python Skill Template ──────────────────────────────────
# Copy this file, rename it, and replace the logic inside run().
# The server auto-loads all .py files in /skills/ on startup.
# ──────────────────────────────────────────────────────────

SKILL_METADATA = {
    "name":        "example_skill",
    "description": "Returns a greeting. Replace with your real logic.",
    "version":     "1.0.0",
    "author":      "Your Name",
}


def run(input: dict) -> dict:
    """
    Example skill: echoes a greeting.

    Input:  { "name": "Alice" }
    Output: { "success": True, "result": "Hello, Alice!", "error": None }
    """
    name = input.get("name", "World")
    return {
        "success": True,
        "result":  f"Hello, {name}! This is an example skill. Replace this logic.",
        "error":   None,
    }
'''

_EXAMPLE_MD_SKILL = '''---
name: example_guide
description: Example Markdown skill guide — replace with your domain playbook
version: 1.0.0
author: Your Team
---

# Example Domain Guide

This is an Anthropic-style Markdown skill. The content below is injected
into the Planner and Executor prompts as domain context.

Replace this file with your real domain knowledge.

## When to Use This Guide
- Always consult this guide before making domain-specific decisions.

## Key Rules
1. Rule one: Always verify before concluding.
2. Rule two: Cite your sources from memory context.
3. Rule three: Output structured results when possible.

## Output Format Requirements
- Always include a `confidence_score` between 0.0 and 1.0.
- Always include a `reasoning` field explaining your conclusion.
- Use bullet points for lists of findings.
'''


def ensure_example_skill():
    """Create example Python skill if /skills/ is empty."""
    skills_dir = cfg.SKILLS_DIR
    if not any(skills_dir.glob("*.py")):
        path = skills_dir / "example_skill.py"
        path.write_text(_EXAMPLE_PY_SKILL)
        log.info(f"Created example Python skill: {path}")


def ensure_example_md_skill():
    """Create example Markdown skill if /skills/md_skills/ is empty."""
    md_dir = cfg.SKILLS_MD_DIR
    if not any(md_dir.glob("*.md")):
        path = md_dir / "example_guide.md"
        path.write_text(_EXAMPLE_MD_SKILL)
        log.info(f"Created example Markdown skill: {path}")


# ════════════════════════════════════════════════════════════
# GLOBAL SINGLETON
# ════════════════════════════════════════════════════════════

skill_registry: Optional[SkillRegistry] = None


def get_registry() -> SkillRegistry:
    """
    Return the global skill registry, initializing on first call.

    Creates example skills if directories are empty (first-run UX).
    Thread-safe for reads; skill loading happens once at startup.

    Usage:
        from skill_loader import get_registry
        registry = get_registry()
        result   = registry.call("fraud_risk_scorer", {"amount": 9800})
        context  = registry.all_md_context()
    """
    global skill_registry
    if skill_registry is None:
        ensure_example_skill()
        ensure_example_md_skill()
        skill_registry = load_all_skills()
    return skill_registry
