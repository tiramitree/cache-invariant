"""Small deterministic and fail-closed helpers."""

from __future__ import annotations

import hashlib
import json
import re
import stat
from pathlib import Path
from typing import Any

SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
SOURCE_REVISION_PATTERN = re.compile(r"^(?:UNCOMMITTED|[0-9a-f]{40})$")
FILE_ATTRIBUTE_REPARSE_POINT = 0x400
DEFAULT_JSON_LIMIT = 1024 * 1024


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def pretty_json(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require_sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or SHA256_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{label} must be a lowercase SHA-256")
    return value


def require_source_revision(value: object, label: str) -> str:
    if not isinstance(value, str) or SOURCE_REVISION_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{label} must be UNCOMMITTED or a lowercase 40-hex revision")
    return value


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _is_reparse(stat_result: object) -> bool:
    attributes = getattr(stat_result, "st_file_attributes", 0)
    return bool(attributes & FILE_ATTRIBUTE_REPARSE_POINT)


def require_regular_file(path: Path, label: str) -> None:
    try:
        metadata = path.lstat()
    except FileNotFoundError as error:
        raise ValueError(f"{label} is missing") from error
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or _is_reparse(metadata)
    ):
        raise ValueError(f"{label} must be a non-reparse regular file")


def reject_reparse_chain(path: Path, label: str) -> None:
    """Reject any existing symlink/junction/reparse component in a local path."""

    absolute = path.absolute()
    anchor = absolute.anchor
    if not anchor or anchor.startswith("\\\\"):
        raise ValueError(f"{label} must use a local absolute-path anchor")
    current = Path(anchor)
    for part in absolute.parts[1:]:
        current = current / part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            break
        if stat.S_ISLNK(metadata.st_mode) or _is_reparse(metadata):
            raise ValueError(f"{label} traverses a reparse point")


def require_plain_directory(path: Path, label: str) -> None:
    reject_reparse_chain(path, label)
    try:
        metadata = path.lstat()
    except FileNotFoundError as error:
        raise ValueError(f"{label} is missing") from error
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or _is_reparse(metadata)
    ):
        raise ValueError(f"{label} must be a non-reparse directory")


def require_plain_path(root: Path, path: Path, label: str) -> None:
    """Reject symlink/junction/reparse traversal between root and path."""

    reject_reparse_chain(root, label)
    reject_reparse_chain(path, label)
    root_resolved = root.resolve(strict=True)
    path_absolute = path.absolute()
    try:
        relative = path_absolute.relative_to(root.absolute())
    except ValueError as error:
        raise ValueError(f"{label} escapes its root") from error
    current = root
    root_meta = current.lstat()
    if stat.S_ISLNK(root_meta.st_mode) or _is_reparse(root_meta):
        raise ValueError(f"{label} root is a reparse point")
    for part in relative.parts:
        current = current / part
        metadata = current.lstat()
        if stat.S_ISLNK(metadata.st_mode) or _is_reparse(metadata):
            raise ValueError(f"{label} traverses a reparse point")
    if not path.resolve(strict=True).is_relative_to(root_resolved):
        raise ValueError(f"{label} resolves outside its root")


def load_json_strict(path: Path, *, max_bytes: int = DEFAULT_JSON_LIMIT) -> Any:
    require_regular_file(path, "JSON input")
    size = path.stat().st_size
    if size <= 0 or size > max_bytes:
        raise ValueError(f"JSON input size is outside 1..{max_bytes} bytes")
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("JSON input is not UTF-8") from error
    return json.loads(
        text,
        object_pairs_hook=_reject_duplicate_pairs,
        parse_constant=lambda value: (_ for _ in ()).throw(
            ValueError(f"non-finite JSON constant: {value}")
        ),
    )


def write_new(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(content)


def require_exact_keys(
    value: object,
    expected: set[str],
    label: str,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise ValueError(f"{label} keys differ: missing={missing}, extra={extra}")
    return value


def require_non_negative_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return value


def require_positive_int(value: object, label: str) -> int:
    result = require_non_negative_int(value, label)
    if result == 0:
        raise ValueError(f"{label} must be positive")
    return result


def safe_relative_path(value: object, label: str) -> Path:
    if (
        not isinstance(value, str)
        or not value
        or "\\" in value
        or value.startswith("/")
        or value.startswith("//")
    ):
        raise ValueError(f"{label} must be a non-empty POSIX relative path")
    path = Path(*value.split("/"))
    if path.is_absolute() or any(
        part in {"", ".", ".."} or ":" in part for part in path.parts
    ):
        raise ValueError(f"{label} is not a safe relative path")
    return path
