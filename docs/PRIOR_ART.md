# Prior art and differentiation

CacheInvariant builds on existing runtime interfaces and benchmark work; it
does not claim invention of prefix caching, slot state, or cache benchmarking.

- [`llama.cpp` server](https://github.com/ggml-org/llama.cpp/tree/c0bc8591e8815c63cb01dd3f051a8b0df02501c9/tools/server)
  exposes request-selected slots, prompt caching, slot monitoring,
  cancellation on disconnect, and save/restore endpoints used by this adapter.
- [vLLM automatic prefix caching](https://docs.vllm.ai/en/stable/design/prefix_caching/)
  documents a different runtime's prefix-cache design and hash-based block
  reuse.
- [MLCommons KV-cache benchmark](https://github.com/mlcommons/storage/tree/main/kv_cache_benchmark)
  addresses cache performance and storage behavior at a broader benchmark
  layer.
- [SGLang server arguments](https://docs.sglang.io/docs/advanced_features/server_arguments)
  expose scheduling, preemption, and cache-eviction controls in another
  runtime.
- [Strata at OSDI 2026](https://www.usenix.org/conference/osdi26/presentation/xie-zhiqiang)
  studies cache loading together with serving scheduling at a different scale
  and performance layer.
- `llama-bench`, serving benchmarks, and load generators primarily emphasize
  latency, throughput, capacity, or workload replay.

The narrow contribution here is an auditable state-transition oracle:

1. a strict cache-on/cache-off matched pair;
2. disconnect-to-idle-to-same-slot-reuse hygiene;
3. two registered dual-stream launch/disconnect orders with per-slot reuse
   comparison;
4. save/restore into another slot;
5. restore after a process restart; and
6. normalized, privacy-bounded evidence with an offline fail-closed verifier.

That is a testing perspective, not an absolute novelty claim.
