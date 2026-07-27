"""Hash-pinned downloads and fresh, safe runtime extraction."""

from __future__ import annotations

import os
import platform
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from .pins import (
    CHECKPOINT,
    FIXTURE_SOURCE_REVISION,
    GGUF_BYTES,
    GGUF_SHA256,
    RUNTIME_ASSETS,
    RUNTIME_LOCK_SCHEMA,
    RUNTIME_RELEASE,
    RUNTIME_SERVER_PINS,
    RUNTIME_SOURCE_COMMIT,
    RUNTIME_VERSION_LINE,
    TOKENIZER,
    Artifact,
)
from .subprocess_env import minimal_environment
from .util import (
    load_json_strict,
    pretty_json,
    reject_reparse_chain,
    require_exact_keys,
    require_plain_directory,
    require_plain_path,
    require_positive_int,
    require_regular_file,
    require_sha256,
    safe_relative_path,
    sha256_file,
    write_new,
)


def current_platform_key() -> str:
    machine = platform.machine().lower()
    if machine not in {"amd64", "x86_64"}:
        raise RuntimeError(f"unsupported machine architecture: {machine}")
    if sys.platform == "win32":
        return "windows-x86_64"
    if sys.platform.startswith("linux"):
        try:
            os_release = platform.freedesktop_os_release()
        except OSError as error:
            raise RuntimeError("Linux host lacks an OS release identity") from error
        if os_release.get("ID", "").lower() != "ubuntu":
            raise RuntimeError("the registered Linux runtime asset is Ubuntu-only")
        return "ubuntu-x86_64"
    raise RuntimeError(f"unsupported operating system: {sys.platform}")


def _download(artifact: Artifact, output: Path) -> None:
    if output.exists():
        raise FileExistsError(f"refusing to overwrite {output.name}")
    output.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(
        artifact.url,
        headers={"User-Agent": "cache-invariant/0.1 pinned-fetch"},
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=60.0) as response:
            with output.open("xb") as handle:
                total = 0
                for block in iter(lambda: response.read(1024 * 1024), b""):
                    total += len(block)
                    if total > artifact.bytes:
                        raise ValueError(
                            f"{artifact.name} exceeded registered byte count"
                        )
                    handle.write(block)
        if output.stat().st_size != artifact.bytes:
            raise ValueError(
                f"{artifact.name} byte count drift: "
                f"{output.stat().st_size} != {artifact.bytes}"
            )
        actual = sha256_file(output)
        if actual != artifact.sha256:
            raise ValueError(
                f"{artifact.name} SHA-256 drift: {actual} != {artifact.sha256}"
            )
    except BaseException:
        if output.exists():
            output.unlink()
        raise


def _safe_member_parts(name: str) -> tuple[str, ...]:
    normalized = name.replace("\\", "/")
    pure = PurePosixPath(normalized)
    if (
        pure.is_absolute()
        or not pure.parts
        or any(part in {"", ".", ".."} or ":" in part for part in pure.parts)
    ):
        raise ValueError("archive contains an unsafe member path")
    return pure.parts


def _extract_zip(archive: Path, destination: Path) -> None:
    with zipfile.ZipFile(archive) as handle:
        for member in handle.infolist():
            parts = _safe_member_parts(member.filename)
            mode = (member.external_attr >> 16) & 0xFFFF
            if stat.S_ISLNK(mode):
                raise ValueError("zip archive contains a link")
            target = destination.joinpath(*parts)
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with handle.open(member) as source, target.open("xb") as output:
                shutil.copyfileobj(source, output)


def _extract_tar(archive: Path, destination: Path) -> None:
    with tarfile.open(archive, mode="r:gz") as handle:
        links: list[tarfile.TarInfo] = []
        for member in handle.getmembers():
            parts = _safe_member_parts(member.name)
            if member.islnk():
                raise ValueError("tar archive contains a hardlink")
            if member.issym():
                links.append(member)
                continue
            if not (member.isdir() or member.isfile()):
                raise ValueError("tar archive contains an unsupported member")
            target = destination.joinpath(*parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            source = handle.extractfile(member)
            if source is None:
                raise ValueError("tar archive regular member could not be read")
            target.parent.mkdir(parents=True, exist_ok=True)
            with source, target.open("xb") as output:
                shutil.copyfileobj(source, output)
            target.chmod(0o755 if member.mode & 0o111 else 0o644)

        # The exact Ubuntu asset contains ten same-directory library aliases.
        # Resolve and copy them as regular files. This admits no link in the
        # resulting run tree and still rejects unknown traversal or cycles.
        unresolved = list(links)
        while unresolved:
            remaining: list[tarfile.TarInfo] = []
            progress = False
            for member in unresolved:
                if (
                    not member.linkname
                    or "/" in member.linkname
                    or "\\" in member.linkname
                    or member.linkname in {".", ".."}
                    or ":" in member.linkname
                ):
                    raise ValueError(
                        "tar symlink is not a same-directory relative alias"
                    )
                alias = destination.joinpath(*_safe_member_parts(member.name))
                target = alias.parent / member.linkname
                if target.exists():
                    require_regular_file(target, "tar alias target")
                    alias.parent.mkdir(parents=True, exist_ok=True)
                    with target.open("rb") as source, alias.open("xb") as output:
                        shutil.copyfileobj(source, output)
                    alias.chmod(target.stat().st_mode & 0o777)
                    progress = True
                else:
                    remaining.append(member)
            if not progress:
                raise ValueError("tar symlink chain is unresolved or cyclic")
            unresolved = remaining


def _find_server(runtime: Path) -> Path:
    expected = "llama-server.exe" if sys.platform == "win32" else "llama-server"
    matches = []
    for value in runtime.rglob(expected):
        try:
            require_regular_file(value, "runtime server candidate")
        except ValueError:
            continue
        matches.append(value)
    if len(matches) != 1:
        raise ValueError("runtime archive must contain exactly one server")
    return matches[0]


def read_server_version(server: Path) -> str:
    completed = subprocess.run(
        [os.fspath(server), "--version"],
        capture_output=True,
        check=False,
        cwd=os.fspath(server.parent),
        env=minimal_environment(
            runtime_directory=server.parent,
            temporary_directory=server.parent,
        ),
        timeout=15.0,
    )
    diagnostic = (completed.stdout + completed.stderr)[:4096].decode(
        "utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        raise RuntimeError(f"server --version failed with exit {completed.returncode}")
    if RUNTIME_VERSION_LINE not in diagnostic:
        raise ValueError("server version drift: registered line is absent")
    return RUNTIME_VERSION_LINE


def _extract_registered_runtime(
    archive: Path,
    destination: Path,
    platform_key: str,
) -> Path:
    asset = RUNTIME_ASSETS[platform_key]
    server_pin = RUNTIME_SERVER_PINS[platform_key]
    require_regular_file(archive, "runtime archive")
    if archive.stat().st_size != asset.bytes or sha256_file(archive) != asset.sha256:
        raise ValueError("runtime archive no longer matches its registered pin")
    reject_reparse_chain(destination, "runtime extraction destination")
    if destination.exists() and any(destination.iterdir()):
        raise FileExistsError("runtime extraction destination is not empty")
    destination.mkdir(parents=True, exist_ok=True)
    require_plain_directory(destination, "runtime extraction destination")
    if asset.name.endswith(".zip"):
        _extract_zip(archive, destination)
    elif asset.name.endswith(".tar.gz"):
        _extract_tar(archive, destination)
    else:
        raise ValueError("registered runtime archive type is unsupported")
    server = _find_server(destination)
    if server.relative_to(destination).as_posix() != server_pin["archive_path"]:
        raise ValueError("runtime server archive path is not registered")
    if (
        server.stat().st_size != server_pin["bytes"]
        or sha256_file(server) != server_pin["sha256"]
    ):
        raise ValueError("runtime server file is not registered")
    read_server_version(server)
    return server


def extract_fresh_runtime(
    archive: Path,
    destination: Path,
    platform_key: str,
) -> Path:
    """Re-hash and freshly extract the exact runtime used for one run."""

    if platform_key != current_platform_key():
        raise ValueError("runtime extraction platform does not match current host")
    return _extract_registered_runtime(archive, destination, platform_key)


def fetch(destination: Path, platform_key: str | None = None) -> Path:
    key = current_platform_key() if platform_key is None else platform_key
    if key != current_platform_key():
        raise ValueError("fetch platform must match the current host")
    asset = RUNTIME_ASSETS.get(key)
    if asset is None:
        raise ValueError(f"unregistered runtime platform: {key}")
    reject_reparse_chain(destination, "fetch destination")
    if destination.exists() and any(destination.iterdir()):
        raise FileExistsError("fetch destination exists and is not empty")
    destination.mkdir(parents=True, exist_ok=True)
    require_plain_directory(destination, "fetch destination")

    archive = destination / "downloads" / asset.name
    checkpoint = destination / "fixture" / CHECKPOINT.name
    tokenizer = destination / "fixture" / TOKENIZER.name
    _download(asset, archive)
    _download(CHECKPOINT, checkpoint)
    _download(TOKENIZER, tokenizer)

    with tempfile.TemporaryDirectory(
        prefix=".runtime-stage-",
        dir=destination,
    ) as staging_value:
        server = _extract_registered_runtime(
            archive,
            Path(staging_value),
            key,
        )
        server_sha256 = sha256_file(server)
    server_pin = RUNTIME_SERVER_PINS[key]
    lock = {
        "converted_model": {
            "bytes": GGUF_BYTES,
            "relative_path": "fixture/stories260K-f32.gguf",
            "sha256": GGUF_SHA256,
        },
        "fixture": {
            "checkpoint": {
                "bytes": CHECKPOINT.bytes,
                "relative_path": f"fixture/{CHECKPOINT.name}",
                "sha256": CHECKPOINT.sha256,
            },
            "source_revision": FIXTURE_SOURCE_REVISION,
            "tokenizer": {
                "bytes": TOKENIZER.bytes,
                "relative_path": f"fixture/{TOKENIZER.name}",
                "sha256": TOKENIZER.sha256,
            },
        },
        "runtime": {
            "archive_relative_path": f"downloads/{asset.name}",
            "asset_bytes": asset.bytes,
            "asset_name": asset.name,
            "asset_sha256": asset.sha256,
            "platform": key,
            "release": RUNTIME_RELEASE,
            "server_archive_path": server_pin["archive_path"],
            "server_bytes": server_pin["bytes"],
            "server_sha256": server_sha256,
            "source_commit": RUNTIME_SOURCE_COMMIT,
            "version_line": RUNTIME_VERSION_LINE,
        },
        "schema": RUNTIME_LOCK_SCHEMA,
    }
    lock_path = destination / "runtime-lock.json"
    write_new(lock_path, pretty_json(lock))
    validate_lock(lock_path, require_model=False)
    return lock_path


def _validate_file_record(
    root: Path,
    value: object,
    label: str,
    *,
    expected_bytes: int,
    expected_relative_path: str,
    expected_sha256: str,
    require_exists: bool,
) -> Path:
    record = require_exact_keys(
        value,
        {"bytes", "relative_path", "sha256"},
        label,
    )
    if require_positive_int(record["bytes"], f"{label}.bytes") != expected_bytes:
        raise ValueError(f"{label}.bytes is not registered")
    if require_sha256(record["sha256"], f"{label}.sha256") != expected_sha256:
        raise ValueError(f"{label}.sha256 is not registered")
    relative = safe_relative_path(record["relative_path"], f"{label}.relative_path")
    if relative.as_posix() != expected_relative_path:
        raise ValueError(f"{label}.relative_path is not registered")
    path = root / relative
    if require_exists:
        require_regular_file(path, label)
        require_plain_path(root, path, label)
        if path.stat().st_size != expected_bytes:
            raise ValueError(f"{label} local byte count differs")
        if sha256_file(path) != expected_sha256:
            raise ValueError(f"{label} local SHA-256 differs")
    return path


def validate_lock(
    lock_path: Path,
    *,
    require_model: bool,
) -> dict[str, Any]:
    require_regular_file(lock_path, "runtime lock input")
    reject_reparse_chain(lock_path, "runtime lock input")
    lock_path = lock_path.resolve(strict=True)
    root = lock_path.parent
    require_regular_file(lock_path, "runtime lock")
    require_plain_path(root, lock_path, "runtime lock")
    value = require_exact_keys(
        load_json_strict(lock_path),
        {"converted_model", "fixture", "runtime", "schema"},
        "runtime lock",
    )
    if value["schema"] != RUNTIME_LOCK_SCHEMA:
        raise ValueError("runtime lock schema is not registered")
    runtime = require_exact_keys(
        value["runtime"],
        {
            "archive_relative_path",
            "asset_bytes",
            "asset_name",
            "asset_sha256",
            "platform",
            "release",
            "server_archive_path",
            "server_bytes",
            "server_sha256",
            "source_commit",
            "version_line",
        },
        "runtime",
    )
    platform_key = runtime["platform"]
    if platform_key != current_platform_key():
        raise ValueError("runtime lock platform does not match current host")
    asset = RUNTIME_ASSETS.get(platform_key)
    if asset is None:
        raise ValueError("runtime platform is not registered")
    server_pin = RUNTIME_SERVER_PINS[platform_key]
    expected_runtime = {
        "asset_bytes": asset.bytes,
        "asset_name": asset.name,
        "asset_sha256": asset.sha256,
        "archive_relative_path": f"downloads/{asset.name}",
        "release": RUNTIME_RELEASE,
        "server_archive_path": server_pin["archive_path"],
        "server_bytes": server_pin["bytes"],
        "server_sha256": server_pin["sha256"],
        "source_commit": RUNTIME_SOURCE_COMMIT,
        "version_line": RUNTIME_VERSION_LINE,
    }
    for key, expected in expected_runtime.items():
        if runtime[key] != expected:
            raise ValueError(f"runtime.{key} is not registered")
    archive_relative = safe_relative_path(
        runtime["archive_relative_path"],
        "runtime.archive_relative_path",
    )
    archive = root / archive_relative
    require_regular_file(archive, "runtime archive")
    require_plain_path(root, archive, "runtime archive")
    if archive.stat().st_size != asset.bytes:
        raise ValueError("runtime archive local byte count differs")
    if sha256_file(archive) != asset.sha256:
        raise ValueError("runtime archive local SHA-256 differs")

    fixture = require_exact_keys(
        value["fixture"],
        {"checkpoint", "source_revision", "tokenizer"},
        "fixture",
    )
    if fixture["source_revision"] != FIXTURE_SOURCE_REVISION:
        raise ValueError("fixture source revision is not registered")
    checkpoint = _validate_file_record(
        root,
        fixture["checkpoint"],
        "fixture.checkpoint",
        expected_bytes=CHECKPOINT.bytes,
        expected_relative_path=f"fixture/{CHECKPOINT.name}",
        expected_sha256=CHECKPOINT.sha256,
        require_exists=True,
    )
    tokenizer = _validate_file_record(
        root,
        fixture["tokenizer"],
        "fixture.tokenizer",
        expected_bytes=TOKENIZER.bytes,
        expected_relative_path=f"fixture/{TOKENIZER.name}",
        expected_sha256=TOKENIZER.sha256,
        require_exists=True,
    )
    model = _validate_file_record(
        root,
        value["converted_model"],
        "converted_model",
        expected_bytes=GGUF_BYTES,
        expected_relative_path="fixture/stories260K-f32.gguf",
        expected_sha256=GGUF_SHA256,
        require_exists=require_model,
    )
    return {
        "archive": archive,
        "asset": asset,
        "checkpoint": checkpoint,
        "lock": value,
        "model": model,
        "platform": platform_key,
        "tokenizer": tokenizer,
    }
