from __future__ import annotations

from pathlib import Path

import pytest

from tools.privacy_scan import main, scan_root


def test_sensitive_path_and_content_are_redacted(tmp_path: Path) -> None:
    sensitive = "private-contact" + chr(64) + "example.invalid"
    path = tmp_path / sensitive
    path.write_text(sensitive, encoding="utf-8")

    findings = "\n".join(scan_root(tmp_path))

    assert "<redacted-path>" in findings
    assert sensitive not in findings
    assert str(path) not in findings


def test_failure_output_does_not_echo_sensitive_value(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sensitive = "private-contact" + chr(64) + "example.invalid"
    path = tmp_path / sensitive
    path.write_text(sensitive, encoding="utf-8")

    with pytest.raises(SystemExit) as caught:
        main(tmp_path)

    captured = capsys.readouterr()
    public_failure = f"{caught.value}\n{captured.out}\n{captured.err}"
    assert "<redacted-path>" in public_failure
    assert sensitive not in public_failure
    assert str(path) not in public_failure


@pytest.mark.parametrize(
    "suffix",
    [".tar.gz", ".tar.xz", ".node", ".dylib"],
)
def test_known_binary_and_archive_suffixes_fail_closed(
    tmp_path: Path,
    suffix: str,
) -> None:
    path = tmp_path / f"fixture{suffix}"
    path.write_bytes(b"synthetic")
    findings = "\n".join(scan_root(tmp_path))
    assert "binary:<redacted-path>:0" in findings
    assert str(path) not in findings


def test_unknown_suffix_content_is_scanned(tmp_path: Path) -> None:
    sensitive = "private-contact" + chr(64) + "example.invalid"
    path = tmp_path / "fixture.dat"
    path.write_text(sensitive, encoding="utf-8")
    findings = "\n".join(scan_root(tmp_path))
    assert "email:<redacted-path>:1" in findings
    assert sensitive not in findings


@pytest.mark.parametrize(
    ("label", "sensitive"),
    [
        ("china-phone", "+86" + "1" + "38" + "0000" + "0000"),
        ("non-loopback-ipv4", "10" + ".0.0.7"),
        ("user-home-shortcut", chr(126) + "/private"),
        ("wsl-user-path", "/mnt/" + "c/Users/private/data"),
    ],
)
def test_additional_sensitive_shapes_are_redacted(
    tmp_path: Path,
    label: str,
    sensitive: str,
) -> None:
    path = tmp_path / "fixture.dat"
    path.write_text(sensitive, encoding="utf-8")
    findings = "\n".join(scan_root(tmp_path))
    assert f"{label}:<redacted-path>:1" in findings
    assert sensitive not in findings
