# Audit and hardening — 0.1.2a1

Date: 2026-09-23. Source: JY-S002-P001 / 0.1.1-partial / run-0001 / product.
The source directory was preserved; work took place in a separate checkout.
All four Python implementation modules and the inherited tests were reviewed.

## Findings repaired

- Unsupported, binary, or mode-only sections could be silently skipped, reporting
  an apparently completed review of only part of a patch. The bounded parser
  now rejects unknown or incomplete sections across the entire input.
- Duplicate headers/files, invalid starts, overlapping hunks, inconsistent gaps,
  and unsafe paths could produce ambiguous or incorrect annotation locations.
  These now abstain; deletions retain the original path.
- Arbitrary backslash lines and blank unprefixed context lines were accepted.
  Only properly placed standard no-newline markers are accepted.
- Python's broad splitlines behavior treated Unicode separators inside source
  code as physical patch lines. Parsing now splits LF and normalizes CRLF.
- Findings and parse errors exposed source text, including detected credentials.
  Reports now omit all code excerpts and use fixed parser error descriptions.
- Invalid Unicode, excessive integer strings, and nonserializable metadata could
  escape the documented abstention behavior. Validation is bounded and reports
  remain serializable. CLI read/decode/JSON errors yield abstention without traces.
- The SQL rule reported parameterized %s queries as injection. Detection now
  distinguishes literal placeholders from f-string interpolation.
- CLI empty arguments now remain empty; duplicate JSON keys and nonfinite values
  are rejected. Exit 1 distinguishes processing abstention from a completed review.

## Release changes and validation

Package version 0.1.1-partial -> 0.1.2a1; analyzer version 0.1.0 -> 0.1.1.
Added installable packaging/CLI, Apache 2.0 LICENSE, NOTICE, README, security
boundaries, version control exclusions, pinned-action CI, and dependency updates.
The existing MIT donor reference and copyright are retained.

22 inherited tests passed before changes. 42 tests pass after changes, including
20 boundary/security/CLI regressions. Source and installed-wheel results are in
CHECK_RUNS.json; historical evidence is preserved in BASELINE_CHECK_RUNS.json.
Release artifacts include a source archive, wheel, and SHA-256 checksums.
Remote CI status is verified separately at publication and in the delivery index.

No runtime dependencies require upgrades. The build backend is constrained to
setuptools>=78,<85 and the tested local version was 84.0.0. No vulnerability
database scanner was run. This is a focused code audit, not a penetration test
or certification. The source carrier's full product roadmap remains incomplete.
