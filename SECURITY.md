# Security

CacheInvariant launches a local server with no authentication, so the runner
binds only to `127.0.0.1`, disables the Web UI, and uses offline mode. Do not
change the bind address on a shared or untrusted machine.

The fetcher rejects hash drift, length drift, archive traversal, symlinks, and
unexpected archive types. The evidence verifier is offline.

Do not publish raw server logs, generated text, runtime/model files, local
paths, credentials, host details, or unreviewed evidence bundles.
