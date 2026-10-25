#!/bin/sh
set -e

if [ -f "$HOME/.kortext/run/runtime.env" ]; then
    . "$HOME/.kortext/run/runtime.env"
fi

# Resolve physical directory of run_hook.sh even through symlinks
PRG="$0"
while [ -h "$PRG" ]; do
    ls="$(ls -ld "$PRG")"
    link="$(expr "$ls" : '.*-> \(.*\)$')"
    if expr "$link" : '/.*' > /dev/null; then
        PRG="$link"
    else
        PRG="$(dirname "$PRG")/$link"
    fi
done
HOOK_DIR="$(cd "$(dirname "$PRG")" && pwd -P)"

# Resolve repository root
if [ -n "$KORTEXT_ROOT" ] && [ -d "$KORTEXT_ROOT" ]; then
    PROJECT_ROOT="$KORTEXT_ROOT"
elif [ -f "$HOOK_DIR/../../pyproject.toml" ]; then
    PROJECT_ROOT="$(cd "$HOOK_DIR/../.." && pwd -P)"
elif [ -f "$HOME/kortext/pyproject.toml" ]; then
    PROJECT_ROOT="$HOME/kortext"
elif [ -f "$HOME/cortex/pyproject.toml" ]; then
    PROJECT_ROOT="$HOME/cortex"
else
    PROJECT_ROOT="$HOOK_DIR"
fi

# Resolve Python interpreter
if [ -n "$KORTEXT_PYTHON" ] && [ -x "$KORTEXT_PYTHON" ]; then
    PY_BIN="$KORTEXT_PYTHON"
elif [ -x "$PROJECT_ROOT/.venv/bin/python3" ]; then
    PY_BIN="$PROJECT_ROOT/.venv/bin/python3"
elif [ -x "$PROJECT_ROOT/.venv/Scripts/python.exe" ]; then
    PY_BIN="$PROJECT_ROOT/.venv/Scripts/python.exe"
elif [ -n "$VIRTUAL_ENV" ] && [ -x "$VIRTUAL_ENV/bin/python3" ]; then
    PY_BIN="$VIRTUAL_ENV/bin/python3"
elif [ -n "$VIRTUAL_ENV" ] && [ -x "$VIRTUAL_ENV/Scripts/python.exe" ]; then
    PY_BIN="$VIRTUAL_ENV/Scripts/python.exe"
elif command -v python3 >/dev/null 2>&1; then
    PY_BIN="$(command -v python3)"
elif command -v python >/dev/null 2>&1; then
    PY_BIN="$(command -v python)"
else
    PY_BIN="python3"
fi

export PYTHONPATH="$PROJECT_ROOT:${PYTHONPATH:-}"
exec "$PY_BIN" -m kortext.hooks.runner "$@"
