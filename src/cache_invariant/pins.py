"""Registered artifacts and public evidence boundary."""

from __future__ import annotations

from dataclasses import dataclass

PACKAGE_VERSION = "0.3.0"
RUNTIME_RELEASE = "b10107"
RUNTIME_SOURCE_COMMIT = "c0bc8591e8815c63cb01dd3f051a8b0df02501c9"
RUNTIME_VERSION_LINE = "version: 10107 (c0bc8591e)"
FIXTURE_SOURCE_REVISION = "0bd21da7698eaf29a0d7de3992de8a46ef624add"
RUNTIME_LOCK_SCHEMA = "cache-invariant-runtime-lock-v1"
EVIDENCE_SCHEMA = "cache-invariant-evidence-v3"
EVIDENCE_SCHEMA_V2 = "cache-invariant-evidence-v2"
EVIDENCE_SCHEMA_V1 = "cache-invariant-evidence-v1"
MANIFEST_SCHEMA = "cache-invariant-manifest-v1"
GGUF_SHA256 = "da5a97120b643453a8bf0482999ee087d1bd11e75c6cc5a3dc71d2ee3c89c92d"
GGUF_BYTES = 1_185_504
RUNTIME_CONTEXT_TOTAL = 4_096
RUNTIME_CONTEXT_TOTAL_V1 = 256
RUNTIME_SLOT_COUNT = 2


@dataclass(frozen=True)
class Artifact:
    name: str
    url: str
    bytes: int
    sha256: str


RUNTIME_ASSETS = {
    "windows-x86_64": Artifact(
        name="llama-b10107-bin-win-cpu-x64.zip",
        url=(
            "https://github.com/ggml-org/llama.cpp/releases/download/"
            "b10107/llama-b10107-bin-win-cpu-x64.zip"
        ),
        bytes=18_213_827,
        sha256="52133a0a5a8f6035b1bdd2f89c3425ea8b742413d9bdb9a2dee30e3a1681b18c",
    ),
    "ubuntu-x86_64": Artifact(
        name="llama-b10107-bin-ubuntu-x64.tar.gz",
        url=(
            "https://github.com/ggml-org/llama.cpp/releases/download/"
            "b10107/llama-b10107-bin-ubuntu-x64.tar.gz"
        ),
        bytes=16_275_561,
        sha256="afe1ae0b706c4a0830b218a9249037b7a6cc723f81deb78825662128b25453e6",
    ),
}

RUNTIME_SERVER_PINS = {
    "windows-x86_64": {
        "archive_path": "llama-server.exe",
        "bytes": 9_216,
        "sha256": "af3e56d6bdb84a9b6bd50f6ad748809370bc29be42d58088041408b2933d80f7",
    },
    "ubuntu-x86_64": {
        "archive_path": "llama-b10107/llama-server",
        "bytes": 17_896,
        "sha256": "88593c2c6942b3fb33683a3ade804b40c55cd0b389f18f05bbb0a556b15d0f01",
    },
}

CHECKPOINT = Artifact(
    name="stories260K.bin",
    url=(
        "https://huggingface.co/karpathy/tinyllamas/resolve/"
        f"{FIXTURE_SOURCE_REVISION}/stories260K/stories260K.bin"
    ),
    bytes=1_056_540,
    sha256="b0a507e7ad0f626624f17112325e66691f9076d622e1d3274d103d00299f2696",
)
TOKENIZER = Artifact(
    name="tok512.bin",
    url=(
        "https://huggingface.co/karpathy/tinyllamas/resolve/"
        f"{FIXTURE_SOURCE_REVISION}/stories260K/tok512.bin"
    ),
    bytes=6_227,
    sha256="037cb335abb25d1fa9e8ecae30ed2a3a8ace9302862ebcdc05d51a6bbb10c312",
)

CONVERSION_DEPENDENCIES = {
    "gguf": "0.19.0",
    "numpy": "2.4.4",
    "PyYAML": "6.0.2",
}
