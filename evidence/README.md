# Reference evidence

`reference-v0.1.0-windows` is a normalized observation of the registered
`llama.cpp b10107` CPU runtime and tiny pinned fixture.

- source revision:
  `6104645dcb56b681d66f4739ec2399e431a72a30`
- manifest-file SHA-256:
  `1b81960f00267a94c447a29d256a3cc063cebf252935dbd75cd76f5d973a3b28`
- inventory: 3 files, 15,945 bytes
- platform: `windows-x86_64`
- registered invariants: 29/29 true
- converted GGUF: 1,185,504 bytes,
  SHA-256 `da5a97120b643453a8bf0482999ee087d1bd11e75c6cc5a3dc71d2ee3c89c92d`

Verify it offline:

```text
cache-invariant verify evidence/reference-v0.1.0-windows
```

The bundle contains exact pins and registration, normalized hashes and
counters, Boolean invariants, JUnit, and a manifest. It excludes generated
text, raw tokens, server logs, wall-clock performance, absolute paths,
hostnames, ports, environment variables, runtime binaries, source fixture
files, and the converted model.

The registered transport is an authenticated local-loopback `llama-server`.
The project has no hosted-model-service integration or paid-service step.

This is source-, version-, fixture-, schedule-, and OS-bound evidence. It is
not independent reproduction, a model-quality or throughput benchmark,
security certification, production validation, cross-runtime equivalence,
external review, or adoption. Public CI separately generates and verifies
fresh Windows and Ubuntu observations without uploading them.
