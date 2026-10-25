"""
Code hygiene and architectural invariant tests for Kortext.

Enforces:
1. FastMCP stdio transport safety: zero direct print() calls in server modules.
2. Complete legacy purge: zero direct CEREBRUM_* or CORTEX_* environment reads.
"""

import ast
from pathlib import Path
from typing import List, Optional, Tuple


def test_no_print_in_server_modules():
    """
    Assert that zero Call nodes calling print() exist in kortext/dream.py,
    kortext/server.py, and kortext/retrieval/engine.py.
    Guarantees stdio JSON-RPC transport safety for FastMCP.
    """
    root = Path(__file__).resolve().parent.parent
    server_modules = [
        root / "kortext" / "dream.py",
        root / "kortext" / "server.py",
        root / "kortext" / "retrieval" / "engine.py",
    ]

    violations: List[str] = []
    for mod_path in server_modules:
        assert mod_path.is_file(), f"Target module {mod_path} does not exist"
        tree = ast.parse(mod_path.read_text(encoding="utf-8"), filename=str(mod_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name) and func.id == "print":
                    violations.append(f"{mod_path.relative_to(root)}:{node.lineno}")

    assert not violations, (
        f"Forbidden print() call(s) detected in FastMCP modules (stdio transport corruption risk): {violations}"
    )


def _is_env_call(node: ast.AST, prefix: str) -> Optional[str]:
    """Check if node is an os.getenv or os.environ.get call reading a variable with prefix."""
    if not isinstance(node, ast.Call):
        return None
    func = node.func
    is_env = False
    if isinstance(func, ast.Attribute):
        if func.attr == "getenv" and isinstance(func.value, ast.Name) and func.value.id == "os":
            is_env = True
        elif func.attr == "get" and isinstance(func.value, ast.Attribute):
            if (
                func.value.attr == "environ"
                and isinstance(func.value.value, ast.Name)
                and func.value.value.id == "os"
            ):
                is_env = True

    if is_env and node.args:
        first_arg = node.args[0]
        if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
            if first_arg.value.startswith(prefix):
                return first_arg.value
    return None





def test_zero_legacy_cerebrum_or_cortex_env_vars():
    """
    Scan all .py files under kortext/ to verify that ZERO direct os.getenv('CEREBRUM_...')
    or os.getenv('CORTEX_...') reads exist anywhere in the codebase.
    """
    root = Path(__file__).resolve().parent.parent
    kortext_dir = root / "kortext"

    violations: List[Tuple[str, int, str]] = []

    for py_file in sorted(kortext_dir.rglob("*.py")):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))

        for node in ast.walk(tree):
            var_name = _is_env_call(node, "CEREBRUM_") or _is_env_call(node, "CORTEX_")
            if var_name:
                violations.append((str(py_file.relative_to(root)), node.lineno, var_name))

    assert not violations, (
        f"Detected legacy CEREBRUM_* or CORTEX_* environment reads: {violations}"
    )
