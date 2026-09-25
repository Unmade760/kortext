---
name: cerebrum-rag
description: Operational runbook and deep guide for querying the Cerebrum 5-tier dual-memory and RAG system. Activate whenever searching memory, persistent knowledge, codebase structure, re-indexing workspaces, or debugging Cerebrum services (Qdrant, FalkorDB, oMLX). Also activate when search_knowledge_and_memory returns empty, when services are offline, or when the user invokes /cerebrum-rag.
---

# Cerebrum 5-Tier Dual-Memory & Retrieval Guide

## 1. System Topology
The Cerebrum cognitive architecture coordinates five distinct knowledge tiers:
- **Tier 0 (Deterministic Symbol Graph):** FalkorDB `cerebrum_symbols` B-Tree indexed by Tree-sitter. Sub-millisecond O(1) jump-to-definition and caller graphs.
- **Tier 1 (Temporal Episodic Facts):** FalkorDB `cerebrum` bi-temporal entity graph with valid-time interval filtering.
- **Tier 2 (Structural Code Maps):** OpenViking hierarchical semantic overview.
- **Tier 3 (Semantic Vector Store):** Embedded Qdrant using Qwen3 MRL-2048 embeddings and BM25 sparse vectors.
- **Tier 4 (HippoRAG Graph Associative Walk):** In-process Personalized PageRank over unified entity and symbol topologies.

## 2. FastMCP Tool Usage
Query the unified substrate before editing code or making decisions:
```python
search_knowledge_and_memory(
    prompt="How does the 5-signal retrieval pipeline work?",
    collection="cerebrum_codebase"
)
```

## 3. Substrate Verification
Ensure native daemons are running:
```bash
cerebrum-check-health
# Or verify ports directly:
# FalkorDB: localhost:6379
# Qdrant:   localhost:6333
# oMLX:     localhost:8000
```
