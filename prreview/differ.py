"""Strict, bounded parsing of textual unified diffs with exact line locations.

Unsupported sections abstain rather than silently reducing review coverage.
Paths are report identifiers only; this module never opens source files.
"""
from __future__ import annotations
import hashlib
import re
from dataclasses import dataclass, field

MAX_DIFF_BYTES = 2 * 1024 * 1024
MAX_LINES = 20000
MAX_LINE_LENGTH = 4096
MAX_FILES = 500
MAX_HUNKS = 2000
MAX_ADDED_LINES = 5000

class DiffError(ValueError):
    pass

@dataclass
class Line:
    kind: str
    text: str
    new_lineno: int | None
    old_lineno: int | None

@dataclass
class Hunk:
    header: str
    lines: list = field(default_factory=list)

    def digest(self) -> str:
        body = self.header + "".join(f"{line.kind}:{line.text}\n" for line in self.lines)
        return "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()

    @property
    def added(self):
        return [line for line in self.lines if line.kind == "add"]

@dataclass
class FileDiff:
    path: str
    old_path: str
    hunks: list = field(default_factory=list)

    @property
    def added_lines(self):
        return [line for hunk in self.hunks for line in hunk.added]

_HUNK_RE = re.compile(r"@@ -([0-9]{1,9})(?:,([0-9]{1,9}))? \+([0-9]{1,9})(?:,([0-9]{1,9}))? @@(?: .*)?")
_INDEX_RE = re.compile(r"index [0-9a-fA-F]{4,64}\.\.[0-9a-fA-F]{4,64}(?: [0-7]{6})?")
_MODE_RE = re.compile(r"(?:old mode|new mode|new file mode|deleted file mode) [0-7]{6}")
_NO_NEWLINE = "\\ No newline at end of file"

def validate_diff_text(text: str) -> bytes:
    if type(text) is not str or not text or len(text) > MAX_DIFF_BYTES:
        raise DiffError("diff must be nonempty text within the size limit")
    try:
        encoded = text.encode("utf-8")
    except UnicodeError:
        raise DiffError("diff is not valid UTF-8 text") from None
    if len(encoded) > MAX_DIFF_BYTES or "\x00" in text:
        raise DiffError("diff exceeds the size limit or contains NUL")
    return encoded

def _path(header: str, prefix: str) -> str:
    path = header.split("\t", 1)[0]
    if path == "/dev/null":
        return path
    if path.startswith(prefix):
        path = path[len(prefix):]
    if (not path or path.startswith("/") or '"' in path or "\\" in path
            or ":" in path or any(ord(c) < 32 or 127 <= ord(c) <= 159 for c in path)
            or any(part in ("", ".", "..", ".git") for part in path.split("/"))):
        raise DiffError("unsafe or unsupported file path")
    return path

def parse_unified_diff(text: str) -> list[FileDiff]:
    validate_diff_text(text)
    rows = text.split("\n")
    if rows[-1] == "":
        rows.pop()
    if len(rows) > MAX_LINES or any(len(row) > MAX_LINE_LENGTH for row in rows):
        raise DiffError("diff exceeds the line count or line length limit")
    rows = [row.removesuffix("\r") for row in rows]
    files = []
    seen = set()
    current = None
    hunk = None
    git_header = None
    old_left = new_left = old_ln = new_ln = 0
    old_end = new_end = 0
    hunk_count = added_count = 0
    marker_allowed = False
    awaiting_new = False

    def finish_file():
        if current is not None and (awaiting_new or not current.hunks):
            raise DiffError("incomplete file section")
        if git_header is not None and current is None:
            raise DiffError("unsupported non-text file section")

    for row in rows:
        if row == _NO_NEWLINE:
            if not marker_allowed:
                raise DiffError("misplaced no-newline marker")
            marker_allowed = False
            continue
        if hunk is not None and (old_left or new_left):
            kind = row[:1]
            if kind == "+" and new_left:
                hunk.lines.append(Line("add", row[1:], new_ln, None))
                new_ln += 1
                new_left -= 1
                added_count += 1
            elif kind == "-" and old_left:
                hunk.lines.append(Line("del", row[1:], None, old_ln))
                old_ln += 1
                old_left -= 1
            elif kind == " " and old_left and new_left:
                hunk.lines.append(Line("ctx", row[1:], new_ln, old_ln))
                old_ln += 1
                new_ln += 1
                old_left -= 1
                new_left -= 1
            else:
                raise DiffError("hunk content does not match its declared counts")
            if added_count > MAX_ADDED_LINES:
                raise DiffError("too many added lines")
            marker_allowed = True
            continue
        marker_allowed = False
        if row.startswith("diff --git "):
            finish_file()
            current = None
            git_header = row
            continue
        if row.startswith("--- "):
            if current is not None:
                finish_file()
                git_header = None
            current = FileDiff(path="", old_path=_path(row[4:], "a/"))
            awaiting_new = True
            old_end = new_end = 0
            continue
        if row.startswith("+++ "):
            if current is None or not awaiting_new:
                raise DiffError("missing or duplicate file header")
            new_path = _path(row[4:], "b/")
            old_path = current.old_path
            if old_path == new_path == "/dev/null":
                raise DiffError("file cannot have two null paths")
            current.path = old_path if new_path == "/dev/null" else new_path
            if old_path != "/dev/null" and new_path != "/dev/null" and old_path != new_path:
                raise DiffError("renames are not supported")
            if git_header is not None:
                expected = f"diff --git a/{current.path} b/{current.path}"
                if git_header != expected:
                    raise DiffError("Git and unified file headers disagree")
            if current.path in seen:
                raise DiffError("duplicate file section")
            seen.add(current.path)
            files.append(current)
            if len(files) > MAX_FILES:
                raise DiffError("too many file sections")
            awaiting_new = False
            # Record null side for validating creation/deletion hunk ranges.
            current._deleted = new_path == "/dev/null"
            continue
        match = _HUNK_RE.fullmatch(row)
        if match:
            if current is None or awaiting_new:
                raise DiffError("hunk outside a complete file header")
            old_ln, old_count, new_ln, new_count = (
                int(value) if value is not None else 1 for value in match.groups())
            if (not old_count and not new_count
                    or old_count and not old_ln or new_count and not new_ln):
                raise DiffError("invalid hunk range")
            old_pos = old_ln - 1 if old_count else old_ln
            new_pos = new_ln - 1 if new_count else new_ln
            if (old_pos < old_end or new_pos < new_end
                    or old_pos - old_end != new_pos - new_end):
                raise DiffError("overlapping or inconsistent hunk locations")
            if (current.old_path == "/dev/null" and (old_ln or old_count)
                    or current._deleted and (new_ln or new_count)):
                raise DiffError("nonempty range for a null file")
            old_end, new_end = old_pos + old_count, new_pos + new_count
            old_left, new_left = old_count, new_count
            hunk = Hunk(header=row)
            current.hunks.append(hunk)
            hunk_count += 1
            if hunk_count > MAX_HUNKS:
                raise DiffError("too many hunks")
            continue
        if git_header is not None and current is None and (
                _INDEX_RE.fullmatch(row) or _MODE_RE.fullmatch(row)):
            continue
        if row == "" and not awaiting_new:
            continue
        raise DiffError("unsupported or malformed diff section")
    if old_left or new_left:
        raise DiffError("truncated hunk")
    finish_file()
    if not files:
        raise DiffError("no textual file sections found")
    return files
