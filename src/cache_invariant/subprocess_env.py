"""Minimal child-process environments with no inherited proxy/token state."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _windows_value(name: str) -> str | None:
    target = name.casefold()
    for key, value in os.environ.items():
        if key.casefold() == target:
            return value
    return None


def minimal_environment(
    *,
    runtime_directory: Path,
    temporary_directory: Path,
    api_key: str | None = None,
) -> dict[str, str]:
    """Return only OS/runtime essentials plus an optional one-use API key."""

    if sys.platform == "win32":
        system_root = _windows_value("SystemRoot")
        if system_root is None:
            raise RuntimeError("Windows child environment lacks SystemRoot")
        environment = {
            "COMSPEC": str(Path(system_root) / "System32" / "cmd.exe"),
            "PATH": os.pathsep.join(
                [str(runtime_directory), str(Path(system_root) / "System32")]
            ),
            "SYSTEMROOT": system_root,
            "TEMP": str(temporary_directory),
            "TMP": str(temporary_directory),
            "WINDIR": system_root,
        }
    else:
        environment = {
            "HOME": str(temporary_directory),
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "LD_LIBRARY_PATH": str(runtime_directory),
            "PATH": "/usr/bin:/bin",
            "TMPDIR": str(temporary_directory),
        }
    if api_key is not None:
        environment["LLAMA_API_KEY"] = api_key
    return environment
