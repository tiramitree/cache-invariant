"""Real-runtime scenario orchestration and normalized evidence assembly."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from .adapter import LlamaCppClient
from .fetch import extract_fresh_runtime, validate_lock
from .oracle import all_invariants
from .pins import (
    CHECKPOINT,
    EVIDENCE_SCHEMA,
    FIXTURE_SOURCE_REVISION,
    GGUF_SHA256,
    PACKAGE_VERSION,
    RUNTIME_CONTEXT_TOTAL,
    RUNTIME_RELEASE,
    RUNTIME_SERVER_PINS,
    RUNTIME_SLOT_COUNT,
    RUNTIME_SOURCE_COMMIT,
    RUNTIME_VERSION_LINE,
    TOKENIZER,
)
from .process import ServerProcess
from .registration import (
    CACHE_PAIRING_CASES,
    CANCELLATION_BASELINE,
    CANCELLATION_REUSE,
    CANCELLATION_STREAM,
    INTERLEAVING_BASELINES,
    INTERLEAVING_STREAMS,
    PREFILL_N_CACHE_REUSE,
    PREFILL_N_PREDICT,
    PREFILL_RETURN_TOKENS,
    PROCESS_ORDER,
    RETURN_TOKENS,
    SAVE_AFTER_RESTART,
    SAVE_SAME_PROCESS,
    SAVE_SOURCE,
    SEED,
    SLOT_STATE_NAME,
    TEMPERATURE,
    TOKEN_PREFIX_CASES,
    CompletionSpec,
    TokenPromptSpec,
    registered_scenarios,
)
from .util import require_regular_file, require_source_revision, sha256_file

if not RETURN_TOKENS:
    raise RuntimeError("registered non-streaming completions require token hashes")
if PREFILL_RETURN_TOKENS:
    raise RuntimeError("registered direct-token probes must discard generated tokens")


def _completion_case(
    client: LlamaCppClient,
    spec: CompletionSpec,
) -> dict[str, Any]:
    return client.completion_case(
        spec.slot,
        spec.prompt,
        cache_prompt=spec.cache_prompt,
        n_predict=spec.n_predict,
        seed=SEED,
        temperature=TEMPERATURE,
    )


def _cache_pairing(
    client: LlamaCppClient,
    trace: list[str],
) -> dict[str, Any]:
    client.erase(0)
    trace.append("cache_pairing.erase_slot_0")
    client.erase(1)
    trace.append("cache_pairing.erase_slot_1")
    result: dict[str, Any] = {}
    for case in CACHE_PAIRING_CASES:
        result[case.name] = _completion_case(client, case)
        trace.append(f"cache_pairing.{case.name}")
    return result


def _cancellation_reuse(
    client: LlamaCppClient,
    trace: list[str],
) -> dict[str, Any]:
    client.erase(0)
    trace.append("cancellation_reuse.erase_slot_0")
    client.erase(1)
    trace.append("cancellation_reuse.erase_slot_1")
    baseline = _completion_case(client, CANCELLATION_BASELINE)
    trace.append("cancellation_reuse.clean_baseline")
    disconnect = client.stream_then_disconnect(
        CANCELLATION_STREAM.slot,
        CANCELLATION_STREAM.prompt,
        cache_prompt=CANCELLATION_STREAM.cache_prompt,
        ignore_eos=CANCELLATION_STREAM.ignore_eos,
        n_predict=CANCELLATION_STREAM.n_predict,
        n_probs=CANCELLATION_STREAM.n_probs,
        receive_buffer_bytes=CANCELLATION_STREAM.receive_buffer_bytes,
        active_observation_wait_ms=(CANCELLATION_STREAM.active_observation_wait_ms),
        seed=SEED,
        temperature=TEMPERATURE,
    )
    trace.append("cancellation_reuse.disconnect")
    reused = _completion_case(client, CANCELLATION_REUSE)
    trace.append("cancellation_reuse.reused_slot")
    return {
        "clean_baseline": baseline,
        "disconnect": disconnect,
        "reused_slot": reused,
    }


def _save_restore_same_process(
    client: LlamaCppClient,
    trace: list[str],
) -> dict[str, Any]:
    client.erase(0)
    trace.append("save_restore.erase_slot_0")
    client.erase(1)
    trace.append("save_restore.erase_slot_1")
    source = _completion_case(client, SAVE_SOURCE)
    trace.append("save_restore.source")
    saved_tokens = client.save(0, SLOT_STATE_NAME)
    trace.append("save_restore.save_slot_0")
    restored_tokens = client.restore(1, SLOT_STATE_NAME)
    trace.append("save_restore.restore_slot_1")
    restored = _completion_case(client, SAVE_SAME_PROCESS)
    trace.append("save_restore.same_process.restored")
    return {
        "saved_tokens": saved_tokens,
        "same_process": {
            "restored": restored,
            "restored_tokens": restored_tokens,
        },
        "source": source,
    }


def _erase_registered_slots(
    client: LlamaCppClient, trace: list[str], prefix: str
) -> None:
    client.erase(0)
    trace.append(f"{prefix}.erase_slot_0")
    client.erase(1)
    trace.append(f"{prefix}.erase_slot_1")


def _interleaving_direction(
    client: LlamaCppClient,
    trace: list[str],
    *,
    first_disconnect_slot: int,
) -> dict[str, Any]:
    first, second = INTERLEAVING_STREAMS
    shared_fields = (
        "cache_prompt",
        "ignore_eos",
        "n_predict",
        "n_probs",
        "receive_buffer_bytes",
        "active_observation_wait_ms",
    )
    if any(getattr(first, name) != getattr(second, name) for name in shared_fields):
        raise RuntimeError("registered dual-stream controls differed")
    result = client.dual_stream_disconnect(
        (first.prompt, second.prompt),
        cache_prompt=first.cache_prompt,
        ignore_eos=first.ignore_eos,
        n_predict=first.n_predict,
        n_probs=first.n_probs,
        receive_buffer_bytes=first.receive_buffer_bytes,
        active_observation_wait_ms=first.active_observation_wait_ms,
        first_disconnect_slot=first_disconnect_slot,
        seed=SEED,
        temperature=TEMPERATURE,
    )
    name = f"slot_{first_disconnect_slot}_cancelled_first"
    trace.append(f"interleaving_isolation.{name}.dual_stream_disconnect")
    result["reuses"] = {}
    for case in INTERLEAVING_BASELINES:
        result["reuses"][case.name] = _completion_case(client, case)
        trace.append(f"interleaving_isolation.{name}.{case.name}_reuse")
    return result


def _interleaving_isolation(
    client: LlamaCppClient,
    trace: list[str],
) -> dict[str, Any]:
    prefix = "interleaving_isolation"
    _erase_registered_slots(client, trace, prefix)
    baselines: dict[str, Any] = {}
    for case in INTERLEAVING_BASELINES:
        baselines[case.name] = _completion_case(client, case)
        trace.append(f"{prefix}.baselines.{case.name}")

    _erase_registered_slots(client, trace, prefix)
    slot_0_first = _interleaving_direction(
        client,
        trace,
        first_disconnect_slot=0,
    )
    _erase_registered_slots(client, trace, prefix)
    slot_1_first = _interleaving_direction(
        client,
        trace,
        first_disconnect_slot=1,
    )
    return {
        "baselines": baselines,
        "slot_0_cancelled_first": slot_0_first,
        "slot_1_cancelled_first": slot_1_first,
    }


def _direct_token_prefill_case(
    client: LlamaCppClient,
    spec: TokenPromptSpec,
) -> dict[str, Any]:
    return client.direct_token_prefill_case(
        spec.slot,
        spec.prompt,
        cache_prompt=spec.cache_prompt,
        n_cache_reuse=PREFILL_N_CACHE_REUSE,
        n_predict=PREFILL_N_PREDICT,
        seed=SEED,
        temperature=TEMPERATURE,
    )


def _token_prefix_divergence(
    client: LlamaCppClient,
    trace: list[str],
) -> dict[str, Any]:
    prefix = "token_prefix_divergence"
    result: dict[str, Any] = {}
    for case in TOKEN_PREFIX_CASES:
        client.erase(0)
        trace.append(f"{prefix}.{case.name}.erase_slot_0")
        source = _direct_token_prefill_case(client, case.source)
        trace.append(f"{prefix}.{case.name}.source")
        cache_on_target = _direct_token_prefill_case(
            client,
            case.cache_on_target,
        )
        trace.append(f"{prefix}.{case.name}.cache_on_target")
        client.erase(0)
        trace.append(f"{prefix}.{case.name}.erase_slot_0")
        cache_off_target = _direct_token_prefill_case(
            client,
            case.cache_off_target,
        )
        trace.append(f"{prefix}.{case.name}.cache_off_target")
        result[case.name] = {
            "cache_off_target": cache_off_target,
            "cache_on_target": cache_on_target,
            "source": source,
        }
    return result


def _restore_after_restart(
    client: LlamaCppClient,
    trace: list[str],
) -> dict[str, Any]:
    client.erase(0)
    trace.append("save_restore.erase_slot_0")
    restored_tokens = client.restore(0, SLOT_STATE_NAME)
    trace.append("save_restore.restore_slot_0")
    restored = _completion_case(client, SAVE_AFTER_RESTART)
    trace.append("save_restore.after_restart.restored")
    return {
        "restored": restored,
        "restored_tokens": restored_tokens,
    }


def build_evidence(
    *,
    platform_key: str,
    cache_pairing: dict[str, Any],
    cancellation_reuse: dict[str, Any],
    interleaving_isolation: dict[str, Any],
    save_restore: dict[str, Any],
    source_revision: str,
    token_prefix_divergence: dict[str, Any],
) -> dict[str, Any]:
    require_source_revision(source_revision, "source revision")
    evidence: dict[str, Any] = {
        "boundary": {
            "absolute_paths_included": False,
            "generated_text_included": False,
            "hostnames_included": False,
            "performance_claim_included": False,
            "ports_included": False,
            "raw_server_logs_included": False,
            "raw_token_lists_included": False,
        },
        "cache_pairing": cache_pairing,
        "cancellation_reuse": cancellation_reuse,
        "fixture": {
            "checkpoint_sha256": CHECKPOINT.sha256,
            "model_sha256": GGUF_SHA256,
            "source_revision": FIXTURE_SOURCE_REVISION,
            "tokenizer_sha256": TOKENIZER.sha256,
        },
        "interleaving_isolation": interleaving_isolation,
        "producer": {
            "name": "cache-invariant",
            "version": PACKAGE_VERSION,
        },
        "registration": registered_scenarios(),
        "runtime": {
            "adapter": "llama.cpp-server",
            "asset_platform": platform_key,
            "asset_sha256": validate_asset_sha256(platform_key),
            "configured_context_total": RUNTIME_CONTEXT_TOTAL,
            "cpu_only": True,
            "offline": True,
            "release": RUNTIME_RELEASE,
            "server_sha256": RUNTIME_SERVER_PINS[platform_key]["sha256"],
            "slot_count": RUNTIME_SLOT_COUNT,
            "source_commit": RUNTIME_SOURCE_COMMIT,
            "version_line": RUNTIME_VERSION_LINE,
        },
        "save_restore": save_restore,
        "schema": EVIDENCE_SCHEMA,
        "source_revision": source_revision,
        "token_prefix_divergence": token_prefix_divergence,
        "transport": {
            "api_key_enabled": True,
            "endpoint": "loopback-redacted",
            "proxy_bypass": True,
        },
    }
    evidence["invariants"] = all_invariants(evidence)
    return evidence


def validate_asset_sha256(platform_key: str) -> str:
    from .pins import RUNTIME_ASSETS

    return RUNTIME_ASSETS[platform_key].sha256


def run_scenarios(lock_path: Path, *, source_revision: str) -> dict[str, Any]:
    require_source_revision(source_revision, "source revision")
    resolved = validate_lock(lock_path, require_model=True)
    platform_key: str = resolved["platform"]
    parent = lock_path.parent
    with tempfile.TemporaryDirectory(
        prefix=".cache-invariant-run-",
        dir=parent,
    ) as temporary_value:
        temporary = Path(temporary_value)
        runtime = temporary / "runtime"
        server = extract_fresh_runtime(
            resolved["archive"],
            runtime,
            platform_key,
        )
        slots = temporary / "slot-state"

        first = ServerProcess(
            server=server,
            model=resolved["model"],
            slot_directory=slots,
            temporary_directory=temporary,
        )
        trace: list[str] = []
        with first as client:
            trace.append("start_server_1")
            cache_pairing = _cache_pairing(client, trace)
            cancellation_reuse = _cancellation_reuse(client, trace)
            interleaving_isolation = _interleaving_isolation(client, trace)
            token_prefix_divergence = _token_prefix_divergence(client, trace)
            save_restore = _save_restore_same_process(client, trace)
        trace.append("stop_server_1")
        # ServerProcess.stop has verified termination, including the captured
        # Windows process tree, before the second process is created.
        process_restart_confirmed = first.process is None
        state_file = slots / SLOT_STATE_NAME
        require_regular_file(state_file, "saved slot state")
        save_restore["slot_state_before_restart"] = {
            "bytes": state_file.stat().st_size,
            "sha256": sha256_file(state_file),
        }
        trace.append("hash_slot_state_before_restart")

        second = ServerProcess(
            server=server,
            model=resolved["model"],
            slot_directory=slots,
            temporary_directory=temporary,
        )
        with second as client:
            trace.append("start_server_2")
            save_restore["after_restart"] = _restore_after_restart(client, trace)
        trace.append("stop_server_2")
        process_restart_confirmed = process_restart_confirmed and second.process is None
        require_regular_file(state_file, "saved slot state after restart")
        save_restore["slot_state_after_restart"] = {
            "bytes": state_file.stat().st_size,
            "sha256": sha256_file(state_file),
        }
        trace.append("hash_slot_state_after_restart")
        save_restore["process_restart_confirmed"] = process_restart_confirmed
        if trace != list(PROCESS_ORDER):
            raise RuntimeError("executed process order differed from registration")

        evidence = build_evidence(
            platform_key=platform_key,
            cache_pairing=cache_pairing,
            cancellation_reuse=cancellation_reuse,
            interleaving_isolation=interleaving_isolation,
            save_restore=save_restore,
            source_revision=source_revision,
            token_prefix_divergence=token_prefix_divergence,
        )
        failed = sorted(
            name for name, passed in evidence["invariants"].items() if not passed
        )
        if failed:
            raise RuntimeError(f"registered runtime invariants failed: {failed}")
        return evidence
