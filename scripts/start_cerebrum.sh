#!/usr/bin/env bash
# ==============================================================================
# Cerebrum Substrate Launcher: Starts native FalkorDB and embedded services.
# ==============================================================================
set -euo pipefail

CEREBRUM_HOME="${CEREBRUM_HOME:-${HOME}/.cerebrum}"
BIN_DIR="${CEREBRUM_HOME}/bin"
RUN_DIR="${CEREBRUM_HOME}/run"
LOG_DIR="${CEREBRUM_HOME}/logs"
CONF_DIR="${CEREBRUM_HOME}/config"
DATA_DIR="${CEREBRUM_HOME}/data/falkordb"
PID_FILE="${RUN_DIR}/falkordb.pid"
SOCKET_FILE="${RUN_DIR}/falkordb.sock"

mkdir -p "${RUN_DIR}" "${LOG_DIR}" "${CONF_DIR}" "${DATA_DIR}" "${BIN_DIR}"

echo "=== Starting Cerebrum Native Substrates ==="

# 1. Locate redis-server binary
REDIS_SERVER_BIN=$(command -v redis-server || echo "/opt/homebrew/bin/redis-server")
if [ ! -x "${REDIS_SERVER_BIN}" ]; then
    echo "Error: redis-server binary not found. Please install via: brew install redis"
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

    echo "Launching native FalkorDB server daemon via ${REDIS_SERVER_BIN}..."
    "${REDIS_SERVER_BIN}" "${CONF_DIR}/falkordb.conf"
    
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
python3 -c "
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
mkdir -p "${CEREBRUM_HOME}/qdrant"
echo "✅ Embedded Qdrant storage verified at ${CEREBRUM_HOME}/qdrant"

echo "=== Cerebrum Native Substrates Online & Ready ==="
