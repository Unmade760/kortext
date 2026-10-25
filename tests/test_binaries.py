"""
Tests for Kortext Cross-Platform Binary Manager and Platform Detection.
"""
import io
import platform
import shutil
import tarfile
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from kortext.binaries import (
    PlatformInfo,
    detect_platform,
    get_qdrant_download_info,
    get_falkordb_download_info,
    extract_archive_binary,
    generate_falkordb_conf,
    generate_qdrant_yaml,
    verify_binary_executable,
    pull_qdrant_binary,
    pull_falkordb_module,
    BinaryDownloadInfo,
)


def test_detect_platform_current():
    info = detect_platform()
    assert isinstance(info, PlatformInfo)
    assert info.os_name in ("darwin", "linux", "windows")
    assert info.arch in ("arm64", "x86_64", "unknown")


@pytest.mark.parametrize(
    "sys_name, mach, exp_os, exp_arch, exp_macos, exp_linux, exp_win",
    [
        ("Darwin", "arm64", "darwin", "arm64", True, False, False),
        ("Darwin", "x86_64", "darwin", "x86_64", True, False, False),
        ("Linux", "x86_64", "linux", "x86_64", False, True, False),
        ("Linux", "aarch64", "linux", "arm64", False, True, False),
        ("Windows", "AMD64", "windows", "x86_64", False, False, True),
    ],
)
def test_detect_platform_matrix(sys_name, mach, exp_os, exp_arch, exp_macos, exp_linux, exp_win):
    with patch("platform.system", return_value=sys_name), patch("platform.machine", return_value=mach):
        info = detect_platform()
        assert info.os_name == exp_os
        assert info.arch == exp_arch
        assert info.is_macos is exp_macos
        assert info.is_linux is exp_linux
        assert info.is_windows is exp_win


def test_get_qdrant_download_info_matrix():
    # macOS arm64
    p_mac_arm = PlatformInfo("darwin", "arm64", "Darwin", "arm64", True, False, False, True, False)
    info = get_qdrant_download_info(p_mac_arm)
    assert info is not None
    assert "qdrant-aarch64-apple-darwin.tar.gz" in info.url
    assert info.archive_format == "tar.gz"
    assert info.binary_filename == "qdrant"

    # macOS x86_64
    p_mac_x86 = PlatformInfo("darwin", "x86_64", "Darwin", "x86_64", True, False, False, False, True)
    info = get_qdrant_download_info(p_mac_x86)
    assert info is not None
    assert "qdrant-x86_64-apple-darwin.tar.gz" in info.url

    # Linux x86_64
    p_lin_x86 = PlatformInfo("linux", "x86_64", "Linux", "x86_64", False, True, False, False, True)
    info = get_qdrant_download_info(p_lin_x86)
    assert info is not None
    assert "qdrant-x86_64-unknown-linux-gnu.tar.gz" in info.url

    # Linux arm64
    p_lin_arm = PlatformInfo("linux", "arm64", "Linux", "aarch64", False, True, False, True, False)
    info = get_qdrant_download_info(p_lin_arm)
    assert info is not None
    assert "qdrant-aarch64-unknown-linux-musl.tar.gz" in info.url

    # Windows x86_64
    p_win_x86 = PlatformInfo("windows", "x86_64", "Windows", "AMD64", False, False, True, False, True)
    info = get_qdrant_download_info(p_win_x86)
    assert info is not None
    assert "qdrant-x86_64-pc-windows-msvc.zip" in info.url
    assert info.archive_format == "zip"
    assert info.binary_filename == "qdrant.exe"


def test_get_falkordb_download_info_matrix():
    # macOS arm64
    p_mac_arm = PlatformInfo("darwin", "arm64", "Darwin", "arm64", True, False, False, True, False)
    info = get_falkordb_download_info(p_mac_arm)
    assert info is not None
    assert "falkordb-macos-arm64v8.so" in info.url
    assert info.is_raw_binary is True
    assert info.binary_filename == "falkordb.so"

    # Linux x86_64
    p_lin_x86 = PlatformInfo("linux", "x86_64", "Linux", "x86_64", False, True, False, False, True)
    info = get_falkordb_download_info(p_lin_x86)
    assert info is not None
    assert "falkordb-x64.so" in info.url

    # Windows (unsupported natively, returns None)
    p_win_x86 = PlatformInfo("windows", "x86_64", "Windows", "AMD64", False, False, True, False, True)
    info = get_falkordb_download_info(p_win_x86)
    assert info is None


def test_extract_archive_binary_tar_gz(tmp_path):
    # Create fake tar.gz archive in memory with a dummy qdrant executable
    archive_path = tmp_path / "test.tar.gz"
    dest_binary = tmp_path / "bin" / "qdrant"

    bio = io.BytesIO()
    with tarfile.open(fileobj=bio, mode="w:gz") as tar:
        dummy_content = b"#!/bin/sh\necho test\n"
        ti = tarfile.TarInfo(name="qdrant")
        ti.size = len(dummy_content)
        tar.addfile(ti, io.BytesIO(dummy_content))

    archive_path.write_bytes(bio.getvalue())
    extracted = extract_archive_binary(archive_path, dest_binary, "tar.gz", "qdrant")
    assert extracted == dest_binary
    assert dest_binary.exists()
    assert dest_binary.read_bytes() == dummy_content


def test_extract_archive_binary_zip(tmp_path):
    archive_path = tmp_path / "test.zip"
    dest_binary = tmp_path / "bin" / "qdrant.exe"

    bio = io.BytesIO()
    with zipfile.ZipFile(bio, mode="w") as zf:
        dummy_content = b"MZ dummy exe"
        zf.writestr("qdrant.exe", dummy_content)

    archive_path.write_bytes(bio.getvalue())
    extracted = extract_archive_binary(archive_path, dest_binary, "zip", "qdrant.exe")
    assert extracted == dest_binary
    assert dest_binary.exists()
    assert dest_binary.read_bytes() == dummy_content


def test_generate_falkordb_conf(tmp_path):
    home = tmp_path / ".kortext"
    conf = generate_falkordb_conf(home, is_windows=False)
    assert f"dir {home / 'data' / 'falkordb'}" in conf
    assert f"unixsocket {home / 'run' / 'falkordb.sock'}" in conf
    assert f"loadmodule {home / 'bin' / 'falkordb.so'}" in conf

    # Windows version should omit unixsocket
    win_conf = generate_falkordb_conf(home, is_windows=True)
    assert "unixsocket" not in win_conf


def test_generate_qdrant_yaml(tmp_path):
    home = tmp_path / ".kortext"
    yaml_content = generate_qdrant_yaml(home)
    assert f"{home / 'data' / 'qdrant_storage'}" in yaml_content or f"{home / 'qdrant'}" in yaml_content
    assert "http_port: 6333" in yaml_content


def test_pull_qdrant_binary_mocked(tmp_path):
    home = tmp_path / ".kortext"
    # Create fake archive to simulate download
    dummy_tar = tmp_path / "fake_qdrant.tar.gz"
    bio = io.BytesIO()
    with tarfile.open(fileobj=bio, mode="w:gz") as tar:
        dummy_content = b"#!/bin/sh\necho 'qdrant 1.13.4'\n"
        ti = tarfile.TarInfo(name="qdrant")
        ti.size = len(dummy_content)
        tar.addfile(ti, io.BytesIO(dummy_content))
    dummy_tar.write_bytes(bio.getvalue())

    p_info = PlatformInfo("darwin", "arm64", "Darwin", "arm64", True, False, False, True, False)

    def fake_dl(url, dest_path, **kwargs):
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(dummy_tar, dest_path)
        return dest_path

    with patch("kortext.binaries.download_file", side_effect=fake_dl), \
         patch("kortext.binaries.verify_binary_executable", return_value=True):
        res = pull_qdrant_binary(home, platform_info=p_info, force=True)
        assert res.success is True
        assert (home / "bin" / "qdrant").exists()


def test_pull_falkordb_module_mocked(tmp_path):
    home = tmp_path / ".kortext"
    dummy_so = tmp_path / "fake_falkordb.so"
    dummy_so.write_bytes(b"\x7fELFfake")

    p_info = PlatformInfo("darwin", "arm64", "Darwin", "arm64", True, False, False, True, False)

    def fake_dl(url, dest_path, **kwargs):
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(dummy_so, dest_path)
        return dest_path

    with patch("kortext.binaries.download_file", side_effect=fake_dl):
        res = pull_falkordb_module(home, platform_info=p_info, force=True)
        assert res.success is True
        assert (home / "bin" / "falkordb.so").exists()
