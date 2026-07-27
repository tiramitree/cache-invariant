from __future__ import annotations

from typing import Any

import pytest

from cache_invariant.runner import build_evidence


def completion_case(
    *,
    content_hash: str,
    token_hash: str,
    prompt_work: int,
    predicted_tokens: int = 8,
) -> dict[str, Any]:
    return {
        "completion": {
            "content_bytes": 12,
            "content_sha256": content_hash,
            "predicted_tokens": predicted_tokens,
            "prompt_work": prompt_work,
            "response_cached_tokens": 12,
            "token_count": predicted_tokens,
            "tokens_sha256": token_hash,
        },
        "idle_slot": {
            "idle": True,
            "prompt_work": prompt_work,
        },
    }


@pytest.fixture
def valid_evidence() -> dict[str, Any]:
    cache_hash = "a" * 64
    cache_tokens = "b" * 64
    cache_pairing = {
        "cold_cache_on": completion_case(
            content_hash=cache_hash,
            token_hash=cache_tokens,
            prompt_work=5,
        ),
        "repeat_cache_on": completion_case(
            content_hash=cache_hash,
            token_hash=cache_tokens,
            prompt_work=1,
        ),
        "cold_cache_off": completion_case(
            content_hash=cache_hash,
            token_hash=cache_tokens,
            prompt_work=5,
        ),
        "repeat_cache_off": completion_case(
            content_hash=cache_hash,
            token_hash=cache_tokens,
            prompt_work=5,
        ),
    }
    cancel_hash = "c" * 64
    cancel_tokens = "d" * 64
    cancellation_reuse = {
        "clean_baseline": completion_case(
            content_hash=cancel_hash,
            token_hash=cancel_tokens,
            prompt_work=8,
            predicted_tokens=16,
        ),
        "disconnect": {
            "active_processing_observed": True,
            "first_event_nonterminal": True,
            "first_event_observed": True,
            "idle_after_disconnect": True,
        },
        "reused_slot": completion_case(
            content_hash=cancel_hash,
            token_hash=cancel_tokens,
            prompt_work=8,
            predicted_tokens=16,
        ),
    }
    restore_hash = "e" * 64
    restore_tokens = "f" * 64
    state = {"bytes": 11_960, "sha256": "1" * 64}
    save_restore = {
        "after_restart": {
            "restored": completion_case(
                content_hash=restore_hash,
                token_hash=restore_tokens,
                prompt_work=1,
            ),
            "restored_tokens": 18,
        },
        "process_restart_confirmed": True,
        "same_process": {
            "restored": completion_case(
                content_hash=restore_hash,
                token_hash=restore_tokens,
                prompt_work=1,
            ),
            "restored_tokens": 18,
        },
        "saved_tokens": 18,
        "slot_state_after_restart": dict(state),
        "slot_state_before_restart": dict(state),
        "source": completion_case(
            content_hash=restore_hash,
            token_hash=restore_tokens,
            prompt_work=11,
        ),
    }
    return build_evidence(
        platform_key="windows-x86_64",
        cache_pairing=cache_pairing,
        cancellation_reuse=cancellation_reuse,
        save_restore=save_restore,
        source_revision="UNCOMMITTED",
    )
