"""Atomic evidence, JUnit, and manifest bundle writer."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from .pins import MANIFEST_SCHEMA
from .util import (
    pretty_json,
    reject_reparse_chain,
    require_plain_directory,
    sha256_file,
    write_new,
)
from .verify import junit_bytes, validate_evidence, verify_bundle


def write_bundle(output: Path, evidence: dict[str, Any]) -> dict[str, Any]:
    validate_evidence(evidence)
    reject_reparse_chain(output, "evidence output")
    if output.exists():
        raise FileExistsError("refusing to overwrite evidence output")
    output.parent.mkdir(parents=True, exist_ok=True)
    require_plain_directory(output.parent, "evidence output parent")
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{output.name}.staging-",
            dir=output.parent,
        )
    )
    require_plain_directory(staging, "evidence staging directory")
    try:
        evidence_path = staging / "evidence.json"
        junit_path = staging / "junit.xml"
        write_new(evidence_path, pretty_json(evidence))
        write_new(junit_path, junit_bytes(evidence["invariants"]))
        manifest = {
            "files": [
                {
                    "bytes": evidence_path.stat().st_size,
                    "path": "evidence.json",
                    "sha256": sha256_file(evidence_path),
                },
                {
                    "bytes": junit_path.stat().st_size,
                    "path": "junit.xml",
                    "sha256": sha256_file(junit_path),
                },
            ],
            "schema": MANIFEST_SCHEMA,
        }
        write_new(staging / "manifest.json", pretty_json(manifest))
        summary = verify_bundle(staging)
        os.replace(staging, output)
        return summary
    except BaseException:
        if staging.exists():
            shutil.rmtree(staging)
        raise
