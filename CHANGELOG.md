# 0.1.2a1 — 2026-09-23

- Bound and validate all text-diff sections and exact annotation locations.
- Omit source excerpts; fail cleanly on malformed Unicode/metadata/CLI inputs.
- Correct parameterized-SQL false positives; analyzer version 0.1.1.
- Package the CLI, document partial scope, add Apache 2.0 LICENSE/NOTICE,
  retain MIT donor attribution, and add 20 regression tests plus CI.

# Changelog — Context-Aware PR Review Assistant

## 0.1.1-partial — 2026-09-14

Maintenance release: repairs only (patch bump). Baseline fingerprint:
JY-S002-P001/build-0001, product.zip sha256
520e8228dc280479758c9af6eeea782f8364e0bfd702fe5d5d2f227ada2244ca
(version 0.1.0-partial). All findings below were reproduced on the
baseline with live probes before fixing.

### Fixed

- **A004-F1 (engine, High)** — `review()` documents "never raises on
  bad input" but a non-mapping `pr_meta` (list/str/int/set) escaped as
  a bare `AttributeError`. Observed: `AttributeError: 'list' object
  has no attribute 'get'`. Expected/now: structured ABSTAINED report
  ("pr metadata is not a mapping"), verdict still ADVISORY_ONLY.
- **A004-F2 (differ, High)** — lines beyond a hunk's declared counts
  were silently consumed with fabricated new-file line numbers, so
  findings could be attached to lines that do not exist in the PR.
  Observed: surplus `+eval(x)` accepted at invented line 2, REVIEWED
  with a SEC-002 finding. Now: DiffError -> engine ABSTAINS (GRD-05).
- **A004-F3 (differ, Medium)** — a truncated hunk (fewer lines than
  declared) was silently accepted and reported REVIEWED, presenting an
  incomplete parse as full coverage. Now: DiffError -> ABSTAINED.
- **A004-F4 (differ, Medium)** — unrecognized junk lines inside a hunk
  were silently dropped (data loss without abstention). Now: DiffError.
- **A004-F5 (differ, Medium)** — a deleted line whose rendered form
  starts with `--- ` (e.g. deleting SQL comment `-- comment`) was
  misread mid-hunk as a new file section; the deletion silently
  vanished from the parsed hunk. Now parsed correctly as a deletion
  while the hunk's declared counts remain unconsumed.

### Changed

- Parser is now strict about unified-diff structure: declared hunk
  counts are enforced both ways, and `+`/`-` content outside an open
  hunk is rejected. Diffs with incorrect hunk headers that the lenient
  0.1.0 parser accepted are now rejected (engine returns ABSTAINED
  instead of a possibly-misattributed review). The test fixture's hunk
  headers were corrected to the true counts accordingly.
- Added native `prreview.__version__` = 0.1.1-partial;
  `ENGINE_VERSION` bumped. `ANALYZER_VERSION` unchanged (0.1.0 — no
  analyzer rule changes).

### Compatibility & rollback

- Public API unchanged (`parse_unified_diff`, `run_analyzers`,
  `dedupe_and_rank`, `review`, CLI). Report schema unchanged
  (prreview/report/v1). Only behavioral change: malformed input that
  was previously mis-reviewed is now rejected/abstained.
- Rollback: redeploy build-0001 product.zip (sha256 above); no data
  migration — the package is stateless.
