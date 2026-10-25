"""
Kortext Cross-Platform Binary Manager.

Handles automated platform detection, release asset URL resolution, safe downloading
with SHA-256 integrity verification, tar/zip archive extraction, execution permission
assignment, and verification for native substrate binaries (Qdrant & FalkorDB).
"""
from __future__ import annotations

import hashlib
import logging
import os
import platform
import shutil
import stat
import subprocess
import tarfile
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple

logger = logging.getLogger("kortext.binaries")

# Default verified release targets
DEFAULT_QDRANT_VERSION = os.getenv("KORTEXT_QDRANT_VERSION", "v1.13.4")
DEFAULT_FALKORDB_VERSION = os.getenv("KORTEXT_FALKORDB_VERSION", "v4.22.0")

# Pinned SHA-256 digests keyed by (binary_name, version, os_name, arch).
# Only verified upstream release digests are pinned by default; additional platform
# targets can be supplied via KORTEXT_<BINARY>_<OS>_<ARCH>_SHA256 environment variables
# or verified automatically via upstream .sha256 sidecar files during download.
_DEFAULT_VERIFIED_SHA256: Dict[Tuple[str, str, str, str], str] = {
    ("qdrant", "v1.13.4", "darwin", "arm64"): "967ce05dac592ede582072f0c335f3c2d095dfe4dd21ab370b89d7d9158d6cc4",
    ("qdrant", "v1.13.4", "darwin", "x86_64"): "c894218a92b0e48901d63218a974258b72a534d2c7800d5c838a57600a737126",
    ("qdrant", "v1.13.4", "linux", "arm64"): "b78d6e109f426488321b5c0a8172645a8014796e217c42d90927846234829104",
    ("falkordb", "v4.22.0", "darwin", "arm64"): "d9aac2d48b455a7efcc35f2421b13dbf9e96c23e5cc2a99f66e9973be61a1d18",
}

_ENV_SHA256_KEYS: Dict[Tuple[str, str, str, str], str] = {
    ("qdrant", "v1.13.4", "darwin", "arm64"): "KORTEXT_QDRANT_DARWIN_ARM64_SHA256",
    ("qdrant", "v1.13.4", "darwin", "x86_64"): "KORTEXT_QDRANT_DARWIN_X86_64_SHA256",
    ("qdrant", "v1.13.4", "linux", "arm64"): "KORTEXT_QDRANT_LINUX_ARM64_SHA256",
    ("qdrant", "v1.13.4", "linux", "x86_64"): "KORTEXT_QDRANT_LINUX_X86_64_SHA256",
    ("qdrant", "v1.13.4", "windows", "x86_64"): "KORTEXT_QDRANT_WINDOWS_X86_64_SHA256",
    ("falkordb", "v4.22.0", "darwin", "arm64"): "KORTEXT_FALKORDB_DARWIN_ARM64_SHA256",
    ("falkordb", "v4.22.0", "darwin", "x86_64"): "KORTEXT_FALKORDB_DARWIN_X86_64_SHA256",
    ("falkordb", "v4.22.0", "linux", "arm64"): "KORTEXT_FALKORDB_LINUX_ARM64_SHA256",
    ("falkordb", "v4.22.0", "linux", "x86_64"): "KORTEXT_FALKORDB_LINUX_X86_64_SHA256",
}

PINNED_BINARY_SHA256: Dict[Tuple[str, str, str, str], str] = {}
for _target_key, _env_var in _ENV_SHA256_KEYS.items():
    _val = os.getenv(_env_var, _DEFAULT_VERIFIED_SHA256.get(_target_key, "")).strip().lower()
    if len(_val) == 64:
        PINNED_BINARY_SHA256[_target_key] = _val


@dataclass(frozen=True)
class PlatformInfo:
    """Immutable representation of host platform and architecture."""
    os_name: str          # "darwin", "linux", "windows"
    arch: str             # "arm64", "x86_64", "unknown"
    raw_os: str           # e.g. "Darwin", "Linux", "Windows"
    raw_arch: str         # e.g. "arm64", "x86_64", "AMD64"
    is_macos: bool
    is_linux: bool
    is_windows: bool
    is_arm64: bool
    is_x86_64: bool


@dataclass(frozen=True)
class BinaryDownloadInfo:
    """Metadata for downloading and installing a native binary."""
    name: str
    version: str
    url: str
    archive_format: Optional[str]  # "tar.gz", "zip", None if raw
    binary_filename: str           # e.g. "qdrant", "qdrant.exe", "falkordb.so"
    is_raw_binary: bool
    expected_sha256: Optional[str] = None


@dataclass(frozen=True)
class BinaryProvisionResult:
    """Result of provisioning a binary."""
    binary_name: str
    path: Optional[Path]
    success: bool
    message: str


def detect_platform() -> PlatformInfo:
    """Detects and normalizes the host operating system and CPU architecture."""
    raw_os = platform.system()
    raw_arch = platform.machine()

    sys_lower = raw_os.lower()
    if "darwin" in sys_lower:
        norm_os = "darwin"
    elif "linux" in sys_lower:
        norm_os = "linux"
    elif "windows" in sys_lower:
        norm_os = "windows"
    else:
        norm_os = sys_lower

    arch_lower = raw_arch.lower()
    if arch_lower in ("arm64", "aarch64") or arch_lower.startswith("armv8"):
        norm_arch = "arm64"
    elif arch_lower in ("x86_64", "amd64", "x64"):
        norm_arch = "x86_64"
    else:
        norm_arch = "unknown"

    is_macos = norm_os == "darwin"
    is_linux = norm_os == "linux"
    is_windows = norm_os == "windows"
    is_arm64 = norm_arch == "arm64"
    is_x86_64 = norm_arch == "x86_64"

    return PlatformInfo(
        os_name=norm_os,
        arch=norm_arch,
        raw_os=raw_os,
        raw_arch=raw_arch,
        is_macos=is_macos,
        is_linux=is_linux,
        is_windows=is_windows,
        is_arm64=is_arm64,
        is_x86_64=is_x86_64,
    )


def get_qdrant_download_info(
    p: Optional[PlatformInfo] = None,
    version: str = DEFAULT_QDRANT_VERSION,
) -> Optional[BinaryDownloadInfo]:
    """Resolves the verified Qdrant release download URL and metadata for host platform."""
    plat = p or detect_platform()
    base_url = f"https://github.com/qdrant/qdrant/releases/download/{version}"
    pinned_sha = PINNED_BINARY_SHA256.get(("qdrant", version, plat.os_name, plat.arch))

    if plat.is_macos:
        asset_name = "qdrant-aarch64-apple-darwin.tar.gz" if plat.is_arm64 else "qdrant-x86_64-apple-darwin.tar.gz"
        return BinaryDownloadInfo(
            name="qdrant",
            version=version,
            url=f"{base_url}/{asset_name}",
            archive_format="tar.gz",
            binary_filename="qdrant",
            is_raw_binary=False,
            expected_sha256=pinned_sha,
        )

    if plat.is_linux:
        asset_name = "qdrant-aarch64-unknown-linux-musl.tar.gz" if plat.is_arm64 else "qdrant-x86_64-unknown-linux-gnu.tar.gz"
        return BinaryDownloadInfo(
            name="qdrant",
            version=version,
            url=f"{base_url}/{asset_name}",
            archive_format="tar.gz",
            binary_filename="qdrant",
            is_raw_binary=False,
            expected_sha256=pinned_sha,
        )

    if plat.is_windows:
        asset_name = "qdrant-x86_64-pc-windows-msvc.zip"
        return BinaryDownloadInfo(
            name="qdrant",
            version=version,
            url=f"{base_url}/{asset_name}",
            archive_format="zip",
            binary_filename="qdrant.exe",
            is_raw_binary=False,
            expected_sha256=pinned_sha,
        )

    return None


def get_falkordb_download_info(
    p: Optional[PlatformInfo] = None,
    version: str = DEFAULT_FALKORDB_VERSION,
) -> Optional[BinaryDownloadInfo]:
    """Resolves the verified FalkorDB release download URL and metadata for host platform."""
    plat = p or detect_platform()
    base_url = f"https://github.com/FalkorDB/FalkorDB/releases/download/{version}"
    pinned_sha = PINNED_BINARY_SHA256.get(("falkordb", version, plat.os_name, plat.arch))

    if plat.is_macos:
        asset_name = "falkordb-macos-arm64v8.so" if plat.is_arm64 else "falkordb-macos-x64.so"
        return BinaryDownloadInfo(
            name="falkordb",
            version=version,
            url=f"{base_url}/{asset_name}",
            archive_format=None,
            binary_filename="falkordb.so",
            is_raw_binary=True,
            expected_sha256=pinned_sha,
        )

    if plat.is_linux:
        asset_name = "falkordb-arm64v8.so" if plat.is_arm64 else "falkordb-x64.so"
        return BinaryDownloadInfo(
            name="falkordb",
            version=version,
            url=f"{base_url}/{asset_name}",
            archive_format=None,
            binary_filename="falkordb.so",
            is_raw_binary=True,
            expected_sha256=pinned_sha,
        )

    # Windows does not have native Redis/FalkorDB shared objects; uses Docker or WSL
    return None


def compute_file_sha256(path: Path) -> str:
    """Computes the SHA-256 hex digest of a file."""
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest().lower()


def _fetch_remote_sha256_sidecar(url: str, timeout: float = 10.0) -> Optional[str]:
    """Attempts to fetch a companion .sha256 sidecar file from the release URL."""
    for suffix in (".sha256", ".sha256sum"):
        sidecar_url = f"{url}{suffix}"
        if not sidecar_url.lower().startswith("https://"):
            continue
        try:
            req = urllib.request.Request(
                sidecar_url,
                headers={"User-Agent": "Kortext-Binary-Manager/2.0"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                text = resp.read(256).decode("utf-8", errors="ignore").strip()
                if text:
                    token = text.split()[0].strip().lower()
                    if len(token) == 64 and all(c in "0123456789abcdef" for c in token):
                        return token
        except Exception:
            continue
    return None


def download_file(
    url: str,
    dest_path: Path,
    timeout: float = 30.0,
    expected_sha256: Optional[str] = None,
) -> Path:
    """Downloads a remote file over HTTPS and verifies SHA-256 integrity before replacement."""
    if not url.lower().startswith("https://"):
        raise ValueError(f"Refusing insecure non-HTTPS binary download URL: {url}")

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    temp_file = dest_path.with_suffix(dest_path.suffix + ".download")

    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Kortext-Binary-Manager/2.0"},
    )

    logger.info("Downloading %s -> %s", url, dest_path)
    try:
        hasher = hashlib.sha256()
        with urllib.request.urlopen(req, timeout=timeout) as resp, open(temp_file, "wb") as out_file:
            while chunk := resp.read(65536):
                hasher.update(chunk)
                out_file.write(chunk)
        actual_sha = hasher.hexdigest().lower()
        resolved_expected = expected_sha256 or _fetch_remote_sha256_sidecar(url, timeout=min(timeout, 10.0))
        if resolved_expected:
            norm_expected = resolved_expected.strip().lower()
            if actual_sha != norm_expected:
                temp_file.unlink(missing_ok=True)
                raise ValueError(
                    f"SHA-256 digest mismatch for {url}: expected {norm_expected}, got {actual_sha}"
                )
        if temp_file.exists():
            temp_file.replace(dest_path)
        return dest_path
    except ValueError:
        if temp_file.exists():
            temp_file.unlink(missing_ok=True)
        raise
    except Exception as exc:
        if temp_file.exists():
            temp_file.unlink(missing_ok=True)
        raise RuntimeError(f"Failed to download {url}: {exc}") from exc


def extract_archive_binary(
    archive_path: Path,
    dest_binary_path: Path,
    archive_format: str,
    target_filename: str,
) -> Path:
    """Safely extracts a single target binary from a tar.gz or zip archive."""
    dest_binary_path.parent.mkdir(parents=True, exist_ok=True)

    if archive_format in ("tar.gz", "tar"):
        with tarfile.open(archive_path, "r:*") as tar:
            target_member = None
            for member in tar.getmembers():
                if Path(member.name).name == target_filename:
                    target_member = member
                    break
            if not target_member:
                raise FileNotFoundError(f"Binary '{target_filename}' not found in {archive_path.name}")

            f = tar.extractfile(target_member)
            if not f:
                raise IOError(f"Could not read member '{target_member.name}' from tar archive")
            with open(dest_binary_path, "wb") as out:
                shutil.copyfileobj(f, out)

    elif archive_format == "zip":
        with zipfile.ZipFile(archive_path, "r") as zf:
            target_name = None
            for name in zf.namelist():
                if Path(name).name == target_filename:
                    target_name = name
                    break
            if not target_name:
                raise FileNotFoundError(f"Binary '{target_filename}' not found in {archive_path.name}")

            with zf.open(target_name) as zf_file, open(dest_binary_path, "wb") as out:
                shutil.copyfileobj(zf_file, out)
    else:
        raise ValueError(f"Unsupported archive format: {archive_format}")

    # Set executable permissions on POSIX
    if platform.system() != "Windows":
        dest_binary_path.chmod(dest_binary_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    return dest_binary_path


def verify_binary_executable(binary_path: Path) -> bool:
    """Verifies that the binary exists and can execute --version or --help."""
    if not binary_path.exists():
        return False
    try:
        res = subprocess.run([str(binary_path), "--version"], capture_output=True, text=True, timeout=5.0)
        return res.returncode == 0 or "qdrant" in res.stdout.lower() or "qdrant" in res.stderr.lower()
    except Exception as exc:
        logger.debug("Binary verification check returned: %s", exc)
        return False


def pull_qdrant_binary(
    kortext_home: Path,
    platform_info: Optional[PlatformInfo] = None,
    force: bool = False,
) -> BinaryProvisionResult:
    """Downloads, verifies SHA-256, extracts, and provisions the native Qdrant executable."""
    plat = platform_info or detect_platform()
    dl_info = get_qdrant_download_info(plat)
    if not dl_info:
        return BinaryProvisionResult(
            binary_name="qdrant",
            path=None,
            success=False,
            message=f"No precompiled Qdrant binary available for {plat.os_name}/{plat.arch}",
        )

    bin_dir = kortext_home / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    target_path = bin_dir / dl_info.binary_filename

    if target_path.exists() and not force:
        return BinaryProvisionResult(
            binary_name="qdrant",
            path=target_path,
            success=True,
            message=f"Qdrant binary already exists at {target_path}",
        )

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_archive = Path(tmp_dir) / f"qdrant_download.{dl_info.archive_format}"
        try:
            download_file(dl_info.url, tmp_archive, expected_sha256=dl_info.expected_sha256)
            extract_archive_binary(tmp_archive, target_path, dl_info.archive_format or "tar.gz", dl_info.binary_filename)
            if platform.system() != "Windows":
                target_path.chmod(0o755)
            return BinaryProvisionResult(
                binary_name="qdrant",
                path=target_path,
                success=True,
                message=f"Successfully installed native Qdrant ({dl_info.version}) -> {target_path}",
            )
        except Exception as exc:
            return BinaryProvisionResult(
                binary_name="qdrant",
                path=None,
                success=False,
                message=f"Failed to pull Qdrant binary: {exc}",
            )


def pull_falkordb_module(
    kortext_home: Path,
    platform_info: Optional[PlatformInfo] = None,
    force: bool = False,
) -> BinaryProvisionResult:
    """Downloads, verifies SHA-256, and provisions the precompiled native FalkorDB module (falkordb.so)."""
    plat = platform_info or detect_platform()
    dl_info = get_falkordb_download_info(plat)
    if not dl_info:
        if plat.is_windows:
            wsl_path = shutil.which("wsl") or shutil.which("wsl.exe")
            if wsl_path:
                msg = (
                    "FalkorDB native module is POSIX-only. WSL2 detected: run `wsl redis-server --loadmodule falkordb.so --port 6379 --daemonize yes` "
                    "or use Docker (`docker run -p 6379:6379 -d falkordb/falkordb`)."
                )
            else:
                msg = "FalkorDB native module is POSIX-only. On Windows, use WSL2 (`wsl --install`) or Docker (`docker run -p 6379:6379 -d falkordb/falkordb`)."
        else:
            msg = f"No precompiled FalkorDB module found for {plat.os_name}/{plat.arch}."
        return BinaryProvisionResult(
            binary_name="falkordb",
            path=None,
            success=False,
            message=msg,
        )

    bin_dir = kortext_home / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    target_path = bin_dir / dl_info.binary_filename

    if target_path.exists() and not force:
        return BinaryProvisionResult(
            binary_name="falkordb",
            path=target_path,
            success=True,
            message=f"FalkorDB module already exists at {target_path}",
        )

    try:
        download_file(dl_info.url, target_path, expected_sha256=dl_info.expected_sha256)
        if platform.system() != "Windows":
            target_path.chmod(0o755)
        return BinaryProvisionResult(
            binary_name="falkordb",
            path=target_path,
            success=True,
            message=f"Successfully installed native FalkorDB module ({dl_info.version}) -> {target_path}",
        )
    except Exception as exc:
        return BinaryProvisionResult(
            binary_name="falkordb",
            path=None,
            success=False,
            message=f"Failed to pull FalkorDB module: {exc}",
        )


def generate_falkordb_conf(home: Path, is_windows: bool = False) -> str:
    """Generates dynamically resolved falkordb.conf without hardcoded workstation paths."""
    resolved_home = home.resolve()
    sock_path = resolved_home / "run" / "falkordb.sock"
    pid_path = resolved_home / "run" / "falkordb.pid"
    log_path = resolved_home / "logs" / "falkordb.log"
    data_path = resolved_home / "data" / "falkordb"
    mod_path = resolved_home / "bin" / "falkordb.so"

    lines = [
        "# Kortext High-Performance FalkorDB Configuration",
        f"# Auto-generated for: {resolved_home}",
        "port 6379",
        "bind 127.0.0.1",
    ]

    if not is_windows:
        lines.extend([
            f"unixsocket {sock_path}",
            "unixsocketperm 700",
            "daemonize yes",
            f"pidfile {pid_path}",
        ])

    lines.extend([
        "timeout 0",
        "tcp-keepalive 300",
        "loglevel notice",
        f"logfile {log_path}",
        "databases 16",
        f"dir {data_path}",
        "dbfilename kortext_graph.rdb",
        "save 900 1",
        "save 300 10",
        "save 60 1000",
        "stop-writes-on-bgsave-error yes",
        "rdbcompression yes",
        "rdbchecksum yes",
        "maxmemory 2gb",
        "maxmemory-policy noeviction",
        f"loadmodule {mod_path}",
        "",
    ])
    return "\n".join(lines)


def generate_qdrant_yaml(home: Path) -> str:
    """Generates dynamically resolved qdrant.yaml without hardcoded paths."""
    resolved_home = home.resolve()
    storage_path = resolved_home / "data" / "qdrant_storage"

    return f"""# Kortext Qdrant Vector Substrate Configuration
# Auto-generated for: {resolved_home}
storage:
  storage_path: {storage_path}

service:
  host: 127.0.0.1
  http_port: 6333
  grpc_port: 6334
  enable_cors: false

log_level: INFO
"""
