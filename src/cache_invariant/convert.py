"""Strict conversion entrypoint for the registered tiny fixture."""

from __future__ import annotations

import importlib.metadata
from pathlib import Path

from .fetch import validate_lock
from .pins import CONVERSION_DEPENDENCIES, GGUF_BYTES, GGUF_SHA256
from .util import sha256_file


def _require_dependency_versions() -> None:
    for distribution, expected in CONVERSION_DEPENDENCIES.items():
        try:
            actual = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError as error:
            raise RuntimeError(
                f"missing conversion dependency {distribution}=={expected}"
            ) from error
        if actual != expected:
            raise RuntimeError(
                f"conversion dependency drift for {distribution}: "
                f"{actual} != {expected}"
            )


def convert_from_lock(lock_path: Path) -> Path:
    resolved = validate_lock(lock_path, require_model=False)
    output: Path = resolved["model"]
    if output.exists():
        raise FileExistsError(f"refusing to overwrite {output.name}")
    _require_dependency_versions()

    from ._vendor.llama2c_gguf import convert

    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        convert(resolved["checkpoint"], resolved["tokenizer"], output)
        actual_bytes = output.stat().st_size
        actual_sha256 = sha256_file(output)
        if actual_bytes != GGUF_BYTES or actual_sha256 != GGUF_SHA256:
            raise ValueError(
                f"converted GGUF drift: bytes={actual_bytes}, sha256={actual_sha256}"
            )
    except BaseException:
        if output.exists():
            output.unlink()
        raise
    validate_lock(lock_path, require_model=True)
    return output
