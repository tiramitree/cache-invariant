from __future__ import annotations

from typing import Any

import pytest

from cache_invariant.adapter import (
    LlamaCppClient,
    _decode_json,
    _stream_event_is_nonterminal,
)


def test_server_json_duplicate_keys_are_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        _decode_json(b'{"a":1,"a":2}')


def test_server_json_nonfinite_values_are_rejected() -> None:
    with pytest.raises(ValueError, match="non-finite"):
        _decode_json(b'{"a":NaN}')


def test_stream_event_requires_nonterminal_sse_object() -> None:
    assert _stream_event_is_nonterminal(b'data: {"content":"synthetic","stop":false}\n')
    assert not _stream_event_is_nonterminal(b'data: {"content":"","stop":true}\n')


def test_slots_require_exact_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    client = LlamaCppClient(port=1, api_key="private")
    monkeypatch.setattr(
        LlamaCppClient,
        "request_json",
        lambda *_args, **_kwargs: [
            {"id": 0, "is_processing": False},
            {"id": 2, "is_processing": False},
        ],
    )
    with pytest.raises(ValueError, match="slot IDs"):
        client.slots()


def test_completion_requests_and_hashes_real_token_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = LlamaCppClient(port=1, api_key="private")
    captured: dict[str, Any] = {}

    def request(
        _self: LlamaCppClient,
        _method: str,
        _path: str,
        body: dict[str, Any],
        **_kwargs: Any,
    ) -> dict[str, Any]:
        captured.update(body)
        return {
            "content": "abc",
            "tokens": [1, 2, 3],
            "tokens_cached": 4,
            "timings": {"predicted_n": 3, "prompt_n": 5},
        }

    monkeypatch.setattr(LlamaCppClient, "request_json", request)
    value = client.completion(
        0,
        "prompt",
        cache_prompt=True,
        n_predict=3,
        seed=42,
        temperature=0,
    )
    assert captured["return_tokens"] is True
    assert value["token_count"] == 3
    assert value["predicted_tokens"] == 3
    assert value["tokens_sha256"] != "0" * 64


def test_completion_rejects_empty_default_token_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = LlamaCppClient(port=1, api_key="private")
    monkeypatch.setattr(
        LlamaCppClient,
        "request_json",
        lambda *_args, **_kwargs: {
            "content": "abc",
            "tokens": [],
            "tokens_cached": 4,
            "timings": {"predicted_n": 3, "prompt_n": 5},
        },
    )
    with pytest.raises(ValueError, match="token list"):
        client.completion(
            0,
            "prompt",
            cache_prompt=True,
            n_predict=3,
            seed=42,
            temperature=0,
        )


def test_direct_token_prefill_discards_generated_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = LlamaCppClient(port=1, api_key="private")
    captured: dict[str, Any] = {}

    def request(
        _self: LlamaCppClient,
        _method: str,
        _path: str,
        body: dict[str, Any],
        **_kwargs: Any,
    ) -> dict[str, Any]:
        captured.update(body)
        return {
            "content": "discarded generated output",
            "tokens": [511],
            "tokens_evaluated": 4,
            "tokens_predicted": 1,
            "timings": {
                "cache_n": 3,
                "predicted_n": 1,
                "prompt_n": 1,
            },
        }

    monkeypatch.setattr(LlamaCppClient, "request_json", request)
    value = client.direct_token_prefill(
        0,
        (403, 407, 261, 378),
        cache_prompt=True,
        n_cache_reuse=0,
        n_predict=1,
        seed=42,
        temperature=0,
    )
    assert captured["prompt"] == [403, 407, 261, 378]
    assert captured["n_cache_reuse"] == 0
    assert captured["n_predict"] == 1
    assert captured["return_tokens"] is False
    assert value == {
        "cache_tokens": 3,
        "predicted_tokens": 1,
        "prompt_tokens": 4,
        "prompt_work": 1,
    }
    assert "content" not in value
    assert "tokens" not in value


def test_direct_token_prefill_requires_counter_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = LlamaCppClient(port=1, api_key="private")
    monkeypatch.setattr(
        LlamaCppClient,
        "request_json",
        lambda *_args, **_kwargs: {
            "content": "discarded",
            "tokens_evaluated": 4,
            "timings": {"predicted_n": 1, "prompt_n": 1},
        },
    )
    with pytest.raises(ValueError, match="cache count"):
        client.direct_token_prefill(
            0,
            (403, 407, 261, 378),
            cache_prompt=True,
            n_cache_reuse=0,
            n_predict=1,
            seed=42,
            temperature=0,
        )


def test_dual_stream_requires_registered_disconnect_slot() -> None:
    client = LlamaCppClient(port=1, api_key="private")
    with pytest.raises(ValueError, match="registered pair"):
        client.dual_stream_disconnect(
            ("first", "second"),
            cache_prompt=True,
            ignore_eos=True,
            n_predict=100_000,
            n_probs=512,
            receive_buffer_bytes=1_024,
            active_observation_wait_ms=5_000,
            first_disconnect_slot=2,
            seed=42,
            temperature=0,
        )
