# Reference evidence

## v0.2.0 Windows

`reference-v0.2.0-windows` is a normalized observation of the registered
`llama.cpp b10107` CPU runtime, tiny pinned fixture, and schema-v2
dual-stream protocol.

- source revision:
  `920dea766e267fd29b4171a144ba195cfa0ef1d4`
- manifest-file SHA-256:
  `e4246f2e37ad6d1d9fd23316fdf667be0097760f1f66f6c3b8f9e1f6bf32abf7`
- inventory: 3 files, 31,458 bytes
- platform: `windows-x86_64`
- registered invariants: 57/57 true
- converted GGUF: 1,185,504 bytes,
  SHA-256 `da5a97120b643453a8bf0482999ee087d1bd11e75c6cc5a3dc71d2ee3c89c92d`

Verify it offline:

```text
cache-invariant verify evidence/reference-v0.2.0-windows
```

The schema-v2 lane launches two registered streams behind one start barrier.
In both launch/disconnect orders, both clients received a nonterminal event
before either disconnected, the first cancelled slot returned to idle, both
slots later returned idle, and each reused result matched its isolated
baseline. The record also retains sampled `both_processing_observed` and
`survivor_active_after_first_disconnect` values, but neither is a pass
condition or a concurrency/liveness claim.

## v0.1.0 Windows

`reference-v0.1.0-windows` preserves the initial normalized observation.

- source revision:
  `6104645dcb56b681d66f4739ec2399e431a72a30`
- manifest-file SHA-256:
  `1b81960f00267a94c447a29d256a3cc063cebf252935dbd75cd76f5d973a3b28`
- inventory: 3 files, 15,945 bytes
- platform: `windows-x86_64`
- registered invariants: 29/29 true

The current verifier remains backward-compatible:

```text
cache-invariant verify evidence/reference-v0.1.0-windows
```

## Shared boundary

Each bundle contains exact pins and registration, normalized hashes and
counters, Boolean invariants, JUnit, and a manifest. It excludes generated
text, raw tokens, server logs, wall-clock performance, absolute paths,
hostnames, ports, environment variables, runtime binaries, source fixture
files, and the converted model.

The registered transport is an authenticated local-loopback `llama-server`.
The project has no hosted-model-service integration or paid-service step.

These are source-, version-, fixture-, schedule-, and OS-bound observations.
They are not independent reproduction, model-quality or throughput benchmarks,
security certification, production validation, cross-runtime equivalence,
external review, or adoption. Public CI separately generates and verifies
fresh Windows and Ubuntu observations without uploading them.
