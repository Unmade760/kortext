---
name: agent-architecture-audit
description: Audits subagent frontmatter, scoped tool sets, and recursion depth limits.
version: 1.0.0
triggers:
  - "audit agents"
  - "check subagents"
---

# Agent Architecture Audit Protocol

## Directives:
1. Verify frontmatter schemas in `integrations/antigravity/agents/`.
2. Ensure models use `gemini-3.1-pro` for deep reasoning and `gemini-3.8-flash` for execution.
3. Validate tool scopes.
