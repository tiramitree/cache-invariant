from __future__ import annotations

from cache_invariant.registration import (
    CACHE_PROMPT,
    CANCELLATION_BASELINE_PROMPT,
    CANCELLATION_STREAM_PROMPT,
    INTERLEAVING_SLOT_0_PROMPT,
    INTERLEAVING_SLOT_1_PROMPT,
    INTERLEAVING_STREAM_PROMPT,
    PROCESS_ORDER,
    SAVE_RESTORE_PROMPT,
    registered_scenarios,
)
from cache_invariant.util import canonical_json


def test_registration_excludes_raw_prompt_text() -> None:
    raw = canonical_json(registered_scenarios())
    for prompt in (
        CACHE_PROMPT,
        CANCELLATION_BASELINE_PROMPT,
        CANCELLATION_STREAM_PROMPT,
        INTERLEAVING_SLOT_0_PROMPT,
        INTERLEAVING_SLOT_1_PROMPT,
        INTERLEAVING_STREAM_PROMPT,
        SAVE_RESTORE_PROMPT,
    ):
        assert prompt.encode("utf-8") not in raw


def test_cancellation_backpressure_parameters_are_registered() -> None:
    stream = registered_scenarios()["cancellation_reuse"]["disconnect"]
    assert stream["n_probs"] == 512
    assert stream["receive_buffer_bytes"] == 1_024
    assert stream["active_observation_wait_ms"] == 2_000


def test_interleaving_mirror_schedule_is_registered() -> None:
    value = registered_scenarios()["interleaving_isolation"]
    assert value["slot_0_cancelled_first"]["first_disconnect_slot"] == 0
    assert value["slot_1_cancelled_first"]["first_disconnect_slot"] == 1
    assert value["slot_0_cancelled_first"]["launch_order"] == [0, 1]
    assert value["slot_1_cancelled_first"]["launch_order"] == [1, 0]
    for name in ("slot_0_cancelled_first", "slot_1_cancelled_first"):
        assert value[name]["simultaneous_start_barrier"] is True
        assert set(value[name]["streams"]) == {"slot_0_active", "slot_1_active"}
        assert set(value[name]["reuses"]) == {"slot_0", "slot_1"}
        for stream in value[name]["streams"].values():
            assert stream["n_predict"] == 100_000
            assert stream["n_probs"] == 512
            assert stream["receive_buffer_bytes"] == 1_024
            assert stream["active_observation_wait_ms"] == 5_000


def test_registration_process_order_is_fresh_and_exact() -> None:
    first = registered_scenarios()
    assert first["process_order"] == list(PROCESS_ORDER)
    first["process_order"].append("tampered")
    assert registered_scenarios()["process_order"] == list(PROCESS_ORDER)
