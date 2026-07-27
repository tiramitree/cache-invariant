"""Hardened lifecycle for one loopback-only llama.cpp server process."""

from __future__ import annotations

import ctypes
import os
import secrets
import signal
import socket
import subprocess
import sys
import threading
import time
from ctypes import wintypes
from pathlib import Path
from typing import BinaryIO, ClassVar

from .adapter import LlamaCppClient
from .pins import RUNTIME_CONTEXT_TOTAL, RUNTIME_SLOT_COUNT
from .subprocess_env import minimal_environment

CAPTURE_LIMIT = 8192


class _BoundedCapture:
    def __init__(self) -> None:
        self._value = bytearray()
        self._lock = threading.Lock()

    def drain(self, stream: BinaryIO) -> None:
        while True:
            block = stream.read(4096)
            if not block:
                return
            with self._lock:
                self._value.extend(block)
                if len(self._value) > CAPTURE_LIMIT:
                    del self._value[:-CAPTURE_LIMIT]

    def nonempty(self) -> bool:
        with self._lock:
            return bool(self._value)


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as handle:
        handle.bind(("127.0.0.1", 0))
        return int(handle.getsockname()[1])


class _ProcessEntry32W(ctypes.Structure):
    _fields_: ClassVar[list[tuple[str, object]]] = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * 260),
    ]


def _windows_process_tree(root_pid: int) -> list[int]:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.Process32FirstW.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(_ProcessEntry32W),
    ]
    kernel32.Process32FirstW.restype = wintypes.BOOL
    kernel32.Process32NextW.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(_ProcessEntry32W),
    ]
    kernel32.Process32NextW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    snapshot = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)
    invalid = wintypes.HANDLE(-1).value
    if snapshot == invalid:
        raise OSError("process-tree snapshot failed")
    try:
        entry = _ProcessEntry32W()
        entry.dwSize = ctypes.sizeof(entry)
        parents: dict[int, int] = {}
        ok = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while ok:
            parents[int(entry.th32ProcessID)] = int(entry.th32ParentProcessID)
            ok = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)
    result = {root_pid}
    changed = True
    while changed:
        changed = False
        for pid, parent in parents.items():
            if parent in result and pid not in result:
                result.add(pid)
                changed = True
    return sorted(result)


def _windows_open_wait_handles(pids: list[int]) -> dict[int, int]:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    handles: dict[int, int] = {}
    for pid in pids:
        ctypes.set_last_error(0)
        handle = kernel32.OpenProcess(0x00100000, False, pid)
        if handle:
            handles[pid] = handle
            continue
        error = ctypes.get_last_error()
        # ERROR_INVALID_PARAMETER is the documented race when a snapshotted
        # process has already exited. Access-denied and all other errors fail.
        if error != 87:
            for opened in handles.values():
                kernel32.CloseHandle(opened)
            raise OSError("could not obtain a Windows process-tree wait handle")
    return handles


def _windows_wait_and_close(handles: dict[int, int], timeout_ms: int) -> None:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    try:
        for handle in handles.values():
            result = kernel32.WaitForSingleObject(handle, timeout_ms)
            if result == 0x00000102:
                raise RuntimeError("Windows child process tree did not exit")
            if result == 0xFFFFFFFF:
                raise OSError("waiting for Windows child process failed")
    finally:
        for handle in handles.values():
            kernel32.CloseHandle(handle)


class ServerProcess:
    """One registered server process with authenticated loopback transport."""

    def __init__(
        self,
        *,
        server: Path,
        model: Path,
        slot_directory: Path,
        temporary_directory: Path,
    ) -> None:
        self.server = server
        self.model = model
        self.slot_directory = slot_directory
        self.temporary_directory = temporary_directory
        self.port = _free_loopback_port()
        self.api_key = secrets.token_urlsafe(32)
        self.process: subprocess.Popen[bytes] | None = None
        self.stdout_capture = _BoundedCapture()
        self.stderr_capture = _BoundedCapture()
        self._threads: list[threading.Thread] = []

    @property
    def client(self) -> LlamaCppClient:
        if self.process is None:
            raise RuntimeError("server process has not started")
        return LlamaCppClient(port=self.port, api_key=self.api_key)

    def start(self) -> LlamaCppClient:
        if self.process is not None:
            raise RuntimeError("server process was already started")
        self.slot_directory.mkdir(parents=True, exist_ok=True)
        environment = minimal_environment(
            runtime_directory=self.server.parent,
            temporary_directory=self.temporary_directory,
            api_key=self.api_key,
        )
        command = [
            os.fspath(self.server),
            "--model",
            os.fspath(self.model),
            "--host",
            "127.0.0.1",
            "--port",
            str(self.port),
            "--parallel",
            str(RUNTIME_SLOT_COUNT),
            "--ctx-size",
            str(RUNTIME_CONTEXT_TOTAL),
            "--threads",
            "2",
            "--threads-batch",
            "2",
            "--n-gpu-layers",
            "0",
            "--offline",
            "--no-webui",
            "--slots",
            "--slot-save-path",
            os.fspath(self.slot_directory),
            "--cache-prompt",
            "--log-disable",
        ]
        kwargs: dict[str, object] = {
            "cwd": os.fspath(self.server.parent),
            "env": environment,
            "stderr": subprocess.PIPE,
            "stdout": subprocess.PIPE,
        }
        if sys.platform == "win32":
            kwargs["creationflags"] = (
                subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
            )
        else:
            kwargs["start_new_session"] = True
        self.process = subprocess.Popen(command, **kwargs)
        assert self.process.stdout is not None
        assert self.process.stderr is not None
        self._threads = [
            threading.Thread(
                target=self.stdout_capture.drain,
                args=(self.process.stdout,),
                daemon=True,
            ),
            threading.Thread(
                target=self.stderr_capture.drain,
                args=(self.process.stderr,),
                daemon=True,
            ),
        ]
        for thread in self._threads:
            thread.start()

        started = time.monotonic()
        while time.monotonic() - started < 30.0:
            if self.process.poll() is not None:
                code = self.process.returncode
                self.stop()
                raise RuntimeError(f"server exited before readiness with exit {code}")
            if self.client.health_ok():
                return self.client
            time.sleep(0.05)
        self.stop()
        raise TimeoutError("server did not become ready within the bounded wait")

    def stop(self) -> None:
        process = self.process
        if process is None:
            return
        if process.poll() is None:
            if sys.platform == "win32":
                pids = _windows_process_tree(process.pid)
                handles = _windows_open_wait_handles(pids)
                if process.pid not in handles and process.poll() is None:
                    _windows_wait_and_close(handles, 0)
                    raise RuntimeError(
                        "Windows root process lacked a verified wait handle"
                    )
                system_root = os.environ.get("SystemRoot")
                if system_root is None:
                    _windows_wait_and_close(handles, 0)
                    raise RuntimeError("Windows process control lacks SystemRoot")
                taskkill = Path(system_root) / "System32" / "taskkill.exe"
                taskkill_result = subprocess.run(
                    [
                        os.fspath(taskkill),
                        "/PID",
                        str(process.pid),
                        "/T",
                        "/F",
                    ],
                    capture_output=True,
                    check=False,
                    timeout=15.0,
                    env=minimal_environment(
                        runtime_directory=self.server.parent,
                        temporary_directory=self.temporary_directory,
                    ),
                )
                try:
                    process.wait(timeout=10.0)
                finally:
                    _windows_wait_and_close(handles, 10_000)
                if taskkill_result.returncode != 0 and process.returncode is None:
                    raise RuntimeError("Windows process-tree termination failed")
            else:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=10.0)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    process.wait(timeout=10.0)
                try:
                    os.killpg(process.pid, 0)
                except ProcessLookupError:
                    pass
                else:
                    raise RuntimeError("POSIX server process remained alive")
        else:
            process.wait(timeout=1.0)
        if process.poll() is None:
            raise RuntimeError("server process did not exit")
        for thread in self._threads:
            thread.join(timeout=2.0)
        self.process = None

    def __enter__(self) -> LlamaCppClient:
        return self.start()

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.stop()
