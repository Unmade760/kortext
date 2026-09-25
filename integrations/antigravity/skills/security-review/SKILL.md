---
name: security-review
description: Validates MINJA threat defenses and causal memory injection sanitization.
version: 1.0.0
triggers:
  - "security audit"
  - "minja check"
---

# Security & MINJA Defense Protocol

## Directives:
1. Verify all causal assertions are sanitized before writing to FalkorDB.
2. Ensure command execution safety gates block destructive shell commands.
