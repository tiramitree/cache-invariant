from __future__ import annotations

import copy

from cache_invariant.oracle import all_invariants


def test_valid_evidence_passes_every_oracle(valid_evidence: dict) -> None:
    invariants = all_invariants(valid_evidence)
    assert invariants
    assert all(invariants.values())
    assert invariants == valid_evidence["invariants"]


def test_cache_on_must_strictly_reduce_prompt_work(valid_evidence: dict) -> None:
    value = copy.deepcopy(valid_evidence)
    value["cache_pairing"]["repeat_cache_on"]["completion"]["prompt_work"] = 5
    value["cache_pairing"]["repeat_cache_on"]["idle_slot"]["prompt_work"] = 5
    assert not all_invariants(value)["cache_on_response_prompt_work_strictly_reduced"]
    assert not all_invariants(value)["cache_on_slot_prompt_work_strictly_reduced"]


def test_cache_off_must_not_reduce_prompt_work(valid_evidence: dict) -> None:
    value = copy.deepcopy(valid_evidence)
    value["cache_pairing"]["repeat_cache_off"]["completion"]["prompt_work"] = 1
    value["cache_pairing"]["repeat_cache_off"]["idle_slot"]["prompt_work"] = 1
    assert not all_invariants(value)["cache_off_response_prompt_work_equal"]
    assert not all_invariants(value)["cache_off_slot_prompt_work_equal"]


def test_reuse_hash_mismatch_fails(valid_evidence: dict) -> None:
    value = copy.deepcopy(valid_evidence)
    value["cancellation_reuse"]["reused_slot"]["completion"]["tokens_sha256"] = "0" * 64
    assert not all_invariants(value)["cancel_reuse_result_matches_clean_slot"]


def test_restart_restore_must_strictly_reduce_work(valid_evidence: dict) -> None:
    value = copy.deepcopy(valid_evidence)
    value["save_restore"]["after_restart"]["restored"]["completion"]["prompt_work"] = 11
    value["save_restore"]["after_restart"]["restored"]["idle_slot"]["prompt_work"] = 11
    invariants = all_invariants(value)
    assert not invariants["restart_response_prompt_work_strictly_reduced"]
    assert not invariants["restart_slot_prompt_work_strictly_reduced"]


def test_slot_file_change_across_restart_fails(valid_evidence: dict) -> None:
    value = copy.deepcopy(valid_evidence)
    value["save_restore"]["slot_state_after_restart"]["sha256"] = "2" * 64
    assert not all_invariants(value)["slot_state_file_unchanged_across_restart"]
