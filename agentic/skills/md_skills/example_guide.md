---
name: example_guide
description: Example Markdown skill — replace with your real domain playbook
version: 1.0.0
author: Your Team
---

# Example Domain Guide

This is an **Anthropic-style Markdown skill**. Its content is automatically
injected into Planner and Executor prompts as domain context.

Replace this file with your real domain knowledge, rules, or playbooks.

## When to Use This Guide
- Consult this guide before making any domain-specific decisions.
- Use the rules below to frame your analysis.

## Key Rules
1. **Always verify** before concluding — use memory_search to check past episodes.
2. **Be specific** — vague answers like "it might be risky" are not acceptable.
3. **Cite evidence** — reference tool results or memory snippets in your answer.
4. **Structured output** — always include a `confidence_score` (0.0–1.0).

## Output Format Requirements
```
ANALYSIS: <your analysis here>
CONFIDENCE: <0.0–1.0>
RECOMMENDATION: <clear, actionable recommendation>
```

## Domain-Specific Terms
| Term | Definition |
|------|------------|
| Example A | Your domain term A |
| Example B | Your domain term B |

---

**To replace this file:**
1. Edit `skills/md_skills/example_guide.md`
2. Or create a new `.md` file with YAML front-matter (same format as above)
3. Call `POST /skills/reload` — no server restart needed
