"""Command-line interface."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import NoReturn

from .convert import convert_from_lock
from .evidence import write_bundle
from .fetch import fetch
from .runner import run_scenarios
from .verify import verify_bundle


def _path(value: str) -> Path:
    return Path(value)


def _fail(parser: argparse.ArgumentParser, error: Exception) -> NoReturn:
    parser.exit(
        2,
        f"cache-invariant failed: {type(error).__name__}\n",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cache-invariant",
        description=(
            "Version-pinned inference cache correctness and slot-isolation lab"
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    fetch_parser = subparsers.add_parser(
        "fetch",
        help="download and hash-check the registered runtime and fixture",
    )
    fetch_parser.add_argument("--destination", type=_path, required=True)

    convert_parser = subparsers.add_parser(
        "convert",
        help="convert the registered tiny fixture to the exact GGUF",
    )
    convert_parser.add_argument("--lock", type=_path, required=True)

    run_parser = subparsers.add_parser(
        "run",
        help="run registered scenarios and write a verified candidate bundle",
    )
    run_parser.add_argument("--lock", type=_path, required=True)
    run_parser.add_argument("--output", type=_path, required=True)
    run_parser.add_argument(
        "--source-revision",
        required=True,
        help="UNCOMMITTED or the lowercase 40-hex revision being exercised",
    )

    verify_parser = subparsers.add_parser(
        "verify",
        help="verify an evidence bundle offline and fail closed",
    )
    verify_parser.add_argument("bundle", type=_path)
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "fetch":
            lock = fetch(arguments.destination)
            result = {"lock": lock.name, "status": "verified"}
        elif arguments.command == "convert":
            model = convert_from_lock(arguments.lock)
            result = {"model": model.name, "status": "verified"}
        elif arguments.command == "run":
            evidence = run_scenarios(
                arguments.lock,
                source_revision=arguments.source_revision,
            )
            result = write_bundle(arguments.output, evidence)
            result["status"] = "verified"
        elif arguments.command == "verify":
            result = verify_bundle(arguments.bundle)
            result["status"] = "verified"
        else:
            raise AssertionError("unreachable command")
    except Exception as error:
        _fail(parser, error)
    print(json.dumps(result, separators=(",", ":"), sort_keys=True))
