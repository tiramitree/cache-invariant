# Privacy and publication gate

`python tools/privacy_scan.py` is a source-tree gate. It scans path names and
UTF-8 content while excluding explicitly generated, ignored directories such
as `.git`, `.venv`, `.cache`, `dist`, and local candidate evidence. It rejects
common absolute home paths, UNC paths, email addresses, private-key markers,
token shapes, reparse points, binary runtime/model files, and sensitive file
names.

Failure messages expose only a finding category, line number, and the literal
`<redacted-path>` marker. They do not echo a matched filename, path, or content
value into CI logs.

That public scanner cannot know private identity strings without embedding
them, which would itself be a disclosure. Before any commit, push, tag,
release, or artifact publication, a separate private denylist must scan:

- the complete candidate tree and Git object set;
- build archives and every archive member;
- candidate evidence and manifests;
- CI workflow text and logs intended for publication; and
- release metadata and assets.

A clean public source scan is not a claim that unrelated history, forks, or
external systems are globally privacy-clean.

The schema-v3 prefix lane keeps its small synthetic direct-token arrays in
source registration only. Evidence contains their token counts and canonical
JSON SHA-256 identities, not the arrays. The lane explicitly requests one
generated token, but generated content and token values are discarded before
normalization and cannot enter evidence.
