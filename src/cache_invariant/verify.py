"""Offline, strict validation for one CacheInvariant evidence bundle."""

from __future__ import annotations

import stat
from pathlib import Path
from typing import Any

from .oracle import all_invariants, all_invariants_v1, all_invariants_v2
from .pins import (
    CHECKPOINT,
    EVIDENCE_SCHEMA,
    EVIDENCE_SCHEMA_V1,
    EVIDENCE_SCHEMA_V2,
    FIXTURE_SOURCE_REVISION,
    GGUF_SHA256,
    MANIFEST_SCHEMA,
    PACKAGE_VERSION,
    RUNTIME_ASSETS,
    RUNTIME_CONTEXT_TOTAL,
    RUNTIME_CONTEXT_TOTAL_V1,
    RUNTIME_RELEASE,
    RUNTIME_SERVER_PINS,
    RUNTIME_SLOT_COUNT,
    RUNTIME_SOURCE_COMMIT,
    RUNTIME_VERSION_LINE,
    TOKENIZER,
)
from .registration import (
    registered_scenarios,
    registered_scenarios_v1,
    registered_scenarios_v2,
)
from .util import (
    load_json_strict,
    reject_reparse_chain,
    require_exact_keys,
    require_non_negative_int,
    require_positive_int,
    require_regular_file,
    require_sha256,
    require_source_revision,
    sha256_file,
)

EXPECTED_FILES = {"evidence.json", "junit.xml", "manifest.json"}


def _require_bool(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be a boolean")
    return value


def _validate_completion(value: object, label: str) -> dict[str, Any]:
    result = require_exact_keys(
        value,
        {
            "content_bytes",
            "content_sha256",
            "predicted_tokens",
            "prompt_work",
            "response_cached_tokens",
            "token_count",
            "tokens_sha256",
        },
        label,
    )
    require_non_negative_int(result["content_bytes"], f"{label}.content_bytes")
    require_sha256(result["content_sha256"], f"{label}.content_sha256")
    predicted = require_positive_int(
        result["predicted_tokens"],
        f"{label}.predicted_tokens",
    )
    require_non_negative_int(result["prompt_work"], f"{label}.prompt_work")
    require_non_negative_int(
        result["response_cached_tokens"],
        f"{label}.response_cached_tokens",
    )
    token_count = require_positive_int(
        result["token_count"],
        f"{label}.token_count",
    )
    if token_count != predicted:
        raise ValueError(f"{label} token count differs from predicted count")
    require_sha256(result["tokens_sha256"], f"{label}.tokens_sha256")
    return result


def _validate_case(value: object, label: str) -> dict[str, Any]:
    result = require_exact_keys(value, {"completion", "idle_slot"}, label)
    _validate_completion(result["completion"], f"{label}.completion")
    slot = require_exact_keys(
        result["idle_slot"],
        {"idle", "prompt_work"},
        f"{label}.idle_slot",
    )
    _require_bool(slot["idle"], f"{label}.idle_slot.idle")
    require_non_negative_int(
        slot["prompt_work"],
        f"{label}.idle_slot.prompt_work",
    )
    return result


def _validate_cache_pairing(value: object) -> dict[str, Any]:
    result = require_exact_keys(
        value,
        {
            "cold_cache_off",
            "cold_cache_on",
            "repeat_cache_off",
            "repeat_cache_on",
        },
        "cache_pairing",
    )
    for name in sorted(result):
        _validate_case(result[name], f"cache_pairing.{name}")
    return result


def _validate_cancellation(value: object) -> dict[str, Any]:
    result = require_exact_keys(
        value,
        {"clean_baseline", "disconnect", "reused_slot"},
        "cancellation_reuse",
    )
    _validate_case(result["clean_baseline"], "cancellation_reuse.clean_baseline")
    _validate_case(result["reused_slot"], "cancellation_reuse.reused_slot")
    disconnect = require_exact_keys(
        result["disconnect"],
        {
            "active_processing_observed",
            "first_event_nonterminal",
            "first_event_observed",
            "idle_after_disconnect",
        },
        "cancellation_reuse.disconnect",
    )
    for key, item in disconnect.items():
        _require_bool(item, f"cancellation_reuse.disconnect.{key}")
    return result


def _validate_interleaving_direction(
    value: object,
    label: str,
) -> dict[str, Any]:
    result = require_exact_keys(
        value,
        {
            "both_idle_after_second_disconnect",
            "both_first_events_before_disconnect",
            "both_processing_observed",
            "cancelled_slot_idle_after_first_disconnect",
            "reuses",
            "slot_0_first_event_nonterminal",
            "slot_0_first_event_observed",
            "slot_1_first_event_nonterminal",
            "slot_1_first_event_observed",
            "survivor_active_after_first_disconnect",
        },
        label,
    )
    reuses = require_exact_keys(
        result["reuses"],
        {"slot_0", "slot_1"},
        f"{label}.reuses",
    )
    for name in sorted(reuses):
        _validate_case(reuses[name], f"{label}.reuses.{name}")
    for key in (
        "both_idle_after_second_disconnect",
        "both_first_events_before_disconnect",
        "both_processing_observed",
        "cancelled_slot_idle_after_first_disconnect",
        "slot_0_first_event_nonterminal",
        "slot_0_first_event_observed",
        "slot_1_first_event_nonterminal",
        "slot_1_first_event_observed",
        "survivor_active_after_first_disconnect",
    ):
        _require_bool(result[key], f"{label}.{key}")
    return result


def _validate_interleaving(value: object) -> dict[str, Any]:
    result = require_exact_keys(
        value,
        {
            "baselines",
            "slot_0_cancelled_first",
            "slot_1_cancelled_first",
        },
        "interleaving_isolation",
    )
    baselines = require_exact_keys(
        result["baselines"],
        {"slot_0", "slot_1"},
        "interleaving_isolation.baselines",
    )
    for name in sorted(baselines):
        _validate_case(
            baselines[name],
            f"interleaving_isolation.baselines.{name}",
        )
    for name in ("slot_0_cancelled_first", "slot_1_cancelled_first"):
        _validate_interleaving_direction(
            result[name],
            f"interleaving_isolation.{name}",
        )
    return result


def _validate_prefill_case(value: object, label: str) -> dict[str, Any]:
    result = require_exact_keys(value, {"idle_slot", "prefill"}, label)
    prefill = require_exact_keys(
        result["prefill"],
        {
            "cache_tokens",
            "predicted_tokens",
            "prompt_tokens",
            "prompt_work",
        },
        f"{label}.prefill",
    )
    for key in sorted(prefill):
        require_non_negative_int(prefill[key], f"{label}.prefill.{key}")
    slot = require_exact_keys(
        result["idle_slot"],
        {"idle", "prompt_work"},
        f"{label}.idle_slot",
    )
    _require_bool(slot["idle"], f"{label}.idle_slot.idle")
    require_non_negative_int(
        slot["prompt_work"],
        f"{label}.idle_slot.prompt_work",
    )
    return result


def _validate_token_prefix(value: object) -> dict[str, Any]:
    result = require_exact_keys(
        value,
        {"exact", "first_token_divergence", "shared_prefix"},
        "token_prefix_divergence",
    )
    for name in sorted(result):
        case = require_exact_keys(
            result[name],
            {"cache_off_target", "cache_on_target", "source"},
            f"token_prefix_divergence.{name}",
        )
        for observation in sorted(case):
            _validate_prefill_case(
                case[observation],
                f"token_prefix_divergence.{name}.{observation}",
            )
    return result


def _validate_save_restore(value: object) -> dict[str, Any]:
    result = require_exact_keys(
        value,
        {
            "after_restart",
            "process_restart_confirmed",
            "same_process",
            "saved_tokens",
            "slot_state_after_restart",
            "slot_state_before_restart",
            "source",
        },
        "save_restore",
    )
    _validate_case(result["source"], "save_restore.source")
    require_positive_int(result["saved_tokens"], "save_restore.saved_tokens")
    _require_bool(
        result["process_restart_confirmed"],
        "save_restore.process_restart_confirmed",
    )
    for name in ("same_process", "after_restart"):
        restored = require_exact_keys(
            result[name],
            {"restored", "restored_tokens"},
            f"save_restore.{name}",
        )
        _validate_case(restored["restored"], f"save_restore.{name}.restored")
        require_positive_int(
            restored["restored_tokens"],
            f"save_restore.{name}.restored_tokens",
        )
    for name in ("slot_state_before_restart", "slot_state_after_restart"):
        state = require_exact_keys(
            result[name],
            {"bytes", "sha256"},
            f"save_restore.{name}",
        )
        require_positive_int(state["bytes"], f"save_restore.{name}.bytes")
        require_sha256(state["sha256"], f"save_restore.{name}.sha256")
    return result


def validate_evidence(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("evidence must be an object")
    schema = value.get("schema")
    if schema not in {EVIDENCE_SCHEMA_V1, EVIDENCE_SCHEMA_V2, EVIDENCE_SCHEMA}:
        raise ValueError("evidence schema is not registered")
    if schema == EVIDENCE_SCHEMA_V1:
        expected_version = "0.1.0"
        expected_registration = registered_scenarios_v1()
        include_interleaving = False
        include_token_prefix = False
        compute_invariants = all_invariants_v1
    elif schema == EVIDENCE_SCHEMA_V2:
        expected_version = "0.2.0"
        expected_registration = registered_scenarios_v2()
        include_interleaving = True
        include_token_prefix = False
        compute_invariants = all_invariants_v2
    else:
        expected_version = PACKAGE_VERSION
        expected_registration = registered_scenarios()
        include_interleaving = True
        include_token_prefix = True
        compute_invariants = all_invariants
    expected_keys = {
        "boundary",
        "cache_pairing",
        "cancellation_reuse",
        "fixture",
        "invariants",
        "producer",
        "registration",
        "runtime",
        "save_restore",
        "schema",
        "source_revision",
        "transport",
    }
    if include_interleaving:
        expected_keys.add("interleaving_isolation")
    if include_token_prefix:
        expected_keys.add("token_prefix_divergence")
    evidence = require_exact_keys(
        value,
        expected_keys,
        "evidence",
    )
    producer = require_exact_keys(
        evidence["producer"],
        {"name", "version"},
        "producer",
    )
    if producer != {"name": "cache-invariant", "version": expected_version}:
        raise ValueError("evidence producer is not registered")
    require_source_revision(evidence["source_revision"], "source_revision")
    if evidence["registration"] != expected_registration:
        raise ValueError("scenario registration differs")

    fixture = require_exact_keys(
        evidence["fixture"],
        {
            "checkpoint_sha256",
            "model_sha256",
            "source_revision",
            "tokenizer_sha256",
        },
        "fixture",
    )
    expected_fixture = {
        "checkpoint_sha256": CHECKPOINT.sha256,
        "model_sha256": GGUF_SHA256,
        "source_revision": FIXTURE_SOURCE_REVISION,
        "tokenizer_sha256": TOKENIZER.sha256,
    }
    if fixture != expected_fixture:
        raise ValueError("fixture pins are not registered")

    runtime = require_exact_keys(
        evidence["runtime"],
        {
            "adapter",
            "asset_platform",
            "asset_sha256",
            "configured_context_total",
            "cpu_only",
            "offline",
            "release",
            "server_sha256",
            "slot_count",
            "source_commit",
            "version_line",
        },
        "runtime",
    )
    platform_key = runtime["asset_platform"]
    if platform_key not in RUNTIME_ASSETS:
        raise ValueError("runtime asset platform is not registered")
    expected_runtime = {
        "adapter": "llama.cpp-server",
        "asset_platform": platform_key,
        "asset_sha256": RUNTIME_ASSETS[platform_key].sha256,
        "configured_context_total": (
            RUNTIME_CONTEXT_TOTAL_V1
            if schema == EVIDENCE_SCHEMA_V1
            else RUNTIME_CONTEXT_TOTAL
        ),
        "cpu_only": True,
        "offline": True,
        "release": RUNTIME_RELEASE,
        "server_sha256": RUNTIME_SERVER_PINS[platform_key]["sha256"],
        "slot_count": RUNTIME_SLOT_COUNT,
        "source_commit": RUNTIME_SOURCE_COMMIT,
        "version_line": RUNTIME_VERSION_LINE,
    }
    if runtime != expected_runtime:
        raise ValueError("runtime pins or configuration are not registered")

    transport = require_exact_keys(
        evidence["transport"],
        {"api_key_enabled", "endpoint", "proxy_bypass"},
        "transport",
    )
    if transport != {
        "api_key_enabled": True,
        "endpoint": "loopback-redacted",
        "proxy_bypass": True,
    }:
        raise ValueError("transport boundary differs")

    boundary = require_exact_keys(
        evidence["boundary"],
        {
            "absolute_paths_included",
            "generated_text_included",
            "hostnames_included",
            "performance_claim_included",
            "ports_included",
            "raw_server_logs_included",
            "raw_token_lists_included",
        },
        "boundary",
    )
    if any(_require_bool(item, f"boundary.{key}") for key, item in boundary.items()):
        raise ValueError("evidence boundary reports forbidden content")

    _validate_cache_pairing(evidence["cache_pairing"])
    _validate_cancellation(evidence["cancellation_reuse"])
    if include_interleaving:
        _validate_interleaving(evidence["interleaving_isolation"])
    if include_token_prefix:
        _validate_token_prefix(evidence["token_prefix_divergence"])
    _validate_save_restore(evidence["save_restore"])
    computed = compute_invariants(evidence)
    invariants = require_exact_keys(
        evidence["invariants"],
        set(computed),
        "invariants",
    )
    for key, item in invariants.items():
        _require_bool(item, f"invariants.{key}")
    if invariants != computed:
        raise ValueError("stored invariants differ from the recomputed oracle")
    failed = sorted(name for name, passed in invariants.items() if not passed)
    if failed:
        raise ValueError(f"runtime invariants failed: {failed}")
    return evidence


def junit_bytes(invariants: dict[str, bool]) -> bytes:
    names = sorted(invariants)
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            f'<testsuite name="cache-invariant" tests="{len(names)}" '
            'failures="0" errors="0" skipped="0">'
        ),
    ]
    lines.extend(
        (f'<testcase classname="cache_invariant.runtime" name="{name}"/>')
        for name in names
    )
    lines.append("</testsuite>")
    return ("\n".join(lines) + "\n").encode("utf-8")


def _validate_manifest(
    directory: Path,
    value: object,
) -> dict[str, Any]:
    manifest = require_exact_keys(value, {"files", "schema"}, "manifest")
    if manifest["schema"] != MANIFEST_SCHEMA:
        raise ValueError("manifest schema is not registered")
    files = manifest["files"]
    if not isinstance(files, list) or len(files) != 2:
        raise ValueError("manifest must contain exactly two file records")
    seen: set[str] = set()
    for index, item in enumerate(files):
        record = require_exact_keys(
            item,
            {"bytes", "path", "sha256"},
            f"manifest.files[{index}]",
        )
        path_value = record["path"]
        if path_value not in {"evidence.json", "junit.xml"} or path_value in seen:
            raise ValueError("manifest file path is unexpected or duplicated")
        seen.add(path_value)
        require_positive_int(record["bytes"], "manifest file bytes")
        require_sha256(record["sha256"], "manifest file SHA-256")
        path = directory / path_value
        require_regular_file(path, f"manifest file {path_value}")
        if path.stat().st_size != record["bytes"]:
            raise ValueError("manifest file byte count differs")
        if sha256_file(path) != record["sha256"]:
            raise ValueError("manifest file SHA-256 differs")
    if seen != {"evidence.json", "junit.xml"}:
        raise ValueError("manifest file set differs")
    return manifest


def verify_bundle(directory: Path) -> dict[str, Any]:
    reject_reparse_chain(directory, "evidence bundle")
    metadata = directory.lstat()
    attributes = getattr(metadata, "st_file_attributes", 0)
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or attributes & 0x400
    ):
        raise ValueError("evidence bundle must be a non-reparse directory")
    entries = list(directory.iterdir())
    if {item.name for item in entries} != EXPECTED_FILES:
        raise ValueError("evidence bundle file set differs")
    for item in entries:
        require_regular_file(item, f"evidence bundle file {item.name}")

    _validate_manifest(
        directory,
        load_json_strict(directory / "manifest.json", max_bytes=128 * 1024),
    )
    evidence = validate_evidence(
        load_json_strict(directory / "evidence.json", max_bytes=512 * 1024)
    )
    actual_junit = (directory / "junit.xml").read_bytes()
    expected_junit = junit_bytes(evidence["invariants"])
    if actual_junit != expected_junit:
        raise ValueError("JUnit projection differs from verified invariants")
    return {
        "invariant_count": len(evidence["invariants"]),
        "platform": evidence["runtime"]["asset_platform"],
        "schema": evidence["schema"],
    }
