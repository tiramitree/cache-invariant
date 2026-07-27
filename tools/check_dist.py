"""Verify licensing, notices, and artifact boundaries in wheel and sdist."""

from __future__ import annotations

import email
import stat
import tarfile
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
SOURCE = ROOT / "src" / "cache_invariant"
FORBIDDEN_SUFFIXES = (
    ".7z",
    ".bin",
    ".dll",
    ".dylib",
    ".exe",
    ".gguf",
    ".node",
    ".pdb",
    ".so",
    ".tar",
    ".tar.bz2",
    ".tar.gz",
    ".tar.xz",
    ".tgz",
    ".zip",
)
SDIST_REPRODUCIBILITY_FILES = {
    ".github/workflows/ci.yml",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "docs/ARCHITECTURE.md",
    "docs/CLAIM_BOUNDARIES.md",
    "docs/PRIOR_ART.md",
    "docs/PRIVACY.md",
    "evidence/README.md",
    "evidence/reference-v0.1.0-windows/evidence.json",
    "evidence/reference-v0.1.0-windows/junit.xml",
    "evidence/reference-v0.1.0-windows/manifest.json",
    "tests/conftest.py",
    "tests/test_adapter.py",
    "tests/test_dist_check.py",
    "tests/test_fetch.py",
    "tests/test_oracle.py",
    "tests/test_process.py",
    "tests/test_privacy_scan.py",
    "tests/test_registration.py",
    "tests/test_util.py",
    "tests/test_verify.py",
    "tools/check_dist.py",
    "tools/privacy_scan.py",
}


def safe_name(name: str, kind: str) -> None:
    if "\\" in name:
        raise SystemExit(f"{kind} contains a backslash path")
    pure = PurePosixPath(name)
    if (
        pure.is_absolute()
        or not pure.parts
        or any(part in {"", ".", ".."} or ":" in part for part in pure.parts)
    ):
        raise SystemExit(f"{kind} contains an unsafe path")


def require_unique_names(names: list[str], kind: str) -> None:
    if len(names) != len(set(names)):
        raise SystemExit(f"{kind} contains duplicate member names")


def reject_forbidden_names(names: set[str], kind: str) -> None:
    for name in names:
        lowered = name.lower()
        if lowered.endswith(FORBIDDEN_SUFFIXES):
            raise SystemExit(f"{kind} contains a forbidden runtime/model member")


def require_names(names: set[str], kind: str) -> None:
    required_suffixes = {
        "LICENSE",
        "NOTICE",
        "THIRD_PARTY_NOTICES.md",
        "third_party/llama.cpp-LICENSE.txt",
        "src/cache_invariant/_vendor/llama2c_gguf.py",
    }
    for suffix in required_suffixes:
        suffix_parts = PurePosixPath(suffix).parts
        if not any(
            PurePosixPath(name).parts[-len(suffix_parts) :] == suffix_parts
            for name in names
        ):
            raise SystemExit(f"{kind} missing required notice/source: {suffix}")
    reject_forbidden_names(names, kind)


def require_sdist_reproducibility_files(names: set[str]) -> None:
    for suffix in sorted(SDIST_REPRODUCIBILITY_FILES):
        suffix_parts = PurePosixPath(suffix).parts
        if not any(
            PurePosixPath(name).parts[-len(suffix_parts) :] == suffix_parts
            for name in names
        ):
            raise SystemExit(f"sdist missing reproducibility file: {suffix}")


def require_wheel_source_parity(
    handle: zipfile.ZipFile,
    names: set[str],
) -> None:
    current = {
        path.relative_to(SOURCE).as_posix(): path for path in SOURCE.rglob("*.py")
    }
    packaged = {
        name.removeprefix("cache_invariant/"): name
        for name in names
        if name.startswith("cache_invariant/") and name.endswith(".py")
    }
    if set(packaged) != set(current):
        raise SystemExit("wheel package source file set differs from current source")
    for relative, path in current.items():
        if handle.read(packaged[relative]) != path.read_bytes():
            raise SystemExit("wheel package source bytes differ from current source")


def require_sdist_source_parity(
    handle: tarfile.TarFile,
    names: set[str],
) -> None:
    current = {
        path.relative_to(SOURCE).as_posix(): path for path in SOURCE.rglob("*.py")
    }
    packaged: dict[str, str] = {}
    marker = "/src/cache_invariant/"
    for name in names:
        if marker in name and name.endswith(".py"):
            packaged[name.split(marker, maxsplit=1)[1]] = name
    if set(packaged) != set(current):
        raise SystemExit("sdist package source file set differs from current source")
    for relative, path in current.items():
        member = handle.extractfile(packaged[relative])
        if member is None or member.read() != path.read_bytes():
            raise SystemExit("sdist package source bytes differ from current source")


def main() -> None:
    wheels = list(DIST.glob("*.whl"))
    sdists = list(DIST.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        raise SystemExit("expected exactly one wheel and one sdist")
    with zipfile.ZipFile(wheels[0]) as handle:
        raw_wheel_names = [info.filename for info in handle.infolist()]
        require_unique_names(raw_wheel_names, "wheel")
        wheel_names: set[str] = set()
        for info in handle.infolist():
            safe_name(info.filename, "wheel")
            mode = (info.external_attr >> 16) & 0xFFFF
            file_type = stat.S_IFMT(mode)
            if info.is_dir() or file_type not in {0, stat.S_IFREG}:
                raise SystemExit("wheel contains a directory or special entry")
            wheel_names.add(info.filename)
        metadata_names = [
            name for name in wheel_names if name.endswith(".dist-info/METADATA")
        ]
        if len(metadata_names) != 1:
            raise SystemExit("wheel METADATA file set differs")
        metadata = email.message_from_bytes(handle.read(metadata_names[0]))
        if metadata.get("Author") != "tiramitree":
            raise SystemExit("wheel author is not exactly tiramitree")
        if metadata.get("License-Expression") != "Apache-2.0 AND MIT":
            raise SystemExit("wheel license expression differs")
        require_wheel_source_parity(handle, wheel_names)
    # Wheel paths differ from source/sdist paths for package files.
    adjusted = set(wheel_names)
    for name in wheel_names:
        if name.endswith("cache_invariant/_vendor/llama2c_gguf.py"):
            adjusted.add("src/" + name)
        if name.endswith("cache_invariant/notices/NOTICE"):
            adjusted.add("NOTICE")
        if name.endswith("cache_invariant/notices/THIRD_PARTY_NOTICES.md"):
            adjusted.add("THIRD_PARTY_NOTICES.md")
        if name.endswith(".dist-info/licenses/LICENSE"):
            adjusted.add("LICENSE")
        if name.endswith(".dist-info/licenses/third_party/llama.cpp-LICENSE.txt"):
            adjusted.add("third_party/llama.cpp-LICENSE.txt")
    require_names(adjusted, "wheel")
    with tarfile.open(sdists[0], "r:gz") as handle:
        members = handle.getmembers()
        require_unique_names([member.name for member in members], "sdist")
        names: set[str] = set()
        for member in members:
            safe_name(member.name, "sdist")
            if not (member.isdir() or member.isfile()):
                raise SystemExit("sdist contains a link/device/special entry")
            names.add(member.name)
        require_names(names, "sdist")
        require_sdist_reproducibility_files(names)
        require_sdist_source_parity(handle, names)
        pyprojects = [name for name in names if name.endswith("/pyproject.toml")]
        if len(pyprojects) != 1:
            raise SystemExit("sdist pyproject file set differs")
        pyproject = handle.extractfile(pyprojects[0])
        if pyproject is None:
            raise SystemExit("sdist pyproject could not be read")
        project_text = pyproject.read().decode("utf-8")
        if 'authors = [{ name = "tiramitree" }]' not in project_text:
            raise SystemExit("sdist author metadata differs")
        if 'license = "Apache-2.0 AND MIT"' not in project_text:
            raise SystemExit("sdist license expression differs")
    with zipfile.ZipFile(wheels[0]) as handle:
        vendor_names = [
            name
            for name in handle.namelist()
            if name.endswith("cache_invariant/_vendor/llama2c_gguf.py")
        ]
        if len(vendor_names) != 1:
            raise SystemExit("wheel converter file set differs")
        vendor = handle.read(vendor_names[0]).decode("utf-8")
        if not vendor.startswith("# SPDX-License-Identifier: MIT\n"):
            raise SystemExit("wheel converter lacks the exact MIT SPDX header")
        if "pinned model-card metadata: mit" not in vendor:
            raise SystemExit("wheel converter fixture metadata boundary differs")
        if "MIT-licensed Karpathy" in vendor:
            raise SystemExit("wheel converter overstates the fixture license record")
        notice_names = [
            name
            for name in handle.namelist()
            if name.endswith("cache_invariant/notices/THIRD_PARTY_NOTICES.md")
        ]
        if len(notice_names) != 1:
            raise SystemExit("wheel third-party notice file set differs")
        notice = handle.read(notice_names[0]).decode("utf-8")
        required_notice_boundaries = (
            "Source-project root license: MIT",
            "not a blanket legal conclusion",
            "cross-platform transitive resolution is not",
            "complete Python environment is",
        )
        if not all(value in notice for value in required_notice_boundaries):
            raise SystemExit("wheel third-party notice boundaries differ")
    print("dist-check: clean")


if __name__ == "__main__":
    main()
