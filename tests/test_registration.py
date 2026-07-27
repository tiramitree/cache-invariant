from __future__ import annotations

from cache_invariant.registration import (
    CACHE_PROMPT,
    CANCELLATION_BASELINE_PROMPT,
    CANCELLATION_STREAM_PROMPT,
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
        SAVE_RESTORE_PROMPT,
    ):
        assert prompt.encode("utf-8") not in raw


def test_cancellation_backpressure_parameters_are_registered() -> None:
    stream = registered_scenarios()["cancellation_reuse"]["disconnect"]
    assert stream["n_probs"] == 512
    assert stream["receive_buffer_bytes"] == 1_024
    assert stream["active_observation_wait_ms"] == 2_000


def test_registration_process_order_is_fresh_and_exact() -> None:
    first = registered_scenarios()
    assert first["process_order"] == list(PROCESS_ORDER)
    first["process_order"].append("tampered")
    assert registered_scenarios()["process_order"] == list(PROCESS_ORDER)
