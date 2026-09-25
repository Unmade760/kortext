#!/usr/bin/env bash
set -e

# ==============================================================================
# Cerebrum Native FalkorDB Build & Universal Binary Provisioning Script
# Target: macOS (Apple Silicon ARM64 / Intel) & Linux (x86_64 / aarch64)
# ==============================================================================

CEREBRUM_HOME="${HOME}/.cerebrum"
BIN_DIR="${CEREBRUM_HOME}/bin"
RUN_DIR="${CEREBRUM_HOME}/run"
LOG_DIR="${CEREBRUM_HOME}/logs"
DATA_DIR="${CEREBRUM_HOME}/data/falkordb"
CONF_DIR="${CEREBRUM_HOME}/config"
BUILD_DIR="/tmp/cerebrum_falkordb_build"

echo "=== Cerebrum Native FalkorDB Provisioning Initializing ==="
mkdir -p "${BIN_DIR}" "${RUN_DIR}" "${LOG_DIR}" "${DATA_DIR}" "${CONF_DIR}" "${BUILD_DIR}"

TARGET_MODULE="${BIN_DIR}/falkordb.so"
OS="$(uname -s)"
ARCH="$(uname -m)"

if [ -f "${TARGET_MODULE}" ]; then
    echo "Native FalkorDB module already exists at ${TARGET_MODULE}."
    echo "To force a rebuild, delete this file and re-run."
    exit 0
fi

# 1. Tier 0: Precompiled Verified Native Binary Retrieval
RELEASE_VERSION="${FALKORDB_VERSION:-v4.20.7}"
RELEASE_URL="https://github.com/FalkorDB/FalkorDB/releases/download/${RELEASE_VERSION}"
BINARY_DOWNLOADED=false

if [ "${OS}" = "Darwin" ]; then
    if [ "${ARCH}" = "arm64" ] || [ "${ARCH}" = "aarch64" ]; then
        DOWNLOAD_NAME="falkordb-macos-arm64v8.so"
    else
        DOWNLOAD_NAME="falkordb-macos-x64.so"
    fi
elif [ "${OS}" = "Linux" ]; then
    if [ "${ARCH}" = "arm64" ] || [ "${ARCH}" = "aarch64" ]; then
        DOWNLOAD_NAME="falkordb-arm64v8.so"
    else
        DOWNLOAD_NAME="falkordb-x64.so"
    fi
else
    DOWNLOAD_NAME=""
fi

if [ -n "${DOWNLOAD_NAME}" ] && [ "${FORCE_SOURCE_BUILD:-0}" != "1" ]; then
    echo "Attempting to retrieve verified precompiled native binary: ${DOWNLOAD_NAME} (${RELEASE_VERSION})..."
    if curl -sSL -f --connect-timeout 10 "${RELEASE_URL}/${DOWNLOAD_NAME}" -o "${TARGET_MODULE}.tmp" 2>/dev/null; then
        mv "${TARGET_MODULE}.tmp" "${TARGET_MODULE}"
        chmod 755 "${TARGET_MODULE}"
        echo "=== Successfully installed precompiled native FalkorDB module -> ${TARGET_MODULE} ==="
        BINARY_DOWNLOADED=true
    else
        echo "Precompiled binary not directly accessible. Falling back to native compilation from source."
        rm -f "${TARGET_MODULE}.tmp"
    fi
fi

# 2. Tier 1: Source Compilation with Strict Toolchain Preflight (Fallback)
if [ "${BINARY_DOWNLOADED}" = "false" ]; then
    command -v git >/dev/null 2>&1 || { echo "Error: git is required."; exit 1; }
    command -v cmake >/dev/null 2>&1 || { echo "Error: cmake is required (brew install cmake)."; exit 1; }
    command -v make >/dev/null 2>&1 || { echo "Error: make is required (install Xcode Command Line Tools)."; exit 1; }

    echo "Cloning FalkorDB source code with submodules (GraphBLAS, SuiteSparse)..."
    rm -rf "${BUILD_DIR}/FalkorDB"
    git clone --recursive --depth 1 https://github.com/FalkorDB/FalkorDB.git "${BUILD_DIR}/FalkorDB"
    cd "${BUILD_DIR}/FalkorDB"

    NUM_CORES=$(sysctl -n hw.ncpu 2>/dev/null || nproc 2>/dev/null || echo 4)
    echo "Detected Platform: ${OS} (${ARCH}) with ${NUM_CORES} compilation cores."

    if [ "${OS}" = "Darwin" ]; then
        BREW_PREFIX=$(brew --prefix 2>/dev/null || echo "/opt/homebrew")
        if [ -d "${BREW_PREFIX}/opt/libomp" ]; then
            export OpenMP_C_FLAGS="-Xpreprocessor -fopenmp -I${BREW_PREFIX}/opt/libomp/include"
            export OpenMP_CXX_FLAGS="-Xpreprocessor -fopenmp -I${BREW_PREFIX}/opt/libomp/include"
            export LDFLAGS="-L${BREW_PREFIX}/opt/libomp/lib -lomp"
        fi
        export CFLAGS="-O3 -flto"
        export CXXFLAGS="-O3 -flto"
        echo "Configuring Apple Clang compiler..."
        make -j"${NUM_CORES}"
        if [ -f "bin/falkordb.so" ]; then
            cp bin/falkordb.so "${TARGET_MODULE}"
        elif [ -f "bin/falkordb.dylib" ]; then
            cp bin/falkordb.dylib "${TARGET_MODULE}"
        else
            echo "Error: FalkorDB compilation completed but module binary not found."
            exit 1
        fi
    else
        export CFLAGS="-O3 -march=native -flto"
        export CXXFLAGS="-O3 -march=native -flto"
        make -j"${NUM_CORES}"
        cp bin/falkordb.so "${TARGET_MODULE}"
    fi

    chmod 755 "${TARGET_MODULE}"
    rm -rf "${BUILD_DIR}"
    echo "=== FalkorDB Native Module Built Successfully -> ${TARGET_MODULE} ==="
fi
