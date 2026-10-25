## 📝 Pull Request Summary

<!-- Briefly explain what changes this PR introduces and why they are needed. -->

## 🎯 Target Subsystems
- [ ] Tier 0: Symbols & SCIP Graph (`kortext/symbols/`)
- [ ] Tier 1: Episodic Knowledge Graph (`kortext/episodic/`)
- [ ] Tier 2: OpenViking Dynamic Chunker (`kortext/chunking/`)
- [ ] Tier 3: Dense Retrieval & Reranker (`kortext/retrieval/`)
- [ ] FastMCP Server & Tools (`kortext/server.py`)
- [ ] Interactive Web Dashboard (`kortext/dashboard/`)
- [ ] Antigravity Integration & Hooks (`integrations/antigravity/`, `scripts/hooks/`)
- [ ] Documentation & CI (`docs/`, `.github/`)

## 🔍 Changes Made
<!-- Bulleted list of specific changes made -->
- 
- 

## 🧪 Verification & Testing
- [ ] `CI=1 uv run pytest -q`
- [ ] `uv run python3 scripts/test_antigravity_hooks.py`
- [ ] `uv run python3 scripts/test_plugin_manifest.py`

## 📋 Pre-Merge Checklist
- [ ] Code follows the guidelines in [CODING_STANDARDS.md](CODING_STANDARDS.md).
- [ ] No single file exceeds the **1,000-line budget**.
- [ ] Zero hardcoded machine paths (`/Users/...`, `/home/...`).
- [ ] All new functions include type annotations.
- [ ] No secrets or `.env` files are tracked.
