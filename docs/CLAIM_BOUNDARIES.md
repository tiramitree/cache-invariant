# Claim boundaries

## A verified bundle can support

For the exact registered `llama.cpp b10107` CPU release assets and exact tiny
fixture, request registration, and source revision recorded by the bundle, on
the operating system named by the registered asset:

- matched cache-on/off requests satisfied the recorded prompt-work oracle;
- a selected slot was observed active, returned idle after a client
  disconnect, and produced the same normalized result as a clean slot when
  reused;
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
- absolute latency, throughput, cost, memory efficiency, or competitive rank;
- production readiness, security certification, or complete state isolation;
- GPU, accelerator, distributed, hosted, or multi-tenant behavior;
- behavior of another `llama.cpp` version, model, request schedule, or runtime;
- vLLM, SGLang, MLPerf, or cross-runtime equivalence;
- external reproduction, adoption, review, endorsement, or users.

An output hash match is evidence about the fixed test result only. It does not
prove that no unobserved internal state exists.
