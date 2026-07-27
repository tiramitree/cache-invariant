from __future__ import annotations

import io
import tarfile
import zipfile
from pathlib import Path

import pytest

from cache_invariant.fetch import _extract_tar, _extract_zip


def test_tar_same_directory_symlink_is_materialized(tmp_path: Path) -> None:
    archive = tmp_path / "runtime.tar.gz"
    payload = b"registered-library"
    with tarfile.open(archive, "w:gz") as handle:
        regular = tarfile.TarInfo("runtime/libexample.so.1")
        regular.size = len(payload)
        regular.mode = 0o755
        handle.addfile(regular, io.BytesIO(payload))
        alias = tarfile.TarInfo("runtime/libexample.so")
        alias.type = tarfile.SYMTYPE
        alias.linkname = "libexample.so.1"
        handle.addfile(alias)
    output = tmp_path / "out"
    output.mkdir()
    _extract_tar(archive, output)
    alias_path = output / "runtime" / "libexample.so"
    assert alias_path.is_file()
    assert not alias_path.is_symlink()
    assert alias_path.read_bytes() == payload


def test_tar_hardlink_is_rejected(tmp_path: Path) -> None:
    archive = tmp_path / "runtime.tar.gz"
    with tarfile.open(archive, "w:gz") as handle:
        link = tarfile.TarInfo("runtime/link")
        link.type = tarfile.LNKTYPE
        link.linkname = "runtime/target"
        handle.addfile(link)
    output = tmp_path / "out"
    output.mkdir()
    with pytest.raises(ValueError, match="hardlink"):
        _extract_tar(archive, output)


def test_tar_traversal_is_rejected(tmp_path: Path) -> None:
    archive = tmp_path / "runtime.tar.gz"
    with tarfile.open(archive, "w:gz") as handle:
        value = tarfile.TarInfo("../escape")
        value.size = 1
        handle.addfile(value, io.BytesIO(b"x"))
    output = tmp_path / "out"
    output.mkdir()
    with pytest.raises(ValueError, match="unsafe"):
        _extract_tar(archive, output)


def test_zip_traversal_is_rejected(tmp_path: Path) -> None:
    archive = tmp_path / "runtime.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("../escape", b"x")
    output = tmp_path / "out"
    output.mkdir()
    with pytest.raises(ValueError, match="unsafe"):
        _extract_zip(archive, output)
