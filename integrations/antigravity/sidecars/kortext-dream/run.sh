#!/bin/sh
set -e
exec "$(dirname "$0")/../run_sidecar.sh" dream "$@"
