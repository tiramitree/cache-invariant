# CacheInvariant

CacheInvariant is a version-pinned correctness and isolation lab for inference
cache state. The first adapter targets the real CPU server shipped by
`llama.cpp` release `b10107` and a tiny `llama2.c` fixture whose pinned model
card declares MIT.

It asks bounded questions:

- Does an identical cache-on request reduce observed prompt work while a
  matched cache-off pair does not?
- For fixed direct-token prompts, do exact reuse, shared-prefix reuse, and
  first-token divergence produce the registered cache/work matrix relative to
  matched cache-off requests?
- After a streaming client disconnects, does the selected slot return to idle,
  accept a new request, and match a clean-slot result?
- When two registered streams are launched behind one start barrier, do both
  produce a nonterminal event before either client disconnects, does the first
  cancelled slot return to idle, and can both slots then be reused without
  changing their fixed results?
- Can slot state be saved, restored into another slot, and reused?
- Does saved state remain restorable after the server process is stopped and
  started again?

It is not a throughput dashboard, a model-quality benchmark, a production
certification, or evidence about GPU, distributed, multi-runtime, or hosted
systems.

## Pinned local lane

Python 3.11 or newer is required. Runtime/model files are fetched into an
ignored directory and are never packaged.

```console
python -m pip install -e ".[convert,dev]"
cache-invariant fetch --destination .cache/pinned
cache-invariant convert --lock .cache/pinned/runtime-lock.json
cache-invariant run \
  --lock .cache/pinned/runtime-lock.json \
  --output candidate-evidence \
  --source-revision UNCOMMITTED
cache-invariant verify candidate-evidence
```

Every runtime/model artifact downloaded by `cache-invariant fetch` is checked
against an exact byte count and SHA-256 before use. Conversion refuses
unexpected input hashes, unexpected dependency versions, an existing output,
and any GGUF result other than the registered fixture hash. Archive extraction
rejects traversal, hardlinks, and unknown links. The exact Ubuntu asset's
same-directory relative library aliases are validated and materialized as
regular files in the fresh run tree.

The direct conversion dependencies are exact version-pinned. Pip-resolved
transitive dependencies are not cross-platform hash-locked, so the exact GGUF
hash is an output-integrity gate rather than a claim that the complete Python
environment is byte-reproducible.

`run` binds the server to a dynamically selected loopback port, forces CPU and
offline mode, enables exactly two slots with a total 4,096-token context, and
suppresses raw server logs. The
evidence contains only normalized hashes, bounded counters, booleans, and
registered version identifiers. It excludes:

- generated text and raw token lists;
- absolute paths, hostnames, ports, and environment variables;
- raw server logs;
- wall-clock latency and throughput.

The schema-v3 direct-token lane explicitly sends `n_predict=1` and requires the
pinned runtime to report `predicted_tokens=1`. Generated content and generated
token values are discarded and never compared. This lane does not claim
output-free execution.

The output directory contains exactly `evidence.json`, `junit.xml`, and
`manifest.json`. `verify` is offline and fail-closed: it validates the exact
schema, registered runtime/model pins and request registration, recomputes every
oracle, validates the manifest and JUnit mapping, and rejects extra files.
Local working-tree evidence must use `UNCOMMITTED`; CI supplies the exact
lowercase 40-hex revision being exercised.

## Current evidence status

The bundled Windows [reference evidence](evidence/README.md) preserves the
29-invariant v0.1 observation, the 57-invariant v0.2 observation, and the
77-invariant v0.3 observation, each bound to the exact source revision
exercised. They are owner-operated observations, not independent reproduction,
external adoption, production use, or cross-platform reference results. The workflow in
`.github/workflows/ci.yml` separately exercises Windows and Ubuntu on free
GitHub Actions without uploading generated evidence.

## Design and boundaries

- [Architecture and evidence contract](docs/ARCHITECTURE.md)
- [Reference evidence](evidence/README.md)
- [Claim boundaries](docs/CLAIM_BOUNDARIES.md)
- [Prior art and differentiation](docs/PRIOR_ART.md)
- [Privacy and publication gate](docs/PRIVACY.md)
- [Third-party notices](THIRD_PARTY_NOTICES.md)
- [Contributing](CONTRIBUTING.md)
- [Security](SECURITY.md)

Original CacheInvariant code is Apache-2.0. The converter file is separately
MIT licensed and visibly attributed; see `NOTICE` and
`THIRD_PARTY_NOTICES.md`.
