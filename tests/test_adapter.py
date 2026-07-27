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
