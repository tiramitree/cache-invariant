from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from cache_invariant.evidence import write_bundle
from cache_invariant.util import pretty_json
from cache_invariant.verify import validate_evidence, verify_bundle


def _directory_symlink_or_skip(target: Path, link: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"directory symlink unavailable: {type(error).__name__}")


def test_round_trip_bundle(
    tmp_path: Path,
    valid_evidence: dict,
) -> None:
    output = tmp_path / "bundle"
    summary = write_bundle(output, valid_evidence)
    assert summary["platform"] == "windows-x86_64"
    assert summary["invariant_count"] == len(valid_evidence["invariants"])
    assert verify_bundle(output) == summary
    assert {path.name for path in output.iterdir()} == {
        "evidence.json",
        "junit.xml",
        "manifest.json",
    }


def test_bundled_v0_1_evidence_remains_offline_verifiable() -> None:
    root = Path(__file__).resolve().parents[1]
    summary = verify_bundle(root / "evidence" / "reference-v0.1.0-windows")
    assert summary == {
        "invariant_count": 29,
        "platform": "windows-x86_64",
        "schema": "cache-invariant-evidence-v1",
    }


def test_bundled_v0_2_evidence_is_offline_verifiable() -> None:
    root = Path(__file__).resolve().parents[1]
    summary = verify_bundle(root / "evidence" / "reference-v0.2.0-windows")
    assert summary == {
        "invariant_count": 57,
        "platform": "windows-x86_64",
        "schema": "cache-invariant-evidence-v2",
    }


def test_bundle_symlink_is_rejected(
    tmp_path: Path,
    valid_evidence: dict,
) -> None:
    real = tmp_path / "real"
    write_bundle(real, valid_evidence)
    linked = tmp_path / "linked"
    _directory_symlink_or_skip(real, linked)
    with pytest.raises(ValueError, match="reparse"):
        verify_bundle(linked)


def test_output_parent_symlink_is_rejected(
    tmp_path: Path,
    valid_evidence: dict,
) -> None:
    real_parent = tmp_path / "real-parent"
    real_parent.mkdir()
    linked_parent = tmp_path / "linked-parent"
    _directory_symlink_or_skip(real_parent, linked_parent)
    with pytest.raises(ValueError, match="reparse"):
        write_bundle(linked_parent / "bundle", valid_evidence)


def test_unknown_evidence_field_is_rejected(valid_evidence: dict) -> None:
    value = copy.deepcopy(valid_evidence)
    value["raw_prompt"] = "forbidden"
    with pytest.raises(ValueError, match="keys differ"):
        validate_evidence(value)


def test_runtime_pin_drift_is_rejected(valid_evidence: dict) -> None:
    value = copy.deepcopy(valid_evidence)
    value["runtime"]["source_commit"] = "0" * 40
    with pytest.raises(ValueError, match="runtime pins"):
        validate_evidence(value)


def test_committed_source_revision_is_accepted(valid_evidence: dict) -> None:
    value = copy.deepcopy(valid_evidence)
    value["source_revision"] = "a" * 40
    assert validate_evidence(value) is value


@pytest.mark.parametrize(
    "source_revision",
    ["", "uncommitted", "A" * 40, "a" * 39, "g" * 40, "a" * 41],
)
def test_invalid_source_revision_is_rejected(
    valid_evidence: dict,
    source_revision: str,
) -> None:
    value = copy.deepcopy(valid_evidence)
    value["source_revision"] = source_revision
    with pytest.raises(ValueError, match="source_revision"):
        validate_evidence(value)


def test_registration_tamper_is_rejected(valid_evidence: dict) -> None:
    value = copy.deepcopy(valid_evidence)
    value["registration"]["cache_pairing"]["cold_cache_on"]["n_predict"] = 9
    with pytest.raises(ValueError, match="registration differs"):
        validate_evidence(value)


@pytest.mark.parametrize(
    ("section", "key"),
    [
        ("fixture", "checkpoint_sha256"),
        ("fixture", "model_sha256"),
        ("fixture", "tokenizer_sha256"),
        ("runtime", "asset_sha256"),
        ("runtime", "server_sha256"),
    ],
)
def test_registered_hash_drift_is_rejected(
    valid_evidence: dict,
    section: str,
    key: str,
) -> None:
    value = copy.deepcopy(valid_evidence)
    value[section][key] = "0" * 64
    with pytest.raises(ValueError):
        validate_evidence(value)


def test_stored_oracle_drift_is_rejected(valid_evidence: dict) -> None:
    value = copy.deepcopy(valid_evidence)
    name = next(iter(value["invariants"]))
    value["invariants"][name] = False
    with pytest.raises(ValueError, match="stored invariants"):
        validate_evidence(value)


def test_boundary_flip_is_rejected(valid_evidence: dict) -> None:
    value = copy.deepcopy(valid_evidence)
    value["boundary"]["absolute_paths_included"] = True
    with pytest.raises(ValueError, match="forbidden content"):
        validate_evidence(value)


def test_nested_raw_prompt_field_is_rejected(valid_evidence: dict) -> None:
    value = copy.deepcopy(valid_evidence)
    value["cache_pairing"]["cold_cache_on"]["completion"]["raw_prompt"] = "x"
    with pytest.raises(ValueError, match="keys differ"):
        validate_evidence(value)


def test_nested_path_field_is_rejected(valid_evidence: dict) -> None:
    value = copy.deepcopy(valid_evidence)
    value["save_restore"]["slot_state_before_restart"]["path"] = "x"
    with pytest.raises(ValueError, match="keys differ"):
        validate_evidence(value)


def test_interleaving_boolean_tamper_fails_closed(valid_evidence: dict) -> None:
    value = copy.deepcopy(valid_evidence)
    value["interleaving_isolation"]["slot_1_cancelled_first"][
        "both_idle_after_second_disconnect"
    ] = False
    value["invariants"] = __import__(
        "cache_invariant.oracle",
        fromlist=["all_invariants"],
    ).all_invariants(value)
    with pytest.raises(ValueError, match="runtime invariants failed"):
        validate_evidence(value)


def test_interleaving_unknown_field_is_rejected(valid_evidence: dict) -> None:
    value = copy.deepcopy(valid_evidence)
    value["interleaving_isolation"]["slot_0_cancelled_first"]["elapsed_ms"] = 12
    with pytest.raises(ValueError, match="keys differ"):
        validate_evidence(value)


def test_slot_state_drift_is_rejected(valid_evidence: dict) -> None:
    value = copy.deepcopy(valid_evidence)
    value["save_restore"]["slot_state_after_restart"]["sha256"] = "2" * 64
    value["invariants"] = __import__(
        "cache_invariant.oracle",
        fromlist=["all_invariants"],
    ).all_invariants(value)
    with pytest.raises(ValueError, match="runtime invariants failed"):
        validate_evidence(value)


def test_token_count_must_match_prediction(valid_evidence: dict) -> None:
    value = copy.deepcopy(valid_evidence)
    value["cache_pairing"]["cold_cache_on"]["completion"]["token_count"] = 7
    with pytest.raises(ValueError, match="token count differs"):
        validate_evidence(value)


def test_extra_bundle_file_is_rejected(
    tmp_path: Path,
    valid_evidence: dict,
) -> None:
    output = tmp_path / "bundle"
    write_bundle(output, valid_evidence)
    (output / "extra.txt").write_text("extra", encoding="utf-8")
    with pytest.raises(ValueError, match="file set differs"):
        verify_bundle(output)


def test_manifest_hash_tamper_is_rejected(
    tmp_path: Path,
    valid_evidence: dict,
) -> None:
    output = tmp_path / "bundle"
    write_bundle(output, valid_evidence)
    evidence = output / "evidence.json"
    evidence.write_bytes(evidence.read_bytes() + b" ")
    with pytest.raises(ValueError, match="byte count differs"):
        verify_bundle(output)


def test_duplicate_key_in_bundle_json_is_rejected(
    tmp_path: Path,
    valid_evidence: dict,
) -> None:
    output = tmp_path / "bundle"
    write_bundle(output, valid_evidence)
    manifest = output / "manifest.json"
    manifest.write_text(
        '{"schema":"cache-invariant-manifest-v1",'
        '"schema":"cache-invariant-manifest-v1","files":[]}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate JSON key"):
        verify_bundle(output)


def test_nonfinite_bundle_json_is_rejected(
    tmp_path: Path,
    valid_evidence: dict,
) -> None:
    output = tmp_path / "bundle"
    write_bundle(output, valid_evidence)
    manifest = output / "manifest.json"
    manifest.write_text('{"schema":NaN,"files":[]}', encoding="utf-8")
    with pytest.raises(ValueError, match="non-finite"):
        verify_bundle(output)


def test_junit_projection_tamper_is_rejected(
    tmp_path: Path,
    valid_evidence: dict,
) -> None:
    output = tmp_path / "bundle"
    write_bundle(output, valid_evidence)
    junit = output / "junit.xml"
    junit.write_text("<testsuite/>", encoding="utf-8")
    manifest_path = output / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for record in manifest["files"]:
        if record["path"] == "junit.xml":
            import hashlib

            raw = junit.read_bytes()
            record["bytes"] = len(raw)
            record["sha256"] = hashlib.sha256(raw).hexdigest()
    manifest_path.write_bytes(pretty_json(manifest))
    with pytest.raises(ValueError, match="JUnit projection"):
        verify_bundle(output)
