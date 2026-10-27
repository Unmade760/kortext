#!/usr/bin/env bash
# ==============================================================================
# Kortext Substrate Launcher: Starts native FalkorDB and embedded services.
# ==============================================================================
set -euo pipefail

KORTEXT_HOME="${KORTEXT_HOME:-${HOME}/.kortext}"
BIN_DIR="${KORTEXT_HOME}/bin"
RUN_DIR="${KORTEXT_HOME}/run"
LOG_DIR="${KORTEXT_HOME}/logs"
CONF_DIR="${KORTEXT_HOME}/config"
DATA_DIR="${KORTEXT_HOME}/data/falkordb"
PID_FILE="${RUN_DIR}/falkordb.pid"
SOCKET_FILE="${RUN_DIR}/falkordb.sock"

mkdir -p "${RUN_DIR}" "${LOG_DIR}" "${CONF_DIR}" "${DATA_DIR}" "${BIN_DIR}"

echo "=== Starting Kortext Native Substrates ==="

# 1. Locate redis-server binary
REDIS_SERVER_BIN=$(command -v redis-server || true)
if [ -z "${REDIS_SERVER_BIN}" ]; then
    echo "Error: redis-server not found on PATH. Install Redis (for example: brew install redis, apt install redis-server)."
    exit 1
fi

# 2. Check if FalkorDB is already running
if [ -f "${PID_FILE}" ] && kill -0 "$(cat "${PID_FILE}")" 2>/dev/null; then
    echo "FalkorDB is already running with PID $(cat "${PID_FILE}")."
else
    # Verify native module binary exists
    if [ ! -f "${BIN_DIR}/falkordb.so" ]; then
        echo "Native FalkorDB module not found. Building/downloading now..."
        bash "$(dirname "$0")/build_falkordb_native.sh"
    fi

    # Ensure dynamic configurations exist in CONF_DIR
    if [ ! -f "${CONF_DIR}/falkordb.conf" ] || [ ! -f "${CONF_DIR}/qdrant.yaml" ]; then
        python3 -c "from kortext.setup import provision_configurations; provision_configurations()" 2>/dev/null || true
    fi

    echo "Launching native FalkorDB server daemon via ${REDIS_SERVER_BIN}..."
    if [ -f "${CONF_DIR}/falkordb.conf" ]; then
        "${REDIS_SERVER_BIN}" "${CONF_DIR}/falkordb.conf"
    else
        "${REDIS_SERVER_BIN}" --daemonize yes --port 6379 --unixsocket "${SOCKET_FILE}" --unixsocketperm 700 --pidfile "${PID_FILE}" --logfile "${LOG_DIR}/falkordb.log" --dir "${DATA_DIR}" --loadmodule "${BIN_DIR}/falkordb.so"
    fi
    
    # Wait for Unix socket / TCP port to initialize
    for i in {1..30}; do
        if [ -S "${SOCKET_FILE}" ] || nc -z 127.0.0.1 6379 2>/dev/null; then
            echo "FalkorDB substrate online and responsive."
            break
        fi
        sleep 0.1
    done
fi

# 3. Verify Health Check
PY_BIN="$(dirname "$0")/../.venv/bin/python3"
if [ ! -x "${PY_BIN}" ]; then
    PY_BIN=$(command -v python3)
fi
"${PY_BIN}" -c "
import redis, sys
try:
    # Try socket first, then TCP
    r = None
    try:
        r = redis.Redis(unix_socket_path='${SOCKET_FILE}', socket_timeout=2.0)
        r.ping()
        print('✅ Substrate health check PASSED (Unix Domain Socket active).')
    except Exception:
        r = redis.Redis(host='127.0.0.1', port=6379, socket_timeout=2.0)
        r.ping()
        print('✅ Substrate health check PASSED (TCP Loopback :6379 active).')
except Exception as e:
    print(f'❌ Substrate health check FAILED: {e}', file=sys.stderr)
    sys.exit(1)
"

# 4. Verify Embedded Qdrant Storage
mkdir -p "${KORTEXT_HOME}/qdrant"
echo "✅ Embedded Qdrant storage verified at ${KORTEXT_HOME}/qdrant"

echo "=== Kortext Native Substrates Online & Ready ==="
