"""Pure deterministic oracles used by both runner and offline verifier."""

from __future__ import annotations

from typing import Any


def _completion(case: dict[str, Any]) -> dict[str, Any]:
    return case["completion"]


def _slot(case: dict[str, Any]) -> dict[str, Any]:
    return case["idle_slot"]


def _same_result(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return (
        left["content_sha256"] == right["content_sha256"]
        and left["tokens_sha256"] == right["tokens_sha256"]
        and left["content_bytes"] == right["content_bytes"]
        and left["predicted_tokens"] == right["predicted_tokens"]
        and left["token_count"] == right["token_count"]
    )


def cache_pairing_invariants(value: dict[str, Any]) -> dict[str, bool]:
    cold_on = value["cold_cache_on"]
    repeat_on = value["repeat_cache_on"]
    cold_off = value["cold_cache_off"]
    repeat_off = value["repeat_cache_off"]
    completions = [_completion(case) for case in value.values()]
    cases = list(value.values())
    first = completions[0]
    return {
        "cache_all_results_equal": all(
            _same_result(first, completion) for completion in completions[1:]
        ),
        "cache_on_response_prompt_work_strictly_reduced": (
            _completion(repeat_on)["prompt_work"] < _completion(cold_on)["prompt_work"]
        ),
        "cache_on_slot_prompt_work_strictly_reduced": (
            _slot(repeat_on)["prompt_work"] < _slot(cold_on)["prompt_work"]
        ),
        "cache_off_response_prompt_work_equal": (
            _completion(repeat_off)["prompt_work"]
            == _completion(cold_off)["prompt_work"]
        ),
        "cache_off_slot_prompt_work_equal": (
            _slot(repeat_off)["prompt_work"] == _slot(cold_off)["prompt_work"]
        ),
        "cache_prompt_work_views_consistent": all(
            _completion(case)["prompt_work"] == _slot(case)["prompt_work"]
            for case in cases
        ),
        "cache_slots_idle": all(_slot(case)["idle"] for case in cases),
    }


def cancellation_invariants(value: dict[str, Any]) -> dict[str, bool]:
    baseline = value["clean_baseline"]
    reused = value["reused_slot"]
    disconnect = value["disconnect"]
    return {
        "cancel_active_processing_observed": disconnect["active_processing_observed"],
        "cancel_first_event_observed": disconnect["first_event_observed"],
        "cancel_first_event_nonterminal": disconnect["first_event_nonterminal"],
        "cancel_idle_after_disconnect": disconnect["idle_after_disconnect"],
        "cancel_reuse_result_matches_clean_slot": _same_result(
            _completion(baseline),
            _completion(reused),
        ),
        "cancel_reuse_prompt_work_matches_clean_slot": (
            _completion(baseline)["prompt_work"] == _completion(reused)["prompt_work"]
        ),
        "cancel_prompt_work_views_consistent": (
            _completion(baseline)["prompt_work"] == _slot(baseline)["prompt_work"]
            and _completion(reused)["prompt_work"] == _slot(reused)["prompt_work"]
        ),
        "cancel_reused_slot_idle": _slot(reused)["idle"],
    }


def save_restore_invariants(value: dict[str, Any]) -> dict[str, bool]:
    source = value["source"]
    same = value["same_process"]
    restarted = value["after_restart"]
    source_completion = _completion(source)
    same_completion = _completion(same["restored"])
    restart_completion = _completion(restarted["restored"])
    state_before = value["slot_state_before_restart"]
    state_after = value["slot_state_after_restart"]
    return {
        "save_reports_positive_tokens": value["saved_tokens"] > 0,
        "same_process_restore_count_matches_save": (
            same["restored_tokens"] == value["saved_tokens"]
        ),
        "same_process_restore_result_matches_source": _same_result(
            source_completion,
            same_completion,
        ),
        "same_process_response_prompt_work_strictly_reduced": (
            same_completion["prompt_work"] < source_completion["prompt_work"]
        ),
        "same_process_slot_prompt_work_strictly_reduced": (
            _slot(same["restored"])["prompt_work"] < _slot(source)["prompt_work"]
        ),
        "restart_restore_count_matches_save": (
            restarted["restored_tokens"] == value["saved_tokens"]
        ),
        "restart_restore_result_matches_source": _same_result(
            source_completion,
            restart_completion,
        ),
        "restart_response_prompt_work_strictly_reduced": (
            restart_completion["prompt_work"] < source_completion["prompt_work"]
        ),
        "restart_slot_prompt_work_strictly_reduced": (
            _slot(restarted["restored"])["prompt_work"] < _slot(source)["prompt_work"]
        ),
        "restore_prompt_work_views_consistent": all(
            _completion(case)["prompt_work"] == _slot(case)["prompt_work"]
            for case in [source, same["restored"], restarted["restored"]]
        ),
        "restore_slots_idle": all(
            _slot(case)["idle"]
            for case in [source, same["restored"], restarted["restored"]]
        ),
        "server_process_restart_confirmed": value["process_restart_confirmed"],
        "slot_state_file_nonempty": state_before["bytes"] > 0,
        "slot_state_file_unchanged_across_restart": state_before == state_after,
    }


def all_invariants(evidence: dict[str, Any]) -> dict[str, bool]:
    result: dict[str, bool] = {}
    for values in (
        cache_pairing_invariants(evidence["cache_pairing"]),
        cancellation_invariants(evidence["cancellation_reuse"]),
        save_restore_invariants(evidence["save_restore"]),
    ):
        overlap = set(result) & set(values)
        if overlap:
            raise ValueError(f"duplicate invariant names: {sorted(overlap)}")
        result.update(values)
    return result
