from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

from cache_invariant.process import (
    ServerProcess,
    _windows_open_wait_handles,
    _windows_wait_and_close,
)
from cache_invariant.subprocess_env import minimal_environment


def test_minimal_environment_excludes_inherited_sensitive_names(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("HTTP_PROXY", "http://example.invalid")
    monkeypatch.setenv("GITHUB_TOKEN", "not-real")
    monkeypatch.setenv("LLAMA_UNREGISTERED", "not-real")
    value = minimal_environment(
        runtime_directory=tmp_path,
        temporary_directory=tmp_path,
        api_key="one-use",
    )
    assert value["LLAMA_API_KEY"] == "one-use"
    assert "HTTP_PROXY" not in value
    assert "GITHUB_TOKEN" not in value
    assert "LLAMA_UNREGISTERED" not in value


def test_stop_terminates_spawned_process_tree(tmp_path: Path) -> None:
    child_code = "import time; time.sleep(60)"
    parent_code = (
        "import subprocess,sys,time;"
        f"p=subprocess.Popen([sys.executable,'-c',{child_code!r}]);"
        "print(p.pid,flush=True);"
        "time.sleep(60)"
    )
    kwargs: dict[str, object] = {
        "stderr": subprocess.PIPE,
        "stdout": subprocess.PIPE,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = (
            subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        )
    else:
        kwargs["start_new_session"] = True
    process = subprocess.Popen([sys.executable, "-c", parent_code], **kwargs)
    assert process.stdout is not None
    child_pid = int(process.stdout.readline().decode("ascii").strip())
    child_handle = (
        _windows_open_wait_handles([child_pid]) if sys.platform == "win32" else {}
    )
    if sys.platform == "win32":
        assert child_pid in child_handle

    wrapper = ServerProcess(
        server=Path(sys.executable),
        model=tmp_path / "unused",
        slot_directory=tmp_path / "slots",
        temporary_directory=tmp_path,
    )
    wrapper.process = process
    wrapper.stop()
    assert wrapper.process is None
    assert process.poll() is not None
    if sys.platform == "win32":
        _windows_wait_and_close(child_handle, 0)
    else:
        deadline = time.monotonic() + 5.0
        while True:
            try:
                os.kill(child_pid, 0)
            except ProcessLookupError:
                break
            if time.monotonic() >= deadline:
                raise AssertionError("spawned descendant remained alive")
            time.sleep(0.02)
