#!/bin/sh
set -e

MODULE="$1"
if [ -z "$MODULE" ]; then
    echo "Usage: run_sidecar.sh <module_name> [args...]" >&2
    exit 1
fi
shift || true

if [ -f "$HOME/.kortext/run/runtime.env" ]; then
    . "$HOME/.kortext/run/runtime.env"
fi

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
SIDECAR_ROOT="$(cd "$(dirname "$PRG")" && pwd)"
PLUGIN_DIR="$(cd "$SIDECAR_ROOT/.." && pwd)"

if [ -n "$KORTEXT_ROOT" ] && [ -d "$KORTEXT_ROOT" ]; then
    PROJECT_ROOT="$KORTEXT_ROOT"
elif [ -f "$PLUGIN_DIR/../../pyproject.toml" ]; then
    PROJECT_ROOT="$(cd "$PLUGIN_DIR/../.." && pwd)"
elif [ -f "$HOME/kortext/pyproject.toml" ]; then
    PROJECT_ROOT="$HOME/kortext"
else
    PROJECT_ROOT="$PLUGIN_DIR"
fi

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
if [ "$MODULE" = "dream" ] && [ $# -eq 0 ]; then
    DREAM_PROJ="${KORTEXT_PROJECT:-}"
    if [ -z "$DREAM_PROJ" ] && [ -n "${WORKSPACE_ROOTS:-}" ]; then
        FIRST_WS="$(printf '%s' "$WORKSPACE_ROOTS" | cut -d',' -f1 | cut -d':' -f1)"
        DREAM_PROJ="$(basename "$FIRST_WS")"
    fi
    DREAM_PROJ="${DREAM_PROJ:-all}"
    exec "$PY_BIN" -m "kortext.$MODULE" --project "$DREAM_PROJ"
fi
exec "$PY_BIN" -m "kortext.$MODULE" "$@"
