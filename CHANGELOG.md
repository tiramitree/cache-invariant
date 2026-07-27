# Changelog

## 0.2.0

- Add a source-bound dual-stream interleaving and cancellation-isolation lane
  for the exact `llama.cpp b10107` CPU adapter.
- Run both registered launch/disconnect orders behind a start barrier, require
  both nonterminal stream events before either disconnect, verify cancelled and
  final idle states, and compare both reused-slot results with isolated
  baselines.
- Retain sampled processing and post-disconnect survivor state as non-gating
  observations instead of converting timing-sensitive samples into claims.
- Raise the registered total context from 256 to 4,096 tokens for the new
  bounded stream protocol.
- Add strict schema-v2 verification while preserving offline verification of
  the bundled schema-v1 evidence.

## 0.1.0

- Initial exact-repeat cache, cancellation/reuse, save/restore, and
  process-restart evidence lanes.
