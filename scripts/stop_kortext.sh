#!/usr/bin/env bash
# ==============================================================================
# Kortext Substrate Shutdown Utility
# ==============================================================================
set -euo pipefail

KORTEXT_HOME="${KORTEXT_HOME:-${HOME}/.kortext}"
RUN_DIR="${KORTEXT_HOME}/run"
PID_FILE="${RUN_DIR}/falkordb.pid"
SOCKET_FILE="${RUN_DIR}/falkordb.sock"

echo "=== Halting Kortext Native Substrates ==="

if [ -f "${PID_FILE}" ]; then
    PID=$(cat "${PID_FILE}")
    if kill -0 "${PID}" 2>/dev/null; then
        echo "Shutting down FalkorDB server (PID ${PID})..."
        kill -TERM "${PID}"
        # Wait for clean exit
        for i in {1..30}; do
            if ! kill -0 "${PID}" 2>/dev/null; then
                echo "FalkorDB process terminated gracefully."
                break
            fi
            sleep 0.1
        done
    fi
    rm -f "${PID_FILE}" "${SOCKET_FILE}"
else
    # Fallback: check if redis-server with falkordb.conf is running
    CONF_PID=$(pgrep -f "falkordb.conf" || true)
    if [ -n "${CONF_PID}" ]; then
        echo "Terminating FalkorDB process ${CONF_PID}..."
        kill -TERM ${CONF_PID} 2>/dev/null || true
    fi
fi

echo "=== All Kortext Substrates Halted Cleanly ==="
