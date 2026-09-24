"""Regression tests for 0.1.2a1 boundary and disclosure fixes."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from prreview import differ
from prreview.engine import main, review

GOOD = "--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-old\n+new\n"

def addition(line):
    return "--- /dev/null\n+++ b/x.py\n@@ -0,0 +1 @@\n+" + line + "\n"

class BoundaryTests(unittest.TestCase):
    def abstains(self, value, meta=None):
        report = review(value, meta)
        self.assertEqual(report["status"], "ABSTAINED")
        self.assertEqual(report["findings"], [])
        json.dumps(report, allow_nan=False)
        return report

    def test_surrogate_and_nontext_diff(self):
        for value in ("\ud800", b"diff", None, 3):
            with self.subTest(value=repr(value)):
                self.abstains(value)

    def test_nonserializable_metadata(self):
        for value in ({"title": object()}, {"id": float("nan")},
                      {"id": True}, {"base": []}, {"head": "\ud800"},
                      {"title": "x" * 4097}, {"id": -1}):
            self.abstains(GOOD, value)
        self.assertEqual(review(GOOD, {"id": 42})["status"], "REVIEWED")

    def test_invalid_header_count_never_leaks_value_error(self):
        for header in ("@@ -0 +0 @@", "@@ -1,0 +1,0 @@",
                       "@@ -" + "1"*4500 + " +1 @@", "@@ invalid @@"):
            self.abstains("--- a/x\n+++ b/x\n" + header + "\n-old\n+new\n")

    def test_binary_and_mode_only_sections_not_skipped(self):
        for tail in ("diff --git a/bin b/bin\nBinary files a/bin and b/bin differ\n",
                     "diff --git a/x b/x\nold mode 100644\nnew mode 100755\n",
                     "diff --git a/new b/new\n", "@@ malformed @@\n"):
            self.abstains(GOOD + tail)

    def test_duplicate_headers_and_files(self):
        self.abstains(GOOD + GOOD)
        self.abstains(GOOD.replace("@@", "+++ b/x.py\n@@", 1))

    def test_hunk_overlap_and_inconsistent_gaps(self):
        for hunk in ("@@ -1 +1 @@", "@@ -3 +4 @@"):
            self.abstains(GOOD + hunk + "\n-old\n+new\n")

    def test_unsafe_paths(self):
        for path in ("../x", "/x", "C:/x", ".git/config", "a//b",
                     "x\\y", '"x"', "x\x01", "x/./y"):
            self.abstains(GOOD.replace("a/x.py", path).replace("b/x.py", path))

    def test_git_header_mismatch(self):
        self.abstains("diff --git a/other b/other\n" + GOOD)
        self.assertEqual(review("diff --git a/x.py b/x.py\n"
                                "index 1234..5678 100644\n" + GOOD)["status"], "REVIEWED")

    def test_blank_context_and_fake_markers_rejected(self):
        for body in ("\n", "\\ ignored\n-old\n+new\n",
                     "\\ No newline at end of file\n-old\n+new\n"):
            self.abstains("--- a/x\n+++ b/x\n@@ -1 +1 @@\n" + body)

    def test_quoted_and_renamed_paths_abstain(self):
        self.abstains(GOOD.replace("b/x.py", "b/y.py"))
        self.abstains(GOOD.replace("a/x.py", '"a/x.py"'))

    def test_crlf_and_unicode_line_separator_preserve_line_location(self):
        report = review(addition("eval(x)\u2028suffix").replace("\n", "\r\n"))
        self.assertEqual(report["status"], "REVIEWED")
        self.assertEqual(report["findings"][0]["line"], 1)

    def test_deleted_file_uses_original_path(self):
        report = review("--- a/x.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-old\n")
        self.assertEqual(report["summary"]["change_layer"]["files"][0]["path"], "x.py")
        self.assertEqual(report["findings"], [])

    def test_null_file_nonempty_range_rejected(self):
        self.abstains(GOOD.replace("--- a/x.py", "--- /dev/null"))
        self.abstains(GOOD.replace("+++ b/x.py", "+++ /dev/null"))

    def test_resource_limits(self):
        self.abstains("x" * (differ.MAX_DIFF_BYTES + 1))
        self.abstains(addition("x" * (differ.MAX_LINE_LENGTH + 1)))
        with patch.object(differ, "MAX_LINES", 4):
            self.abstains(GOOD)
        with patch.object(differ, "MAX_FILES", 1):
            self.abstains(GOOD + GOOD.replace("x.py", "y.py"))
        with patch.object(differ, "MAX_ADDED_LINES", 1):
            self.abstains("--- /dev/null\n+++ b/x\n@@ -0,0 +1,2 @@\n+a\n+b\n")

    def test_error_and_all_findings_omit_source(self):
        secret = "credential-for-regression-only"
        report = review(addition('password = "' + secret + '" # TODO'))
        self.assertGreaterEqual(len(report["findings"]), 2)
        self.assertNotIn(secret, json.dumps(report))
        report = self.abstains(GOOD + secret)
        self.assertNotIn(secret, json.dumps(report))

    def test_parameterized_sql_not_flagged_as_interpolation(self):
        safe = review(addition('cursor.execute("SELECT * FROM users WHERE id=%s", (user_id,))'))
        unsafe = review(addition('cursor.execute(f"SELECT * FROM users WHERE id={user_id}")'))
        self.assertNotIn("SEC-004", {f["rule_id"] for f in safe["findings"]})
        self.assertIn("SEC-004", {f["rule_id"] for f in unsafe["findings"]})

class CliTests(unittest.TestCase):
    def invoke(self, args):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            status = main(args)
        return status, json.loads(stdout.getvalue())

    def test_missing_file_abstains_without_traceback(self):
        with tempfile.TemporaryDirectory() as temp:
            code, report = self.invoke([str(Path(temp) / "missing")])
        self.assertEqual(code, 1)
        self.assertEqual(report["status"], "ABSTAINED")

    def test_bad_json_and_duplicate_keys_abstain(self):
        with tempfile.TemporaryDirectory() as temp:
            diff = Path(temp) / "diff"
            meta = Path(temp) / "meta"
            diff.write_text(GOOD, encoding="utf-8")
            for content in ('{"title":"a","title":"b"}', '{"id":NaN}', "{", "["*2000):
                meta.write_text(content, encoding="utf-8")
                code, report = self.invoke([str(diff), str(meta)])
                self.assertEqual(code, 1)
                self.assertEqual(report["status"], "ABSTAINED")

    def test_findings_do_not_set_approval_exit_code(self):
        with tempfile.TemporaryDirectory() as temp:
            diff = Path(temp) / "diff"
            diff.write_text(addition("eval(untrusted)"), encoding="utf-8")
            code, report = self.invoke([str(diff)])
        self.assertEqual(code, 0)
        self.assertTrue(report["findings"])
        self.assertEqual(report["verdict"], "ADVISORY_ONLY")

    def test_explicit_empty_argv_not_replaced_with_process_args(self):
        with patch("sys.argv", ["prreview", "wrong"]), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main([]), 2)
