"""COMP-04 — deterministic multi-category review analyzers.

Each analyzer is a pure function over added lines: (file, line) →
findings with category, severity, rationale, confidence, and analyzer
version — deterministic tool results, kept distinguishable from model
inference (package rule 3; no model inference exists in this build).
Severity taxonomy Critical/High/Medium/Low follows the retrieved
BC-ALAgents donor's review taxonomy (MIT; see vendor/ and notices).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict

ANALYZER_VERSION = "0.1.1"

SEVERITIES = ("Critical", "High", "Medium", "Low")


@dataclass(frozen=True)
class Finding:
    category: str
    rule_id: str
    severity: str
    path: str
    line: int
    excerpt: str
    rationale: str
    confidence: str          # "high" | "medium" | "low" — explicit (PAPER-GRD-04)
    analyzer: str
    analyzer_version: str
    hunk_digest: str

    def as_dict(self):
        return asdict(self)


_SEC_RULES = [
    ("SEC-001", "Critical", re.compile(
        r"(?i)(api[_-]?key|secret|passwd|password|token)\s*[:=]\s*['\"][^'\"]{8,}"),
     "possible hardcoded credential", "medium"),
    ("SEC-002", "High", re.compile(r"\beval\s*\(|\bexec\s*\("),
     "dynamic code execution added", "high"),
    ("SEC-003", "High", re.compile(r"subprocess\.[a-zA-Z_]+\([^)]*shell\s*=\s*True"),
     "subprocess with shell=True", "high"),
    ("SEC-004", "High", re.compile(
        r'(?i)(?:"[^"]*\b(select|insert|update|delete)\b[^"]*"\s*\+'
        r"|'[^']*\b(select|insert|update|delete)\b[^']*'\s*\+"
        r"""|execute\s*\(\s*f["'][^"')]*\{)"""),
     "SQL built by string interpolation/concatenation", "medium"),
    ("SEC-005", "Medium", re.compile(r"(?i)verify\s*=\s*False|CERT_NONE"),
     "TLS verification disabled", "high"),
    ("SEC-006", "High", re.compile(r"pickle\.loads?\s*\("),
     "unpickling of external data", "medium"),
    ("SEC-007", "Medium", re.compile(r"\bmd5\s*\(|hashlib\.md5|hashlib\.sha1\b"),
     "weak hash primitive added", "high"),
]

_MAINT_RULES = [
    ("MNT-001", "Low", re.compile(r"\bTODO\b|\bFIXME\b|\bXXX\b"),
     "unresolved TODO/FIXME marker added", "high"),
    ("MNT-002", "Low", re.compile(r"^\s*print\s*\(|console\.log\s*\("),
     "debug print/logging added to committed code", "medium"),
    ("MNT-003", "Medium", re.compile(r"except\s*:\s*(pass)?\s*$|except\s+Exception\s*:\s*pass"),
     "broad or silent exception swallowing", "high"),
    ("MNT-004", "Low", re.compile(r".{161,}"),
     "line exceeds 160 characters", "high"),
]

_PERF_RULES = [
    ("PRF-001", "Medium", re.compile(r"\.read\(\)\s*\.split|readlines\(\)\s*\["),
     "whole-file read pattern in what may be a hot path", "low"),
    ("PRF-002", "Low", re.compile(r"\+\s*=\s*[\"'].*[\"']\s*(#|$)"),
     "string accumulation via += in a loop is quadratic if repeated", "low"),
    ("PRF-003", "Medium", re.compile(r"time\.sleep\s*\(\s*[0-9]"),
     "fixed sleep added — consider event/poll with timeout", "medium"),
]

CATEGORIES = {
    "security": _SEC_RULES,
    "maintainability": _MAINT_RULES,
    "performance": _PERF_RULES,
}


def run_analyzers(file_diffs) -> list[Finding]:
    findings: list[Finding] = []
    for fd in file_diffs:
        for hunk in fd.hunks:
            hd = hunk.digest()
            for line in hunk.added:
                for category, rules in CATEGORIES.items():
                    for rule_id, severity, rx, rationale, confidence in rules:
                        if rx.search(line.text):
                            findings.append(Finding(
                                category=category, rule_id=rule_id,
                                severity=severity, path=fd.path,
                                line=line.new_lineno,
                                excerpt="[source excerpt omitted]",
                                rationale=rationale, confidence=confidence,
                                analyzer=f"deterministic/{category}",
                                analyzer_version=ANALYZER_VERSION,
                                hunk_digest=hd))
    return findings


def dedupe_and_rank(findings: list[Finding]) -> list[Finding]:
    """COMP-05 — deduplicate (same rule+path+line) and rank by severity
    then category then location; deterministic total order."""
    seen = {}
    for f in findings:
        seen.setdefault((f.rule_id, f.path, f.line), f)
    order = {s: i for i, s in enumerate(SEVERITIES)}
    return sorted(seen.values(),
                  key=lambda f: (order[f.severity], f.category, f.path,
                                 f.line, f.rule_id))
