#!/bin/sh
set -e
if [ $# -eq 0 ]; then
    set -- --root "${WORKSPACE_ROOT:-.}"
fi
exec "$(dirname "$0")/../run_sidecar.sh" watcher "$@"
