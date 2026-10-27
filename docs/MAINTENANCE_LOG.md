# Maintenance log

Test-suite repairs on branch `fix/test-failures`, starting from commit fb1c115 (656 passed, 8 failed, 1 collection error).

## 1. Missing jinja2 dependency

- Symptom: `ModuleNotFoundError: No module named 'jinja2'` while collecting `tests/test_dashboard_routes.py`, and in three audit tests that import the dashboard app.
- Root cause: `kortext/dashboard/app.py` uses FastAPI `Jinja2Templates`, but `jinja2` was not listed in `pyproject.toml`.
- Change: added `jinja2>=3.1` to `dependencies`, regenerated `uv.lock`, ran `uv sync --extra dev`.
- Files: `pyproject.toml`, `uv.lock`.
- Result: the collection error is gone and the three audit tests pass. Collecting `test_dashboard_routes.py` exposed one more failure, covered in fix 3.

## 2. Hardcoded /Users/rb paths in tests

- Symptom: `test_fix11_task_tracker_modularity_review_gate_and_token_budget` and `test_fix_section_4c4_shallow_module_detection_and_glossary` read files under `/Users/rb/kortext`, which does not exist here.
- Root cause: absolute paths from the original author's machine.
- Change: both paths now resolve from `Path(__file__).resolve().parents[1]`.
- Files: `tests/test_audit_fixes.py`.
- Left alone: the remaining `/Users/rb/agy-hud/...` references in `tests/test_audit_regressions.py` and `tests/test_complete_audit_verification.py` point at a separate project, and the tests guard them with `is_file()` or skip. The `cwd` string in a stdin payload is only sample data.
- Result: `tests/test_audit_fixes.py` 13 passed.

## 3. Embedding dimension hardcoded to 4096 in tests

- Symptom: `test_benchmark_embedded_qdrant_latency` failed with `shapes (0,384) and (4096,) not aligned`. After fix 1, `test_action_create_collection_meta_json_safe` failed with `384 == 4096`.
- Root cause: both tests assume the 4096-dim remote embedding model. The code takes the dimension from `get_embed_dimension()`, which gives 384 (local FastEmbed) unless `EMBED_BASE_URL` or `EMBED_DIMENSION` is set. Nothing leaked from the environment: no `EMBED_*` or `KORTEXT_*` variables, no `.env` in the repo, and nothing in `~/.kortext` sets them. The 4096 comes from the test code itself.
- Change: the benchmark reads the vector size from the `Antigravity_Docs` collection it queries, since that size was fixed by whatever config created the store. The dashboard test clears `EMBED_DIMENSION`, `EMBED_BASE_URL` and their `KORTEXT_` forms, then asserts the literal 384 fallback. Comparing against `get_embed_dimension()` broke when the route's raw `os.getenv("EMBED_DIMENSION")` and the helper disagreed. Both pass with `EMBED_DIMENSION=999` set.
- Files: `tests/test_empirical_benchmarks.py`, `tests/test_dashboard_routes.py`.
- Result: both files pass.

## 4. Stale markdown AST declarations test

- Symptom: `test_save_markdown_ast_parameterized` expected `$declarations` in the third Cypher query and found the links query.
- Root cause: `SymbolGraphManager.save_markdown_ast` deliberately skips declarations that match a section by name and line (added in fb1c115, with a code comment). The test passed a declaration named "Introduction" at line 1, the same as its section, so it was skipped.
- Change: the test passes the duplicate "Introduction" at line 1 plus a new "Details" at line 3, and asserts that only "Details" is written. That keeps a check on the dedup: with the skip disabled in `graph.py`, the test fails. No code change.
- Files: `tests/test_falkordb_consolidation.py`.
- Result: 12 passed.

## 5. Missing networkx dependency

- Symptom: `AttributeError: 'NoneType' object has no attribute 'Graph'` in `test_detect_subsystems_excludes_markdown_and_path_labels`.
- Root cause: `kortext/symbols/clustering.py` imports networkx in a try block and sets `nx = None` on failure, then calls `nx.Graph()` unconditionally. networkx was not a declared dependency, so a fresh environment lacked it.
- Change: added `networkx>=3.0` to `dependencies` and updated `uv.lock`.
- Files: `pyproject.toml`, `uv.lock`.
- Result: `tests/test_subsystem_clustering.py` 3 passed.

## 6. Lint cleanups (no behavior change)

- Symptom: `ruff check` with the error rules (E9, F63, F7, F82, F811, F821, F823) reported an undefined name and five redundant imports.
- Change: imported `Tuple` in `kortext/episodic/driver.py` (used in a local annotation; harmless at runtime because of `from __future__ import annotations`, but undefined). Removed the second `generate_skeleton_chunk` import at the end of `kortext/chunking/ast_splitter.py` (the top-level import already serves `__all__`). Removed unused duplicate imports in `tests/test_retrieval_pipeline.py` and `tests/test_setup_wizard.py`.
- Left alone: ruff B023 on the `embed_batch` closure in `kortext/ingest.py` is a false positive, since the closure is awaited by `asyncio.gather` inside the same loop pass.
- Files: `kortext/episodic/driver.py`, `kortext/chunking/ast_splitter.py`, `tests/test_retrieval_pipeline.py`, `tests/test_setup_wizard.py`, `docs/MAINTENANCE_LOG.md`.
- Result: ruff reports no errors under those rules. Affected test files pass.

## Final state

Every test file run separately: 690 passed, 0 failed (baseline 656 passed, 8 failed, 1 collection error).

## 7. Tests installing Kortext into the developer's Antigravity config

- Symptom: after a test run, `~/.gemini/config/plugins/kortext` linked to the repo, a `kortext` server sat in `~/.gemini/config/mcp_config.json`, and `kortext/*` sidecars were enabled in `~/.gemini/config/config.json`. Every `agy` session then loaded the Kortext hooks.
- Root cause: `test_cli_setup_parser` and `test_cli_setup_parser_skip_binaries` run the real `kortext setup`. Its step 7 calls `install_plugin()` and `_enable_plugin_sidecars()` under `Path.home()`. `test_run_diagnostics` also passed only because a real `~/.kortext` existed.
- Change: an autouse fixture in `tests/test_setup_wizard.py` points `HOME` and `KORTEXT_HOME` at each test's `tmp_path` and creates `.kortext` there.
- Files: `tests/test_setup_wizard.py`, `docs/MAINTENANCE_LOG.md`.
- Result: the full suite run under a throwaway `HOME` passes (690) and writes nothing under that home's `.gemini`. Other files still create `~/.kortext` (data only, no Antigravity config); an autouse `HOME` fixture in `conftest.py` would cover those too.

## 8. `pre_tool` hook stalling 8 s when FalkorDB is down

- Symptom: with FalkorDB not running, the `pre_tool` hook on `grep_search` took a median of 8.0 s (max 9.3 s over 20 runs), longer than its 5 s timeout in `hooks.json`. Every grep in an `agy` session waited that long.
- Root cause: `_auto_seek_symbol_hint` in `kortext/hooks/pipelines/pre_tool.py` called `seek_symbol` without checking that FalkorDB was reachable. `FalkorDBClient.get_redis` used the redis-py 8 default retry policy, which backs off for about 4 s per command on a refused connection (20 sleeps across two commands, seen with cProfile).
- Change: `get_redis` sets `socket_connect_timeout=0.5` and `Retry(ExponentialBackoff(cap=0.1, base=0.02), 2)` on both the Unix socket and TCP clients. `_auto_seek_symbol_hint` returns early unless the 20 ms socket probe already used by `_is_symbol_graph_empty` succeeds.
- Files: `kortext/falkordb_client.py`, `kortext/hooks/pipelines/pre_tool.py`, `tests/test_fastembed_fallback.py` (the two exact-kwargs `redis.Redis` assertions now expect the new arguments), `docs/MAINTENANCE_LOG.md`.
- Result: `pre_tool` median 116 ms with FalkorDB down, 122 ms with a live FalkorDB container (121 ms before the change, so no cost on the healthy path). Queries through the client against the live container work. Hook, FalkorDB, seek, server and regression test files pass, and `scripts/test_antigravity_hooks.py` passes.

Other hook timings measured at the same baseline (median of 20 cold runs, FalkorDB down): `pre_invoke` 53 to 178 ms, `post_invoke` 52 ms, `post_tool` 152 ms, `stop` 153 ms.
