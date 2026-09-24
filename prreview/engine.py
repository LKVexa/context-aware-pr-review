"""Review engine and report assembly (PAPER-CAP-01..04, PAPER-GRD-01..05,
COMP-05..08 slices).

Guardrails are structural, not advisory text:
- GRD-01/02: the report's verdict field is the literal string
  "ADVISORY_ONLY" and the engine exposes no approve/merge/pass-fail API.
- GRD-03: there is no code-modification API anywhere in the package.
- GRD-04: every finding carries an explicit confidence; the report
  separates deterministic analyzer output from anything else (this build
  contains deterministic analyzers only, and says so).
- GRD-05: malformed input or an unresolvable scope aborts with an
  ABSTAINED report rather than guessing (COMP-08).

PAPER-CAP-01's layered intent summary is deterministic here: PR
metadata + per-file change shape (files touched, hunks, adds/deletes,
touched modules by path). Model-based intent reconstruction (COMP-01)
is out of scope for this build and recorded as such.
"""

from __future__ import annotations

import hashlib
import json
import time

from .differ import DiffError, MAX_DIFF_BYTES, parse_unified_diff, validate_diff_text
from .analyzers import ANALYZER_VERSION, CATEGORIES, dedupe_and_rank, run_analyzers

ENGINE_VERSION = "0.1.2a1"


def review(diff_text: str, pr_meta: dict | None = None) -> dict:
    """Review plain text and JSON-shaped metadata; invalid input abstains.

    Arbitrary executable Python objects and resource exhaustion are outside
    this contract. Reports intentionally omit source-code excerpts.
    """
    started = time.time()
    base = {
        "schema": "prreview/report/v1",
        "engine_version": ENGINE_VERSION,
        "verdict": "ADVISORY_ONLY",     # GRD-01/02: never pass/fail
        "human_review_required": True,
        "pr": {k: None for k in ("title", "id", "base", "head")},
        "diff_sha256": None,
        "generated_at": started,
    }
    try:
        encoded = validate_diff_text(diff_text)
        base["diff_sha256"] = hashlib.sha256(encoded).hexdigest()
        pr_meta = _metadata(pr_meta)
        base["pr"] = pr_meta.copy()
        files = parse_unified_diff(diff_text)
    except DiffError as exc:
        return dict(base, status="ABSTAINED",
                    abstention_reason=f"input not reviewable: {exc}",
                    findings=[], coverage=_coverage(reviewed=False))

    findings = dedupe_and_rank(run_analyzers(files))
    summary = _layered_summary(files, findings, pr_meta)
    annotations = [_annotation(f) for f in findings]
    return dict(base, status="REVIEWED", summary=summary,
                findings=[f.as_dict() for f in findings],
                annotations=annotations,
                coverage=_coverage(reviewed=True),
                duration_ms=round((time.time() - started) * 1000, 3))

def _metadata(meta):
    if meta is None:
        meta = {}
    if type(meta) is not dict or len(meta) > 64:
        raise DiffError("PR metadata must be a bounded JSON object")
    clean = {}
    for key in ("title", "id", "base", "head"):
        value = meta.get(key)
        if value is None:
            clean[key] = None
            continue
        if key == "id" and type(value) is int and 0 <= value <= 10**12:
            clean[key] = value
            continue
        if type(value) is not str or len(value) > 4096 or "\x00" in value:
            raise DiffError("invalid PR metadata field")
        try:
            value.encode("utf-8")
        except UnicodeError:
            raise DiffError("invalid Unicode in PR metadata") from None
        clean[key] = value
    return clean


def _layered_summary(files, findings, pr_meta) -> dict:
    per_file = []
    for fd in files:
        adds = len(fd.added_lines)
        dels = sum(1 for h in fd.hunks for l in h.lines if l.kind == "del")
        per_file.append({"path": fd.path, "hunks": len(fd.hunks),
                         "added_lines": adds, "removed_lines": dels})
    modules = sorted({fd.path.rsplit("/", 1)[0] if "/" in fd.path else "."
                      for fd in files})
    sev_counts = {}
    for f in findings:
        sev_counts[f.severity] = sev_counts.get(f.severity, 0) + 1
    return {
        "intent_layer": {
            "stated_title": pr_meta.get("title"),
            "note": "deterministic summary only; model-based intent "
                    "reconstruction (COMP-01) not implemented in this build",
        },
        "change_layer": {"files": per_file,
                         "affected_modules": modules},
        "impact_layer": {"findings_by_severity": sev_counts,
                         "highest_severity": (findings[0].severity
                                              if findings else None)},
    }


def _annotation(f) -> dict:
    """COMP-06 — inline annotation record for exact file/line."""
    return {"path": f.path, "line": f.line,
            "severity": f.severity, "category": f.category,
            "rule": f.rule_id, "message": f.rationale,
            "confidence": f.confidence,
            "provenance": {"analyzer": f.analyzer,
                           "analyzer_version": f.analyzer_version,
                           "hunk_digest": f.hunk_digest}}


def _coverage(reviewed: bool) -> dict:
    """PAPER-CAP-04 / COMP-07 — checked categories and boundaries."""
    return {
        "categories_checked": sorted(CATEGORIES) if reviewed else [],
        "analyzer_version": ANALYZER_VERSION,
        "analysis_boundaries": [
            "added lines of unified diffs only (context/removed lines not analyzed)",
            "deterministic pattern analyzers only; no model inference, "
            "no repository graph (DATA-03), no review history (DATA-04), "
            "no CI/test signal (DATA-06) in this build",
            "language-agnostic heuristics; rule set is not exhaustive",
            "binary patches, quoted paths, renames and non-text-only sections abstain",
            "source excerpts omitted; metadata and file paths remain visible",
            "file modes are not security-reviewed",
        ],
        "not_a_pass_fail_authority": True,
    }


def main(argv=None):
    import sys
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) not in (1, 2):
        print("usage: python3 -m prreview.engine <diff-file> [pr-meta.json]",
              file=sys.stderr)
        return 2
    try:
        with open(argv[0], "rb") as fh:
            diff_text = fh.read(MAX_DIFF_BYTES + 1).decode("utf-8")
        meta = None
        if len(argv) == 2:
            with open(argv[1], "rb") as fh:
                raw = fh.read(65537)
            if len(raw) > 65536:
                raise ValueError("metadata too large")
            meta = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_pairs,
                              parse_constant=_invalid_constant)
        report = review(diff_text, meta)
    except (OSError, UnicodeError, ValueError, RecursionError):
        report = review("")
        report["abstention_reason"] = "input not reviewable: cannot read valid bounded UTF-8/JSON input"
    print(json.dumps(report, indent=2, allow_nan=False))
    # This is processing status only, never approval or a finding-severity gate.
    return 0 if report["status"] == "REVIEWED" else 1

def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate metadata key")
        result[key] = value
    return result

def _invalid_constant(value):
    raise ValueError("nonfinite JSON number")


if __name__ == "__main__":
    import sys
    sys.exit(main())
