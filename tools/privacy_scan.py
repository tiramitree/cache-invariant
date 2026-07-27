"""Fail-closed source privacy scan for the publication candidate."""

from __future__ import annotations

import re
import stat
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRECTORIES = {
    ".cache",
    ".git",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "candidate-evidence",
    "dist",
}
BINARY_SUFFIXES = {
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
}
PATTERNS = {
    "china-phone": re.compile(
        r"(?<![A-Za-z0-9])(?:\+?86[-\s]?)?1[3-9]\d{9}(?![A-Za-z0-9])"
    ),
    "email": re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b"),
    "non-loopback-ipv4": re.compile(
        r"(?<![\d.])(?!127\.)(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}"
        r"(?:25[0-5]|2[0-4]\d|1?\d?\d)(?![\d.])"
    ),
    "private-key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "secret-token": re.compile(
        r"(?i)\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{20,})\b"
    ),
    "unc-path": re.compile(r"\\\\[^\\\r\n]+\\[^\\\r\n]+"),
    "unix-home": re.compile(r"(?i)(?:^|[\s\"'])/(?:home|users)/[^/\s\"']+/"),
    "user-home-shortcut": re.compile(r"(?<![A-Za-z0-9])~[/\\]"),
    "windows-path": re.compile(r"(?i)\b[A-Z]:[\\/]"),
    "wsl-user-path": re.compile(r"(?i)(?:^|[\s\"'])/mnt/[a-z]/users/[^/\s\"']+/"),
}
SENSITIVE_PATH_PARTS = {
    ".env",
    "credentials",
    "id_rsa",
    "private_key",
    "secrets",
}
AUDITED_TEST_FIXTURES = {
    ("tests/test_util.py", "windows-path"): {
        '"' + chr(67) + ':/drive",',
    },
}


def _known_binary_name(path: Path) -> bool:
    lowered = path.name.casefold()
    return any(lowered.endswith(suffix) for suffix in BINARY_SUFFIXES)


def scan_root(root: Path) -> list[str]:
    findings: list[str] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if any(part in SKIP_DIRECTORIES for part in relative.parts):
            continue
        relative_text = relative.as_posix()
        if any(part.casefold() in SENSITIVE_PATH_PARTS for part in relative.parts):
            findings.append("sensitive-name:<redacted-path>:0")
        for label, pattern in PATTERNS.items():
            if pattern.search(relative_text):
                findings.append(f"{label}-in-name:<redacted-path>:0")
        try:
            metadata = path.lstat()
        except OSError:
            findings.append("metadata-error:<redacted-path>:0")
            continue
        attributes = getattr(metadata, "st_file_attributes", 0)
        if stat.S_ISLNK(metadata.st_mode) or attributes & 0x400:
            findings.append("reparse:<redacted-path>:0")
            continue
        if not stat.S_ISREG(metadata.st_mode):
            continue
        if _known_binary_name(path):
            findings.append("binary:<redacted-path>:0")
            continue
        if metadata.st_size > 2 * 1024 * 1024:
            findings.append("oversize-text:<redacted-path>:0")
            continue
        try:
            with path.open("rb") as handle:
                raw = handle.read(2 * 1024 * 1024 + 1)
        except OSError:
            findings.append("read-error:<redacted-path>:0")
            continue
        if len(raw) > 2 * 1024 * 1024:
            findings.append("oversize-text:<redacted-path>:0")
            continue
        if b"\x00" in raw:
            findings.append("nul-byte:<redacted-path>:0")
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            findings.append("non-utf8:<redacted-path>:0")
            continue
        for line_number, line_text in enumerate(text.splitlines(), start=1):
            stripped = line_text.strip()
            for label, pattern in PATTERNS.items():
                if pattern.search(line_text) is None:
                    continue
                self_definition = (
                    relative_text == "tools/privacy_scan.py"
                    and stripped == f'"{label}": re.compile(r"{pattern.pattern}"),'
                )
                audited_fixture = stripped in AUDITED_TEST_FIXTURES.get(
                    (relative_text, label),
                    set(),
                )
                if self_definition or audited_fixture:
                    continue
                findings.append(f"{label}:<redacted-path>:{line_number}")
    return findings


def main(root: Path = ROOT) -> None:
    try:
        findings = scan_root(root)
    except Exception as error:
        raise SystemExit(f"privacy-scan failed: {type(error).__name__}") from None
    if findings:
        raise SystemExit("\n".join(findings))
    print("privacy-scan: source tree clean")


if __name__ == "__main__":
    main()
