from __future__ import annotations

import pytest

from tools.check_dist import reject_forbidden_names, require_unique_names


@pytest.mark.parametrize(
    "name",
    [
        "runtime.7z",
        "runtime.dylib",
        "runtime.node",
        "runtime.tar.bz2",
        "runtime.tar.xz",
    ],
)
def test_additional_runtime_archive_suffixes_are_rejected(name: str) -> None:
    with pytest.raises(SystemExit, match="forbidden runtime/model"):
        reject_forbidden_names({name}, "fixture")


def test_duplicate_distribution_member_names_are_rejected() -> None:
    with pytest.raises(SystemExit, match="duplicate member names"):
        require_unique_names(["same", "same"], "fixture")


def test_forbidden_member_error_does_not_echo_untrusted_name() -> None:
    sensitive = "private-contact" + chr(64) + "example.invalid.dylib"
    with pytest.raises(SystemExit) as caught:
        reject_forbidden_names({sensitive}, "fixture")
    assert sensitive not in str(caught.value)
