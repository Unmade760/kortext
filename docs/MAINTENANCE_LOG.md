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
- Change: both tests use `get_embed_dimension()`, so they hold under either configuration.
- Files: `tests/test_empirical_benchmarks.py`, `tests/test_dashboard_routes.py`.
- Result: both files pass.

## 4. Stale markdown AST declarations test

- Symptom: `test_save_markdown_ast_parameterized` expected `$declarations` in the third Cypher query and found the links query.
- Root cause: `SymbolGraphManager.save_markdown_ast` deliberately skips declarations that match a section by name and line (added in fb1c115, with a code comment). The test passed a declaration named "Introduction" at line 1, the same as its section, so it was skipped.
- Change: the test declaration is now "Details" at line 3, so it is not a duplicate. No code change.
- Files: `tests/test_falkordb_consolidation.py`.
- Result: 12 passed.

## 5. Missing networkx dependency

- Symptom: `AttributeError: 'NoneType' object has no attribute 'Graph'` in `test_detect_subsystems_excludes_markdown_and_path_labels`.
- Root cause: `kortext/symbols/clustering.py` imports networkx in a try block and sets `nx = None` on failure, then calls `nx.Graph()` unconditionally. networkx was not a declared dependency, so a fresh environment lacked it.
- Change: added `networkx>=3.0` to `dependencies` and updated `uv.lock`.
- Files: `pyproject.toml`, `uv.lock`.
- Result: `tests/test_subsystem_clustering.py` 3 passed.
