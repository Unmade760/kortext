---
name: token-budget-advisor
description: Context economics runbook monitoring attention entropy and enforcing Knapsack MMR packing.
version: 1.0.0
triggers:
  - "token budget"
  - "context bloat"
  - "check tokens"
---

# Token Budget & Context Economics Runbook

## Protocol Directives:
1. **Grep Suppression:** Never execute `rg` or `grep_search` on broad paths. Use `seek_symbol`.
2. **Context Window Ceiling:** If conversation transcript exceeds 40,000 tokens, trigger task handoff via `memory_session_handoff` and recommend starting a clean session.
3. **Subagent Delegation:** When task complexity $C \ge 4$, delegate to subagents to isolate tool output tokens.
