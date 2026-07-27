"""Frozen scenario stimuli and their privacy-normalized public registration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .util import canonical_json, sha256_bytes

REGISTRATION_SCHEMA = "cache-invariant-registration-v3"
REGISTRATION_SCHEMA_V2 = "cache-invariant-registration-v2"
REGISTRATION_SCHEMA_V1 = "cache-invariant-registration-v1"
SEED = 42
TEMPERATURE = 0
RETURN_TOKENS = True
PREFILL_RETURN_TOKENS = False
PREFILL_N_PREDICT = 1
PREFILL_N_CACHE_REUSE = 0
SLOT_STATE_NAME = "cache-invariant-slot-v1.bin"

CACHE_PROMPT = "Once upon a time"
CANCELLATION_BASELINE_PROMPT = "The moon rose above the quiet village"
CANCELLATION_STREAM_PROMPT = "A synthetic story begins"
SAVE_RESTORE_PROMPT = "In a small forest"
INTERLEAVING_SLOT_0_PROMPT = "A copper fox crossed the silent bridge"
INTERLEAVING_SLOT_1_PROMPT = "A paper kite climbed above the harbor"
INTERLEAVING_STREAM_PROMPT = "A registered synthetic stream continues"
TOKEN_PREFIX_SOURCE = (403, 407, 261, 378)
TOKEN_PREFIX_EXACT_TARGET = TOKEN_PREFIX_SOURCE
TOKEN_PREFIX_SHARED_TARGET = (403, 407, 261, 328, 426)
TOKEN_PREFIX_DIVERGED_TARGET = (385, 328, 426)


@dataclass(frozen=True)
class CompletionSpec:
    """One registered non-streaming completion."""

    name: str
    slot: int
    prompt: str
    cache_prompt: bool
    n_predict: int


@dataclass(frozen=True)
class StreamSpec:
    """One registered streaming request that is deliberately disconnected."""

    name: str
    slot: int
    prompt: str
    cache_prompt: bool
    ignore_eos: bool
    n_predict: int
    n_probs: int
    receive_buffer_bytes: int
    active_observation_wait_ms: int


@dataclass(frozen=True)
class TokenPromptSpec:
    """One registered direct-token prefill request."""

    name: str
    slot: int
    prompt: tuple[int, ...]
    cache_prompt: bool


@dataclass(frozen=True)
class TokenPrefixCase:
    """One source/target longest-common-prefix case."""

    name: str
    common_prefix_tokens: int
    source: TokenPromptSpec
    cache_on_target: TokenPromptSpec
    cache_off_target: TokenPromptSpec


CACHE_PAIRING_CASES = (
    CompletionSpec("cold_cache_on", 0, CACHE_PROMPT, True, 8),
    CompletionSpec("repeat_cache_on", 0, CACHE_PROMPT, True, 8),
    CompletionSpec("cold_cache_off", 1, CACHE_PROMPT, False, 8),
    CompletionSpec("repeat_cache_off", 1, CACHE_PROMPT, False, 8),
)
CANCELLATION_BASELINE = CompletionSpec(
    "clean_baseline",
    1,
    CANCELLATION_BASELINE_PROMPT,
    False,
    16,
)
CANCELLATION_STREAM = StreamSpec(
    "disconnect",
    0,
    CANCELLATION_STREAM_PROMPT,
    True,
    True,
    100_000,
    512,
    1_024,
    2_000,
)
CANCELLATION_REUSE = CompletionSpec(
    "reused_slot",
    0,
    CANCELLATION_BASELINE_PROMPT,
    False,
    16,
)
SAVE_SOURCE = CompletionSpec("source", 0, SAVE_RESTORE_PROMPT, True, 8)
SAVE_SAME_PROCESS = CompletionSpec(
    "same_process.restored",
    1,
    SAVE_RESTORE_PROMPT,
    True,
    8,
)
SAVE_AFTER_RESTART = CompletionSpec(
    "after_restart.restored",
    0,
    SAVE_RESTORE_PROMPT,
    True,
    8,
)
INTERLEAVING_BASELINES = (
    CompletionSpec(
        "slot_0",
        0,
        INTERLEAVING_SLOT_0_PROMPT,
        False,
        16,
    ),
    CompletionSpec(
        "slot_1",
        1,
        INTERLEAVING_SLOT_1_PROMPT,
        False,
        16,
    ),
)
INTERLEAVING_STREAMS = (
    StreamSpec(
        "slot_0_active",
        0,
        INTERLEAVING_STREAM_PROMPT,
        True,
        True,
        100_000,
        512,
        1_024,
        5_000,
    ),
    StreamSpec(
        "slot_1_active",
        1,
        INTERLEAVING_STREAM_PROMPT,
        True,
        True,
        100_000,
        512,
        1_024,
        5_000,
    ),
)
TOKEN_PREFIX_CASES = (
    TokenPrefixCase(
        "exact",
        4,
        TokenPromptSpec("source", 0, TOKEN_PREFIX_SOURCE, True),
        TokenPromptSpec("cache_on_target", 0, TOKEN_PREFIX_EXACT_TARGET, True),
        TokenPromptSpec("cache_off_target", 0, TOKEN_PREFIX_EXACT_TARGET, False),
    ),
    TokenPrefixCase(
        "shared_prefix",
        3,
        TokenPromptSpec("source", 0, TOKEN_PREFIX_SOURCE, True),
        TokenPromptSpec("cache_on_target", 0, TOKEN_PREFIX_SHARED_TARGET, True),
        TokenPromptSpec("cache_off_target", 0, TOKEN_PREFIX_SHARED_TARGET, False),
    ),
    TokenPrefixCase(
        "first_token_divergence",
        0,
        TokenPromptSpec("source", 0, TOKEN_PREFIX_SOURCE, True),
        TokenPromptSpec("cache_on_target", 0, TOKEN_PREFIX_DIVERGED_TARGET, True),
        TokenPromptSpec("cache_off_target", 0, TOKEN_PREFIX_DIVERGED_TARGET, False),
    ),
)

PROCESS_ORDER_V1 = (
    "start_server_1",
    "cache_pairing.erase_slot_0",
    "cache_pairing.erase_slot_1",
    *(f"cache_pairing.{case.name}" for case in CACHE_PAIRING_CASES),
    "cancellation_reuse.erase_slot_0",
    "cancellation_reuse.erase_slot_1",
    "cancellation_reuse.clean_baseline",
    "cancellation_reuse.disconnect",
    "cancellation_reuse.reused_slot",
    "save_restore.erase_slot_0",
    "save_restore.erase_slot_1",
    "save_restore.source",
    "save_restore.save_slot_0",
    "save_restore.restore_slot_1",
    "save_restore.same_process.restored",
    "stop_server_1",
    "hash_slot_state_before_restart",
    "start_server_2",
    "save_restore.erase_slot_0",
    "save_restore.restore_slot_0",
    "save_restore.after_restart.restored",
    "stop_server_2",
    "hash_slot_state_after_restart",
)
INTERLEAVING_PROCESS_ORDER = (
    "interleaving_isolation.erase_slot_0",
    "interleaving_isolation.erase_slot_1",
    "interleaving_isolation.baselines.slot_0",
    "interleaving_isolation.baselines.slot_1",
    "interleaving_isolation.erase_slot_0",
    "interleaving_isolation.erase_slot_1",
    "interleaving_isolation.slot_0_cancelled_first.dual_stream_disconnect",
    "interleaving_isolation.slot_0_cancelled_first.slot_0_reuse",
    "interleaving_isolation.slot_0_cancelled_first.slot_1_reuse",
    "interleaving_isolation.erase_slot_0",
    "interleaving_isolation.erase_slot_1",
    "interleaving_isolation.slot_1_cancelled_first.dual_stream_disconnect",
    "interleaving_isolation.slot_1_cancelled_first.slot_0_reuse",
    "interleaving_isolation.slot_1_cancelled_first.slot_1_reuse",
)
PROCESS_ORDER_V2 = (
    *PROCESS_ORDER_V1[:12],
    *INTERLEAVING_PROCESS_ORDER,
    *PROCESS_ORDER_V1[12:],
)
TOKEN_PREFIX_PROCESS_ORDER = tuple(
    step
    for case in TOKEN_PREFIX_CASES
    for step in (
        f"token_prefix_divergence.{case.name}.erase_slot_0",
        f"token_prefix_divergence.{case.name}.source",
        f"token_prefix_divergence.{case.name}.cache_on_target",
        f"token_prefix_divergence.{case.name}.erase_slot_0",
        f"token_prefix_divergence.{case.name}.cache_off_target",
    )
)
PROCESS_ORDER = (
    *PROCESS_ORDER_V1[:12],
    *INTERLEAVING_PROCESS_ORDER,
    *TOKEN_PREFIX_PROCESS_ORDER,
    *PROCESS_ORDER_V1[12:],
)


def _prompt_identity(prompt: str) -> dict[str, Any]:
    raw = prompt.encode("utf-8")
    return {
        "bytes": len(raw),
        "sha256": sha256_bytes(raw),
    }


def _completion_registration(spec: CompletionSpec) -> dict[str, Any]:
    return {
        "cache_prompt": spec.cache_prompt,
        "n_predict": spec.n_predict,
        "prompt": _prompt_identity(spec.prompt),
        "return_tokens": RETURN_TOKENS,
        "seed": SEED,
        "slot": spec.slot,
        "stream": False,
        "temperature": TEMPERATURE,
    }


def _stream_registration(spec: StreamSpec) -> dict[str, Any]:
    return {
        "cache_prompt": spec.cache_prompt,
        "active_observation_wait_ms": spec.active_observation_wait_ms,
        "ignore_eos": spec.ignore_eos,
        "n_predict": spec.n_predict,
        "n_probs": spec.n_probs,
        "prompt": _prompt_identity(spec.prompt),
        "return_tokens": False,
        "receive_buffer_bytes": spec.receive_buffer_bytes,
        "seed": SEED,
        "slot": spec.slot,
        "stream": True,
        "temperature": TEMPERATURE,
    }


def _token_prompt_identity(prompt: tuple[int, ...]) -> dict[str, Any]:
    return {
        "sha256": sha256_bytes(canonical_json(prompt)),
        "tokens": len(prompt),
    }


def _token_prompt_registration(spec: TokenPromptSpec) -> dict[str, Any]:
    return {
        "cache_prompt": spec.cache_prompt,
        "n_cache_reuse": PREFILL_N_CACHE_REUSE,
        "n_predict": PREFILL_N_PREDICT,
        "prompt": _token_prompt_identity(spec.prompt),
        "return_tokens": PREFILL_RETURN_TOKENS,
        "seed": SEED,
        "slot": spec.slot,
        "stream": False,
        "temperature": TEMPERATURE,
    }


def registered_scenarios_v1() -> dict[str, Any]:
    """Return the exact v0.1 registration for offline evidence compatibility."""

    state_name = SLOT_STATE_NAME.encode("utf-8")
    return {
        "cache_pairing": {
            case.name: _completion_registration(case) for case in CACHE_PAIRING_CASES
        },
        "cancellation_reuse": {
            CANCELLATION_BASELINE.name: _completion_registration(CANCELLATION_BASELINE),
            CANCELLATION_STREAM.name: _stream_registration(CANCELLATION_STREAM),
            CANCELLATION_REUSE.name: _completion_registration(CANCELLATION_REUSE),
        },
        "process_order": list(PROCESS_ORDER_V1),
        "save_restore": {
            "after_restart.restored": _completion_registration(SAVE_AFTER_RESTART),
            "same_process.restored": _completion_registration(SAVE_SAME_PROCESS),
            "source": _completion_registration(SAVE_SOURCE),
            "state_filename": {
                "bytes": len(state_name),
                "sha256": sha256_bytes(state_name),
            },
        },
        "schema": REGISTRATION_SCHEMA_V1,
    }


def registered_scenarios_v2() -> dict[str, Any]:
    """Return the exact v0.2 registration for offline evidence compatibility."""

    state_name = SLOT_STATE_NAME.encode("utf-8")
    return {
        "cache_pairing": {
            case.name: _completion_registration(case) for case in CACHE_PAIRING_CASES
        },
        "cancellation_reuse": {
            CANCELLATION_BASELINE.name: _completion_registration(CANCELLATION_BASELINE),
            CANCELLATION_STREAM.name: _stream_registration(CANCELLATION_STREAM),
            CANCELLATION_REUSE.name: _completion_registration(CANCELLATION_REUSE),
        },
        "interleaving_isolation": {
            "baselines": {
                case.name: _completion_registration(case)
                for case in INTERLEAVING_BASELINES
            },
            "slot_0_cancelled_first": {
                "first_disconnect_slot": 0,
                "launch_order": [0, 1],
                "simultaneous_start_barrier": True,
                "reuses": {
                    case.name: _completion_registration(case)
                    for case in INTERLEAVING_BASELINES
                },
                "streams": {
                    stream.name: _stream_registration(stream)
                    for stream in INTERLEAVING_STREAMS
                },
            },
            "slot_1_cancelled_first": {
                "first_disconnect_slot": 1,
                "launch_order": [1, 0],
                "simultaneous_start_barrier": True,
                "reuses": {
                    case.name: _completion_registration(case)
                    for case in INTERLEAVING_BASELINES
                },
                "streams": {
                    stream.name: _stream_registration(stream)
                    for stream in INTERLEAVING_STREAMS
                },
            },
        },
        "process_order": list(PROCESS_ORDER_V2),
        "save_restore": {
            "after_restart.restored": _completion_registration(SAVE_AFTER_RESTART),
            "same_process.restored": _completion_registration(SAVE_SAME_PROCESS),
            "source": _completion_registration(SAVE_SOURCE),
            "state_filename": {
                "bytes": len(state_name),
                "sha256": sha256_bytes(state_name),
            },
        },
        "schema": REGISTRATION_SCHEMA_V2,
    }


def registered_scenarios() -> dict[str, Any]:
    """Return a fresh exact public registration without raw prompts or tokens."""

    result = registered_scenarios_v2()
    result["process_order"] = list(PROCESS_ORDER)
    result["schema"] = REGISTRATION_SCHEMA
    result["token_prefix_divergence"] = {
        case.name: {
            "cache_off_target": _token_prompt_registration(case.cache_off_target),
            "cache_on_target": _token_prompt_registration(case.cache_on_target),
            "common_prefix_tokens": case.common_prefix_tokens,
            "source": _token_prompt_registration(case.source),
        }
        for case in TOKEN_PREFIX_CASES
    }
    return result
