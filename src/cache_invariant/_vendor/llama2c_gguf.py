# SPDX-License-Identifier: MIT
# Copyright (c) 2023-2026 The ggml authors
#
# Source basis:
#   ggml-org/llama.cpp commit
#   c0bc8591e8815c63cb01dd3f051a8b0df02501c9
#   examples/convert-llama2c-to-ggml/convert-llama2c-to-ggml.cpp
#   Git blob 702bc74bee2dd443dcd847ac49bb916a768342de
#
# Modifications:
#   Ported the registered llama2.c tensor layout and tokenizer parsing to
#   Python/NumPy; writes GGUF through gguf-py; restricts conversion to the
#   hash-pinned stories260K fixture; adds exact tensor accounting and
#   deterministic metadata. The complete upstream MIT terms are preserved in
#   third_party/llama.cpp-LICENSE.txt.
"""Convert the pinned stories260K llama2.c fixture to deterministic GGUF."""

from __future__ import annotations

import hashlib
import re
import struct
from dataclasses import dataclass
from pathlib import Path

import gguf
import numpy as np

EXPECTED_CHECKPOINT_SHA256 = (
    "b0a507e7ad0f626624f17112325e66691f9076d622e1d3274d103d00299f2696"
)
EXPECTED_TOKENIZER_SHA256 = (
    "037cb335abb25d1fa9e8ecae30ed2a3a8ace9302862ebcdc05d51a6bbb10c312"
)


@dataclass(frozen=True)
class Config:
    dim: int
    hidden_dim: int
    n_layers: int
    n_heads: int
    n_kv_heads: int
    vocab_size_signed: int
    seq_len: int

    @property
    def vocab_size(self) -> int:
        return abs(self.vocab_size_signed)

    @property
    def shared_weights(self) -> bool:
        return self.vocab_size_signed > 0

    @property
    def n_multiqueries(self) -> int:
        if self.n_kv_heads <= 0 or self.n_kv_heads >= self.n_heads:
            return 1
        if self.n_heads % self.n_kv_heads:
            raise ValueError("n_heads must be divisible by n_kv_heads")
        return self.n_heads // self.n_kv_heads


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _require_fixture(path: Path, expected: str) -> None:
    actual = _sha256(path)
    if actual != expected:
        raise ValueError(f"unexpected SHA-256 for {path.name}: {actual}")


def _take(
    values: np.ndarray,
    cursor: int,
    count: int,
) -> tuple[np.ndarray, int]:
    end = cursor + count
    if end > values.size:
        raise ValueError("checkpoint ended before all declared tensors")
    return values[cursor:end], end


def load_checkpoint(path: Path) -> tuple[Config, dict[str, np.ndarray]]:
    with path.open("rb") as handle:
        header = handle.read(7 * 4)
        if len(header) != 7 * 4:
            raise ValueError("short llama2.c header")
        config = Config(*struct.unpack("<7i", header))
        values = np.fromfile(handle, dtype="<f4")

    c = config
    if (
        min(
            c.dim,
            c.hidden_dim,
            c.n_layers,
            c.n_heads,
            c.n_kv_heads,
            c.vocab_size,
            c.seq_len,
        )
        <= 0
    ):
        raise ValueError(f"invalid checkpoint configuration: {c}")

    cursor = 0
    raw: dict[str, np.ndarray] = {}

    def load(name: str, shape: tuple[int, ...]) -> None:
        nonlocal cursor
        flat, cursor = _take(values, cursor, int(np.prod(shape)))
        raw[name] = flat.reshape(shape)

    load("token_embd.weight", (c.vocab_size, c.dim))
    load("rms_att", (c.n_layers, c.dim))
    load("wq", (c.n_layers, c.dim, c.dim))
    kv_rows = c.dim // c.n_multiqueries
    load("wk", (c.n_layers, kv_rows, c.dim))
    load("wv", (c.n_layers, kv_rows, c.dim))
    load("wo", (c.n_layers, c.dim, c.dim))
    load("rms_ffn", (c.n_layers, c.dim))
    load("w1", (c.n_layers, c.hidden_dim, c.dim))
    load("w2", (c.n_layers, c.dim, c.hidden_dim))
    load("w3", (c.n_layers, c.hidden_dim, c.dim))
    load("output_norm.weight", (c.dim,))

    # llama2.c stores precomputed RoPE real+imag values after the model tensors.
    _, cursor = _take(values, cursor, c.seq_len * (c.dim // c.n_heads))

    if c.shared_weights:
        raw["output.weight"] = raw["token_embd.weight"]
    else:
        load("output.weight", (c.vocab_size, c.dim))

    if cursor != values.size:
        raise ValueError(
            f"checkpoint tensor accounting mismatch: used {cursor}, has {values.size}"
        )
    return config, raw


def load_tokenizer(
    path: Path,
    vocab_size: int,
) -> tuple[list[bytes], list[float], list[int]]:
    tokens: list[bytes] = []
    scores: list[float] = []
    types: list[int] = []
    byte_pattern = re.compile(rb"^<0x[0-9A-Fa-f]{2}>$")

    with path.open("rb") as handle:
        max_len_raw = handle.read(4)
        if len(max_len_raw) != 4:
            raise ValueError("short tokenizer header")
        struct.unpack("<I", max_len_raw)

        for token_id in range(vocab_size):
            score_raw = handle.read(4)
            len_raw = handle.read(4)
            if len(score_raw) != 4 or len(len_raw) != 4:
                raise ValueError("tokenizer ended before declared vocabulary")
            score = struct.unpack("<f", score_raw)[0]
            length = struct.unpack("<I", len_raw)[0]
            text = handle.read(length)
            if len(text) != length:
                raise ValueError("short tokenizer token")

            token_type = int(gguf.TokenType.NORMAL)
            if token_id == 0:
                text = b"<unk>"
                token_type = int(gguf.TokenType.UNKNOWN)
            elif token_id == 1:
                text = b"<s>"
                token_type = int(gguf.TokenType.CONTROL)
            elif token_id == 2:
                text = b"</s>"
                token_type = int(gguf.TokenType.CONTROL)
            elif not text:
                token_type = int(gguf.TokenType.CONTROL)
            elif byte_pattern.fullmatch(text):
                token_type = int(gguf.TokenType.BYTE)

            text = text.replace(b" ", "\u2581".encode())
            tokens.append(text)
            scores.append(score)
            types.append(token_type)

        if handle.read(1):
            raise ValueError("tokenizer contains trailing bytes")

    return tokens, scores, types


def convert(checkpoint: Path, tokenizer: Path, output: Path) -> None:
    _require_fixture(checkpoint, EXPECTED_CHECKPOINT_SHA256)
    _require_fixture(tokenizer, EXPECTED_TOKENIZER_SHA256)
    config, raw = load_checkpoint(checkpoint)
    tokens, scores, types = load_tokenizer(tokenizer, config.vocab_size)

    writer = gguf.GGUFWriter(output, arch="llama")
    writer.add_name("stories260K-cache-invariant-fixture")
    writer.add_description(
        "Karpathy stories260K fixture (pinned model-card metadata: mit), "
        "converted locally for cache semantics tests"
    )
    writer.add_context_length(128)
    writer.add_embedding_length(config.dim)
    writer.add_feed_forward_length(config.hidden_dim)
    writer.add_head_count(config.n_heads)
    writer.add_head_count_kv(config.n_kv_heads)
    writer.add_block_count(config.n_layers)
    writer.add_rope_dimension_count(min(64, config.dim // config.n_heads))
    writer.add_layer_norm_rms_eps(1e-5)

    writer.add_tokenizer_model("llama")
    writer.add_tokenizer_pre("default")
    writer.add_token_list(tokens)
    writer.add_token_scores(scores)
    writer.add_token_types(types)
    writer.add_unk_token_id(0)
    writer.add_bos_token_id(1)
    writer.add_eos_token_id(2)

    writer.add_tensor("token_embd.weight", raw["token_embd.weight"])
    writer.add_tensor("output_norm.weight", raw["output_norm.weight"])
    writer.add_tensor("output.weight", raw["output.weight"])
    for layer in range(config.n_layers):
        writer.add_tensor(f"blk.{layer}.attn_q.weight", raw["wq"][layer])
        writer.add_tensor(f"blk.{layer}.attn_k.weight", raw["wk"][layer])
        writer.add_tensor(f"blk.{layer}.attn_v.weight", raw["wv"][layer])
        writer.add_tensor(
            f"blk.{layer}.attn_output.weight",
            raw["wo"][layer],
        )
        writer.add_tensor(
            f"blk.{layer}.attn_norm.weight",
            raw["rms_att"][layer],
        )
        writer.add_tensor(f"blk.{layer}.ffn_gate.weight", raw["w1"][layer])
        writer.add_tensor(f"blk.{layer}.ffn_down.weight", raw["w2"][layer])
        writer.add_tensor(f"blk.{layer}.ffn_up.weight", raw["w3"][layer])
        writer.add_tensor(
            f"blk.{layer}.ffn_norm.weight",
            raw["rms_ffn"][layer],
        )

    writer.write_header_to_file()
    writer.write_kv_data_to_file()
    writer.write_tensors_to_file()
    writer.close()
