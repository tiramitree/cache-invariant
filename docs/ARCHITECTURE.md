# Architecture and evidence contract

## State-machine focus

The adapter drives one real `llama.cpp` server through explicit state
transitions:

```text
empty slot
  -> cache-on cold request
  -> cache-on identical repeat
  -> erase
  -> cache-off cold request
  -> cache-off identical repeat

clean slot
  -> long streaming request
  -> client disconnect
  -> idle observation
  -> same-slot reuse
  -> compare with other-slot clean baseline

two empty slots
  -> launch two long streams behind one start barrier
  -> require a nonterminal event from both before either disconnects
  -> disconnect the first registered slot
  -> observe that cancelled slot return to idle
  -> disconnect the second stream
  -> observe both slots idle
  -> reuse both slots and compare each result with its isolated baseline
  -> repeat with the opposite launch and disconnect order

empty slot
  -> cached source completion
  -> save slot state
  -> restore into other slot
  -> identical completion with strictly less prompt work
  -> stop server
  -> start new server process
  -> restore saved state
  -> identical completion with strictly less prompt work
```

The oracle compares matched requests at fixed prompt, seed, temperature, and
prediction count. Cache effectiveness uses `timings.prompt_n` and the idle slot
view's `n_prompt_tokens_processed`; the response field `tokens_cached` is
recorded but is not a pass/fail signal in `b10107`.

## Components

- `pins.py` is the only allowlist for runtime, model, and conversion artifacts.
- `registration.py` owns the fixed stimuli, request parameters, slots, state
  filename identity, and exact process order.
- `fetch.py` downloads, byte-counts, hashes, and safely extracts exact assets.
- `_vendor/llama2c_gguf.py` converts only the registered tiny fixture.
- `adapter.py` exposes the narrow version-pinned server protocol.
- `runner.py` owns process lifecycle and normalized observations.
- `evidence.py` writes canonical JSON, a deterministic JUnit projection, and a
  hash manifest.
- `verify.py` performs an offline, strict recomputation against the frozen
  oracle, independent of runtime execution and process state.

## Trust boundaries

The runtime lock is not accepted merely because it exists. The runner checks
its exact schema and allowlisted values, re-hashes local files, checks the
converted GGUF hash, and checks the server's `--version` output before launch.

The server listens only on `127.0.0.1`, has no Web UI, runs in offline mode,
uses no GPU layers, and writes slot state only beneath a fresh run directory.
The port and local paths never enter evidence. The registered two-slot server
uses a bounded total context of 4,096 tokens. The cancellation and interleaving
requests ask for the fixed 512-vocabulary probability field while the client
uses a registered small stream receive buffer. The single-stream cancellation
lane requires a concurrent `/slots` observation before the first event is
read. The dual-stream lane requires both clients to receive a syntactically
nonterminal event before either disconnects, then runs both disconnect orders.
A sampled `both_processing_observed` value is retained but is deliberately not
a pass condition because the bounded sampler did not observe it in every local
repetition. Probabilities, generated content, and elapsed-time data are not
retained.

The evidence verifier performs no network access and starts no process. It
accepts exactly three regular files and rejects symlinks, unknown schema keys,
unregistered pins or request registration, invalid source revisions, failed
invariants, malformed JUnit, hash mismatches, and extra files.

## Normalization

Generated text is reduced to a SHA-256 and UTF-8 byte count. Token lists are
reduced to the SHA-256 of canonical JSON. Stream-only probability fields used
to create cancellation backpressure are discarded. The timing-sensitive cancellation
observation is reduced to two booleans: active processing was observed, and
the same slot later returned to idle. Prompt-work token counts that define the
cache and restore oracle remain as bounded integers.

Raw prompts are absent from evidence. Their UTF-8 byte counts and SHA-256
identities, together with fixed seed, temperature, prediction count, cache and
stream flags, selected slots, state-filename identity, and process order form
the exact public registration. `source_revision` is either `UNCOMMITTED` for a
local candidate or a lowercase 40-hex revision supplied by CI.

No inference speed measurement is retained.
