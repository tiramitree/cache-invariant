"""Narrow HTTP adapter for the registered llama.cpp server interface."""

from __future__ import annotations

import http.client
import json
import socket
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from .pins import RUNTIME_SLOT_COUNT
from .util import canonical_json, require_non_negative_int, sha256_bytes

MAX_RESPONSE_BYTES = 2 * 1024 * 1024


def _decode_json(raw: bytes) -> Any:
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError("server response exceeded the bounded JSON size")

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("server JSON contained a duplicate key")
            result[key] = value
        return result

    try:
        return json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda _value: (_ for _ in ()).throw(
                ValueError("server JSON contained a non-finite value")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("server response was not valid UTF-8 JSON") from error


def _stream_event_is_nonterminal(raw: bytes) -> bool:
    line = raw.strip()
    prefix = b"data: "
    if not line.startswith(prefix):
        raise ValueError("streaming event lacked the registered SSE prefix")
    value = _decode_json(line[len(prefix) :])
    if not isinstance(value, dict):
        raise ValueError("streaming event was not an object")
    stopped = value.get("stop")
    if not isinstance(stopped, bool):
        raise ValueError("streaming event stop state was not a boolean")
    return not stopped


def _validated_slots(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError("slots endpoint did not return a list")
    if len(value) != RUNTIME_SLOT_COUNT:
        raise ValueError("registered adapter requires exactly two slots")
    if not all(isinstance(item, dict) for item in value):
        raise ValueError("slot entry was not an object")
    ids = [item.get("id") for item in value]
    if any(isinstance(item, bool) or not isinstance(item, int) for item in ids) or set(
        ids
    ) != {0, 1}:
        raise ValueError("slot IDs differed from the registered pair")
    return value


def _slot_view_from_values(
    values: list[dict[str, Any]],
    slot_id: int,
) -> dict[str, Any]:
    for value in values:
        if value.get("id") == slot_id:
            processing = value.get("is_processing")
            if not isinstance(processing, bool):
                raise ValueError("slot processing state was not a boolean")
            processed = require_non_negative_int(
                value.get("n_prompt_tokens_processed"),
                "slot prompt-work count",
            )
            return {
                "idle": not processing,
                "prompt_work": processed,
            }
    raise ValueError("selected slot was not present")


@dataclass(frozen=True)
class LlamaCppClient:
    port: int
    api_key: str

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def request_json(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        *,
        timeout: float = 20.0,
    ) -> Any:
        payload = None if body is None else canonical_json(body)
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=payload,
            method=method,
            headers=self._headers(),
        )
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(request, timeout=timeout) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as error:
            raise RuntimeError(f"server returned HTTP {error.code}") from error
        return _decode_json(raw)

    def health_ok(self) -> bool:
        try:
            value = self.request_json("GET", "/health", timeout=1.0)
        except (OSError, RuntimeError, ValueError):
            return False
        return isinstance(value, dict) and value.get("status") == "ok"

    def slots(self, *, timeout: float = 20.0) -> list[dict[str, Any]]:
        value = self.request_json("GET", "/slots", timeout=timeout)
        return _validated_slots(value)

    def slot_view(
        self,
        slot_id: int,
        *,
        timeout: float = 20.0,
    ) -> dict[str, Any]:
        return _slot_view_from_values(self.slots(timeout=timeout), slot_id)

    def erase(self, slot_id: int) -> None:
        value = self.request_json(
            "POST",
            f"/slots/{slot_id}?action=erase",
            {},
        )
        acknowledged = value.get("id_slot") if isinstance(value, dict) else None
        if (
            isinstance(acknowledged, bool)
            or not isinstance(acknowledged, int)
            or acknowledged != slot_id
        ):
            raise ValueError("slot erase acknowledgement differed")

    def completion(
        self,
        slot_id: int,
        prompt: str,
        *,
        cache_prompt: bool,
        n_predict: int,
        seed: int,
        temperature: int,
    ) -> dict[str, Any]:
        value = self.request_json(
            "POST",
            "/completion",
            {
                "cache_prompt": cache_prompt,
                "id_slot": slot_id,
                "n_predict": n_predict,
                "prompt": prompt,
                "return_tokens": True,
                "seed": seed,
                "stream": False,
                "temperature": temperature,
            },
            timeout=30.0,
        )
        if not isinstance(value, dict):
            raise ValueError("completion response was not an object")
        content = value.get("content")
        tokens = value.get("tokens")
        timings = value.get("timings")
        if not isinstance(content, str):
            raise ValueError("completion content was not a string")
        if not isinstance(tokens, list) or any(
            isinstance(item, bool) or not isinstance(item, int) for item in tokens
        ):
            raise ValueError("completion token list was malformed")
        if not isinstance(timings, dict):
            raise ValueError("completion timings were missing")
        prompt_work = require_non_negative_int(
            timings.get("prompt_n"),
            "completion prompt-work count",
        )
        predicted = require_non_negative_int(
            timings.get("predicted_n"),
            "completion predicted-token count",
        )
        response_cached = require_non_negative_int(
            value.get("tokens_cached"),
            "completion response cache count",
        )
        content_bytes = content.encode("utf-8")
        if predicted <= 0 or len(tokens) != predicted:
            raise ValueError(
                "returned token list did not match the positive predicted count"
            )
        return {
            "content_bytes": len(content_bytes),
            "content_sha256": sha256_bytes(content_bytes),
            "predicted_tokens": predicted,
            "prompt_work": prompt_work,
            "response_cached_tokens": response_cached,
            "token_count": len(tokens),
            "tokens_sha256": sha256_bytes(canonical_json(tokens)),
        }

    def completion_case(
        self,
        slot_id: int,
        prompt: str,
        *,
        cache_prompt: bool,
        n_predict: int,
        seed: int,
        temperature: int,
    ) -> dict[str, Any]:
        completion = self.completion(
            slot_id,
            prompt,
            cache_prompt=cache_prompt,
            n_predict=n_predict,
            seed=seed,
            temperature=temperature,
        )
        return {
            "completion": completion,
            "idle_slot": self.slot_view(slot_id),
        }

    def direct_token_prefill(
        self,
        slot_id: int,
        prompt: tuple[int, ...],
        *,
        cache_prompt: bool,
        n_cache_reuse: int,
        n_predict: int,
        seed: int,
        temperature: int,
    ) -> dict[str, int]:
        if not prompt or any(
            isinstance(token, bool) or not isinstance(token, int) or token < 0
            for token in prompt
        ):
            raise ValueError("direct-token prompt was malformed")
        value = self.request_json(
            "POST",
            "/completion",
            {
                "cache_prompt": cache_prompt,
                "id_slot": slot_id,
                "n_cache_reuse": n_cache_reuse,
                "n_predict": n_predict,
                "prompt": list(prompt),
                "return_tokens": False,
                "seed": seed,
                "stream": False,
                "temperature": temperature,
            },
            timeout=30.0,
        )
        if not isinstance(value, dict):
            raise ValueError("direct-token completion response was not an object")
        timings = value.get("timings")
        if not isinstance(timings, dict):
            raise ValueError("direct-token completion timings were missing")
        return {
            "cache_tokens": require_non_negative_int(
                timings.get("cache_n"),
                "direct-token cache count",
            ),
            "predicted_tokens": require_non_negative_int(
                timings.get("predicted_n"),
                "direct-token predicted count",
            ),
            "prompt_tokens": require_non_negative_int(
                value.get("tokens_evaluated"),
                "direct-token evaluated count",
            ),
            "prompt_work": require_non_negative_int(
                timings.get("prompt_n"),
                "direct-token prompt-work count",
            ),
        }

    def direct_token_prefill_case(
        self,
        slot_id: int,
        prompt: tuple[int, ...],
        *,
        cache_prompt: bool,
        n_cache_reuse: int,
        n_predict: int,
        seed: int,
        temperature: int,
    ) -> dict[str, Any]:
        prefill = self.direct_token_prefill(
            slot_id,
            prompt,
            cache_prompt=cache_prompt,
            n_cache_reuse=n_cache_reuse,
            n_predict=n_predict,
            seed=seed,
            temperature=temperature,
        )
        return {
            "idle_slot": self.slot_view(slot_id),
            "prefill": prefill,
        }

    def _open_registered_stream(
        self,
        slot_id: int,
        prompt: str,
        *,
        cache_prompt: bool,
        ignore_eos: bool,
        n_predict: int,
        n_probs: int,
        receive_buffer_bytes: int,
        seed: int,
        temperature: int,
    ) -> tuple[http.client.HTTPConnection, http.client.HTTPResponse]:
        payload = canonical_json(
            {
                "cache_prompt": cache_prompt,
                "id_slot": slot_id,
                "ignore_eos": ignore_eos,
                "n_predict": n_predict,
                "n_probs": n_probs,
                "prompt": prompt,
                "return_tokens": False,
                "seed": seed,
                "stream": True,
                "temperature": temperature,
            }
        )
        connection = http.client.HTTPConnection(
            "127.0.0.1",
            self.port,
            timeout=10.0,
        )
        try:
            connection.connect()
            if connection.sock is None:
                raise RuntimeError("streaming socket was not connected")
            connection.sock.setsockopt(
                socket.SOL_SOCKET,
                socket.SO_RCVBUF,
                receive_buffer_bytes,
            )
            connection.request(
                "POST",
                "/completion",
                body=payload,
                headers=self._headers(),
            )
            response = connection.getresponse()
            if response.status != 200:
                response.close()
                raise RuntimeError(f"streaming request returned HTTP {response.status}")
            return connection, response
        except BaseException:
            connection.close()
            raise

    def stream_then_disconnect(
        self,
        slot_id: int,
        prompt: str,
        *,
        cache_prompt: bool,
        ignore_eos: bool,
        n_predict: int,
        n_probs: int,
        receive_buffer_bytes: int,
        active_observation_wait_ms: int,
        seed: int,
        temperature: int,
    ) -> dict[str, bool]:
        active_observed = threading.Event()
        sampler_ready = threading.Event()
        sampler_stop = threading.Event()

        def sample_processing_state() -> None:
            slot_connection = http.client.HTTPConnection(
                "127.0.0.1",
                self.port,
                timeout=0.25,
            )
            try:
                while not sampler_stop.is_set():
                    try:
                        slot_connection.request(
                            "GET",
                            "/slots",
                            headers=self._headers(),
                        )
                        slot_response = slot_connection.getresponse()
                        raw = slot_response.read(MAX_RESPONSE_BYTES + 1)
                        status = slot_response.status
                        slot_response.close()
                        if status != 200:
                            raise RuntimeError(f"slots sampler returned HTTP {status}")
                        values = _validated_slots(_decode_json(raw))
                        sampler_ready.set()
                        if not _slot_view_from_values(values, slot_id)["idle"]:
                            active_observed.set()
                            return
                    except (OSError, RuntimeError, ValueError):
                        slot_connection.close()
                        slot_connection = http.client.HTTPConnection(
                            "127.0.0.1",
                            self.port,
                            timeout=0.25,
                        )
                    sampler_stop.wait(0.001)
            finally:
                slot_connection.close()

        sampler = threading.Thread(
            target=sample_processing_state,
            daemon=True,
        )
        sampler.start()
        if not sampler_ready.wait(2.0):
            sampler_stop.set()
            sampler.join(timeout=2.0)
            raise RuntimeError("slot-state sampler did not become ready")
        connection: http.client.HTTPConnection | None = None
        response: http.client.HTTPResponse | None = None
        try:
            connection, response = self._open_registered_stream(
                slot_id,
                prompt,
                cache_prompt=cache_prompt,
                ignore_eos=ignore_eos,
                n_predict=n_predict,
                n_probs=n_probs,
                receive_buffer_bytes=receive_buffer_bytes,
                seed=seed,
                temperature=temperature,
            )
            active_observed.wait(active_observation_wait_ms / 1_000)
            first_event = response.readline(MAX_RESPONSE_BYTES + 1)
            if len(first_event) > MAX_RESPONSE_BYTES:
                raise ValueError("streaming event exceeded the bounded size")
            first_event_nonterminal = _stream_event_is_nonterminal(first_event)
        finally:
            if response is not None:
                response.close()
            if connection is not None:
                connection.close()
            sampler_stop.set()
            sampler.join(timeout=2.0)
            if sampler.is_alive():
                raise RuntimeError("slot-state sampler did not stop")

        idle_observed = False
        started = time.monotonic()
        while time.monotonic() - started < 15.0:
            if self.slot_view(slot_id)["idle"]:
                idle_observed = True
                break
            time.sleep(0.01)
        return {
            "active_processing_observed": active_observed.is_set(),
            "first_event_observed": bool(first_event),
            "first_event_nonterminal": first_event_nonterminal,
            "idle_after_disconnect": idle_observed,
        }

    def dual_stream_disconnect(
        self,
        slot_prompts: tuple[str, str],
        *,
        cache_prompt: bool,
        ignore_eos: bool,
        n_predict: int,
        n_probs: int,
        receive_buffer_bytes: int,
        active_observation_wait_ms: int,
        first_disconnect_slot: int,
        seed: int,
        temperature: int,
    ) -> dict[str, Any]:
        if first_disconnect_slot not in {0, 1}:
            raise ValueError("first disconnect slot must be one of the registered pair")
        connections: list[http.client.HTTPConnection | None] = [None, None]
        responses: list[http.client.HTTPResponse | None] = [None, None]
        first_events: list[bytes] = [b"", b""]
        first_event_ready = [threading.Event(), threading.Event()]
        release_stream = [threading.Event(), threading.Event()]
        start_barrier = threading.Barrier(3)
        worker_errors: list[BaseException] = []
        state_lock = threading.Lock()
        both_first_events_before_disconnect = False
        both_processing_observed = False
        cancelled_slot_idle = False
        survivor_active_after_first_disconnect = False
        both_idle_after_second_disconnect = False
        survivor_slot = 1 - first_disconnect_slot

        def stream_worker(slot_id: int, prompt: str) -> None:
            connection: http.client.HTTPConnection | None = None
            response: http.client.HTTPResponse | None = None
            try:
                start_barrier.wait(timeout=2.0)
                connection, response = self._open_registered_stream(
                    slot_id,
                    prompt,
                    cache_prompt=cache_prompt,
                    ignore_eos=ignore_eos,
                    n_predict=n_predict,
                    n_probs=n_probs,
                    receive_buffer_bytes=receive_buffer_bytes,
                    seed=seed,
                    temperature=temperature,
                )
                with state_lock:
                    connections[slot_id] = connection
                    responses[slot_id] = response
                first_event = response.readline(MAX_RESPONSE_BYTES + 1)
                if len(first_event) > MAX_RESPONSE_BYTES:
                    raise ValueError("streaming event exceeded the bounded size")
                _stream_event_is_nonterminal(first_event)
                with state_lock:
                    first_events[slot_id] = first_event
                first_event_ready[slot_id].set()
                if not release_stream[slot_id].wait(20.0):
                    raise TimeoutError("stream release gate exceeded its bound")
            except BaseException as error:
                with state_lock:
                    worker_errors.append(error)
                first_event_ready[slot_id].set()
            finally:
                if response is not None:
                    response.close()
                if connection is not None:
                    connection.close()

        workers = [
            threading.Thread(
                target=stream_worker,
                args=(slot_id, prompt),
                daemon=True,
            )
            for slot_id, prompt in enumerate(slot_prompts)
        ]
        try:
            for slot in (first_disconnect_slot, survivor_slot):
                workers[slot].start()
            start_barrier.wait(timeout=2.0)

            started = time.monotonic()
            while time.monotonic() - started < active_observation_wait_ms / 1_000:
                values = self.slots(timeout=0.25)
                if all(
                    not _slot_view_from_values(values, slot)["idle"] for slot in (0, 1)
                ):
                    both_processing_observed = True
                    break
                if all(event.is_set() for event in first_event_ready):
                    break
                time.sleep(0.001)

            if not all(event.wait(5.0) for event in first_event_ready):
                raise TimeoutError("dual stream events exceeded their bounded wait")
            both_first_events_before_disconnect = True
            release_stream[first_disconnect_slot].set()

            started = time.monotonic()
            while time.monotonic() - started < 15.0:
                values = self.slots(timeout=0.25)
                first_idle = _slot_view_from_values(
                    values,
                    first_disconnect_slot,
                )["idle"]
                survivor_active = not _slot_view_from_values(
                    values,
                    survivor_slot,
                )["idle"]
                if first_idle:
                    cancelled_slot_idle = True
                    survivor_active_after_first_disconnect = survivor_active
                    break
                time.sleep(0.01)

            if not first_event_ready[survivor_slot].wait(5.0):
                raise TimeoutError("survivor stream event exceeded its bounded wait")
            release_stream[survivor_slot].set()

            for worker in workers:
                worker.join(timeout=10.0)
                if worker.is_alive():
                    raise RuntimeError("stream worker did not stop")
            if worker_errors:
                names = sorted({type(error).__name__ for error in worker_errors})
                raise RuntimeError(f"stream workers failed: {names}")

            started = time.monotonic()
            while time.monotonic() - started < 15.0:
                values = self.slots()
                if all(_slot_view_from_values(values, slot)["idle"] for slot in (0, 1)):
                    both_idle_after_second_disconnect = True
                    break
                time.sleep(0.01)
        finally:
            for gate in release_stream:
                gate.set()
            for worker in workers:
                worker.join(timeout=10.0)
            with state_lock:
                open_responses = list(responses)
                open_connections = list(connections)
            for response in open_responses:
                if response is not None:
                    response.close()
            for connection in open_connections:
                if connection is not None:
                    connection.close()
        return {
            "both_idle_after_second_disconnect": (both_idle_after_second_disconnect),
            "both_first_events_before_disconnect": (
                both_first_events_before_disconnect
            ),
            "both_processing_observed": both_processing_observed,
            "cancelled_slot_idle_after_first_disconnect": cancelled_slot_idle,
            "slot_0_first_event_nonterminal": _stream_event_is_nonterminal(
                first_events[0]
            ),
            "slot_0_first_event_observed": bool(first_events[0]),
            "slot_1_first_event_nonterminal": _stream_event_is_nonterminal(
                first_events[1]
            ),
            "slot_1_first_event_observed": bool(first_events[1]),
            "survivor_active_after_first_disconnect": (
                survivor_active_after_first_disconnect
            ),
        }

    def save(self, slot_id: int, filename: str) -> int:
        value = self.request_json(
            "POST",
            f"/slots/{slot_id}?action=save",
            {"filename": filename},
        )
        acknowledged = value.get("id_slot") if isinstance(value, dict) else None
        if (
            isinstance(acknowledged, bool)
            or not isinstance(acknowledged, int)
            or acknowledged != slot_id
        ):
            raise ValueError("slot save acknowledgement differed")
        return require_non_negative_int(value.get("n_saved"), "saved-token count")

    def restore(self, slot_id: int, filename: str) -> int:
        value = self.request_json(
            "POST",
            f"/slots/{slot_id}?action=restore",
            {"filename": filename},
        )
        acknowledged = value.get("id_slot") if isinstance(value, dict) else None
        if (
            isinstance(acknowledged, bool)
            or not isinstance(acknowledged, int)
            or acknowledged != slot_id
        ):
            raise ValueError("slot restore acknowledgement differed")
        return require_non_negative_int(
            value.get("n_restored"),
            "restored-token count",
        )
