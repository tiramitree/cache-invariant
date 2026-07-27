# Contributing

Changes should preserve the narrow evidence boundary:

1. add or update deterministic unit tests;
2. run `ruff check .`, `pytest`, `python -m build`, and
   `python tools/privacy_scan.py`;
3. keep runtime/model artifacts, raw logs, generated text, and local paths out
   of commits;
4. never add a runtime or model pin without recording source, license, exact
   bytes, SHA-256, and a bounded claim;
5. do not treat synthetic tests as real-runtime evidence.

Third-party code must retain its original license and attribution. Do not
submit a CLA or other legal agreement on another person's behalf.
