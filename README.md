# Context-Aware PR Review

Local, deterministic, advisory review of textual unified diffs. Version
**0.1.2a1** is an experimental partial candidate from **JY-S002-P001**.
It does not approve or merge pull requests. Human review is always required.

## Install and run

Python 3.10 or newer; no runtime dependencies.

~~~sh
python -m pip install .
prreview change.diff pr-meta.json
# Or run directly from this checkout:
python -m prreview.engine change.diff
python -m unittest discover -s tests -t .
~~~

Optional metadata is a JSON object with title, id, base, and head.
Fields accept strings or null; id also accepts nonnegative integers up to
10^12. Strings are limited to 4,096 characters; unknown keys are ignored.

~~~python
from prreview.engine import review
report = review(diff_text, {"title": "Update database query", "id": 7})
~~~

Reports contain file/hunk summaries, findings ranked by severity, exact new-file
line numbers, confidence, analyzer versions, hunk digests, and coverage limits.
The three analyzer categories are security, maintainability, and performance.
Source-code excerpts are omitted from every finding to avoid copying credentials
or other source text into logs. Metadata and file paths remain visible.

Status is REVIEWED or ABSTAINED; verdict is always ADVISORY_ONLY.
CLI exit codes are 0 for a completed review, 1 for abstention/input failure,
and 2 for incorrect usage. Exit 0 says nothing about whether changes are safe.
This changes the prior CLI behavior that returned 0 on abstention.

## Supported input and limits

Supports ordinary unified text diffs, standard Git index/mode headers,
additions and deletions using /dev/null, CRLF transport, and no-newline markers.
Declared counts, ordered/non-overlapping ranges, unchanged gaps, and matching
Git/file headers are checked. Duplicate file sections, renames, quoted paths,
binary patches, mode-only changes, unsafe paths, and unknown sections cause
the whole review to abstain. File modes themselves are not analyzed.

Limits: 2 MiB UTF-8 input, 20,000 physical lines, 4,096 characters per line,
500 files, 2,000 hunks, and 5,000 added lines. CLI metadata is capped at 64 KiB;
duplicate JSON keys and nonfinite numbers are rejected.

## Scope and evidence

42 tests cover parsing, advisory boundaries, findings, malformed data, disclosure,
CLI behavior, and security regressions. See [audit](docs/AUDIT.md),
[check evidence](docs/CHECK_RUNS.json), and [security boundaries](SECURITY.md).
CI tests Python 3.10, 3.12, and 3.14 on Linux, and 3.12 on Windows.

This is a pattern-based core, with false positives and false negatives.
It does not implement model-based intent, repository graphs, review history,
CI signal analysis, or the original package's service architecture. No completion
is claimed for the source carrier's 196 parent items or 36 phase gates.
Reports and digests are provenance aids, not signatures or a proof of security.

## License

Copyright 2026 **RUSSELL PHILIP SMITHSON**. Original code and modifications:
[Apache License 2.0](LICENSE), with [NOTICE](NOTICE).
The bundled BC-ALAgents design reference retains its MIT license; see
[third-party notices](THIRD-PARTY-NOTICES.md).
