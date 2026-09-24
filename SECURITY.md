# Security boundaries

This experimental tool supplies human-review suggestions, never an approval gate.
Only added lines are scanned. Multiline constructs, aliases, generated code, and
language-specific semantics may evade patterns. A clean report is not a security
assessment. Parameterized SQL is no longer reported merely for containing %s.

The parser accepts a bounded subset of text diffs. Unsupported sections cause
whole-input abstention. Input is never executed and source paths are never opened.
The in-process API accepts ordinary strings and JSON-shaped dictionaries; hostile
Python subclasses and OS-level resource exhaustion are outside its contract.
Callers exposed to adversarial traffic should enforce process time/memory limits
and rate limits in addition to parser limits.

Source excerpts and raw parse-error text are excluded from reports. PR metadata,
paths, timestamps, and SHA-256 digests remain visible. Keep these confidential
when they reveal sensitive project information. Reports are not authenticated.

No network client, remote connector, automatic repository modification, or merging
function is included. GitHub Actions needs read-only contents access.
No third-party runtime dependencies are installed. No vulnerability-database
scanner was available for the local build toolchain.

Report defects privately to the repository owner with a minimal redacted
reproduction. Do not include real credentials in public issues.
