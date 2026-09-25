---
description: Mandatory rule guaranteeing embedded substrate resilience and socket connectivity.
globs: ["**/*"]
always_apply: true
---

# Invariant [Substrate-Resilience-Mandate]

## Rule:
Cerebrum operations MUST communicate with memory substrates exclusively via:
1. Unix Domain Socket (`~/.cerebrum/run/falkordb.sock`) or loopback TCP (`127.0.0.1:6379`).
2. FastMCP Sole Custodian daemon (`cerebrum.server`) for vector search and RocksDB writes.
3. Subagents and lifecycle hooks MUST NEVER instantiate `QdrantClient(path=...)` directly to prevent exclusive OS lock conflicts.
