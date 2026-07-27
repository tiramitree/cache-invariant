# Claim boundaries

## A verified bundle can support

For the exact registered `llama.cpp b10107` CPU release assets and exact tiny
fixture, request registration, and source revision recorded by the bundle, on
the operating system named by the registered asset:

- matched cache-on/off requests satisfied the recorded prompt-work oracle;
- in a schema-v3 bundle, the three registered direct-token rows satisfied the
  exact/full-prefix-last-token, shared-prefix, and first-token-divergence
  cache/work rules against matched cache-off requests;
- a selected slot was observed active, returned idle after a client
  disconnect, and produced the same normalized result as a clean slot when
  reused;
- in each of two registered launch/disconnect orders, two streams each
  produced a nonterminal event before either client disconnected, the first
  cancelled slot returned to idle, both slots later returned idle, and both
  reused results matched their isolated baselines;
- saved slot state restored into another slot with strictly less prompt work;
- after a full server process restart, the same saved state restored with
  strictly less prompt work than the source completion; and
- the supplied evidence directory passes the offline schema, oracle, manifest,
  JUnit, and privacy-shape checks.

These are controlled observations for one version and one tiny fixture.
The committed reference bundle is one Windows observation bound to its exact
source revision. CI generates separate Windows and Ubuntu observations
ephemerally without publishing their bundles.

## It does not support

- model quality, semantic correctness, safety, or useful generated text;
- output-free execution: the direct-token lane explicitly requests and records
  one predicted token, then discards generated values rather than evaluating
  them;
- absolute latency, throughput, cost, memory efficiency, or competitive rank;
- production readiness, security certification, or complete state isolation;
- scheduling fairness, simultaneous token generation, head-of-line-blocking
  absence, or a guarantee that the surviving slot remains active after the
  first disconnect;
- GPU, accelerator, distributed, hosted, or multi-tenant behavior;
- behavior of another `llama.cpp` version, model, request schedule, or runtime;
- vLLM, SGLang, MLPerf, or cross-runtime equivalence;
- external reproduction, adoption, review, endorsement, or users.

An output hash match is evidence about the fixed test result only. It does not
prove that no unobserved internal state exists.

The dual-stream record retains `both_processing_observed` and
`survivor_active_after_first_disconnect` as non-gating observations. They are
not used to claim concurrent processing or survivor liveness.

The committed v0.1 and v0.2 Windows references predate the schema-v3
direct-token lane. A v3 source candidate without a verified v3 bundle supports
the protocol and verifier design, not a published short-row runtime
observation.
