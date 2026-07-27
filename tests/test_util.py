from __future__ import annotations

from pathlib import Path

import pytest

from cache_invariant.util import (
    canonical_json,
    load_json_strict,
    safe_relative_path,
)


def test_canonical_json_is_sorted_and_compact() -> None:
    assert canonical_json({"b": 2, "a": 1}) == b'{"a":1,"b":2}'


def test_duplicate_json_key_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "value.json"
    path.write_text('{"a":1,"a":2}', encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate JSON key"):
        load_json_strict(path)


def test_nonfinite_json_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "value.json"
    path.write_text('{"a":NaN}', encoding="utf-8")
    with pytest.raises(ValueError, match="non-finite"):
        load_json_strict(path)


@pytest.mark.parametrize(
    "value",
    [
        "../escape",
        "/absolute",
        "C:/drive",
        r"folder\file",
        "//server/share",
        "folder/../file",
    ],
)
def test_unsafe_relative_paths_are_rejected(value: str) -> None:
    with pytest.raises(ValueError):
        safe_relative_path(value, "test")


def test_registered_shape_relative_path_is_accepted() -> None:
    assert (
        safe_relative_path(
            "fixture/stories260K.bin",
            "test",
        ).as_posix()
        == "fixture/stories260K.bin"
    )
