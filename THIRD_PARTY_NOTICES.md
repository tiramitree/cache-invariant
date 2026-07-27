# Third-party notices

CacheInvariant does not redistribute a model or a `llama.cpp` runtime. Its
fetch workflow downloads exact, hash-pinned upstream artifacts into an ignored
local directory.

## `llama.cpp`

- Project: `ggml-org/llama.cpp`
- Release: `b10107`
- Source commit: `c0bc8591e8815c63cb01dd3f051a8b0df02501c9`
- Source-project root license: MIT
- License copy: [`third_party/llama.cpp-LICENSE.txt`](third_party/llama.cpp-LICENSE.txt)

That MIT record describes the `llama.cpp` source project's root license and
the converter lineage below; it is not a blanket legal conclusion about every
file in an official binary asset. Such assets can contain separately licensed
runtime components. CacheInvariant hash-checks but does not redistribute those
assets, and downstream users remain responsible for applicable third-party
terms.

The separately licensed
[`src/cache_invariant/_vendor/llama2c_gguf.py`](src/cache_invariant/_vendor/llama2c_gguf.py)
is a Python/GGUF adaptation of tensor-layout and tokenizer-loading logic in:

- `examples/convert-llama2c-to-ggml/convert-llama2c-to-ggml.cpp`
- pinned blob: `702bc74bee2dd443dcd847ac49bb916a768342de`
- source URL:
  <https://github.com/ggml-org/llama.cpp/blob/c0bc8591e8815c63cb01dd3f051a8b0df02501c9/examples/convert-llama2c-to-ggml/convert-llama2c-to-ggml.cpp>

That file is MIT licensed; the repository-level Apache-2.0 license does not
replace its MIT terms.

## `karpathy/tinyllamas` fixture

- Model repository: `karpathy/tinyllamas`
- Revision: `0bd21da7698eaf29a0d7de3992de8a46ef624add`
- Pinned model-card license metadata: `mit`
- Pinned model card:
  <https://huggingface.co/karpathy/tinyllamas/blob/0bd21da7698eaf29a0d7de3992de8a46ef624add/README.md>

The fetched `stories260K.bin` checkpoint and `tok512.bin` tokenizer are used
only as a tiny real-inference fixture. They are not included in this
repository or redistributed in build/CI artifacts. The pinned tree has no
standalone license file; the license statement available for this fixture is
the pinned model-card metadata above. Generated text is neither recorded nor
treated as model-quality evidence.

## Conversion-only Python dependencies

The conversion lane directly pins:

- `gguf==0.19.0` — MIT, source:
  <https://pypi.org/project/gguf/0.19.0/>;
- `numpy==2.4.4` — package metadata expression
  `BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0` (NumPy core is
  BSD-3-Clause and the distribution includes separately licensed bundled
  components), source: <https://pypi.org/project/numpy/2.4.4/>; and
- `PyYAML==6.0.2` — MIT, source:
  <https://pypi.org/project/PyYAML/6.0.2/>.

These packages remain third-party software under their own licenses. They are
installed dependencies, not vendored files or build artifacts. Their direct
versions are exact, but cross-platform transitive resolution is not
hash-locked; `gguf` metadata currently pulls additional packages such as
`requests` and `tqdm`. The exact GGUF byte count and SHA-256 are a conversion
output gate, not a claim that the complete Python environment is
byte-reproducible.
