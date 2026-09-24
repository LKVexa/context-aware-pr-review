import unittest

from prreview.differ import DiffError, parse_unified_diff
from prreview.analyzers import dedupe_and_rank, run_analyzers
from prreview.engine import review

# NOTE (0.1.1-partial): hunk headers below carry the TRUE line
# counts. The strengthened parser enforces declared counts
# (strict, abort-don't-infer); the old fixture understated/
# overstated them and relied on the lenient parser.
DIFF = """\
--- a/app/db.py
+++ b/app/db.py
@@ -10,2 +10,6 @@ def get_user(cursor, name):
 def get_user(cursor, name):
-    return cursor.execute("SELECT * FROM users WHERE name = ?", (name,))
+    query = "SELECT * FROM users WHERE name = '" + name + "'"
+    cursor.execute(query)
+    password = "hunter2secret"
+    # TODO: remove debug output
+    print(query)
@@ -30,2 +34,3 @@ def helper():
 def helper():
     pass
+    eval(user_input)
--- a/app/util.py
+++ b/app/util.py
@@ -1,1 +1,2 @@
 import requests
+resp = requests.get(url, verify=False)
"""


class Differ(unittest.TestCase):
    def test_parse_files_hunks_lines(self):
        files = parse_unified_diff(DIFF)
        self.assertEqual([f.path for f in files], ["app/db.py", "app/util.py"])
        self.assertEqual(len(files[0].hunks), 2)
        added = files[0].hunks[0].added
        self.assertEqual(added[0].new_lineno, 11)      # exact new-file lines
        self.assertEqual(files[1].added_lines[0].new_lineno, 2)

    def test_hunk_digest_stable(self):
        a = parse_unified_diff(DIFF)[0].hunks[0].digest()
        b = parse_unified_diff(DIFF)[0].hunks[0].digest()
        self.assertEqual(a, b)

    def test_malformed_diff_raises(self):
        for bad in ("", "not a diff at all", "--- a/x\nno plus line"):
            with self.assertRaises(DiffError):
                parse_unified_diff(bad)


class Analyzers(unittest.TestCase):
    def setUp(self):
        self.findings = dedupe_and_rank(run_analyzers(parse_unified_diff(DIFF)))

    def rule_ids(self):
        return {f.rule_id for f in self.findings}

    def test_expected_detections(self):
        ids = self.rule_ids()
        for expected in ("SEC-001", "SEC-002", "SEC-004", "SEC-005",
                         "MNT-001", "MNT-002"):
            self.assertIn(expected, ids)

    def test_exact_line_attachment(self):
        f = next(f for f in self.findings if f.rule_id == "SEC-002")
        self.assertEqual((f.path, f.line), ("app/db.py", 36))
        f2 = next(f for f in self.findings if f.rule_id == "SEC-005")
        self.assertEqual((f2.path, f2.line), ("app/util.py", 2))

    def test_ranked_by_severity(self):
        sevs = [f.severity for f in self.findings]
        order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
        self.assertEqual(sevs, sorted(sevs, key=order.get))

    def test_confidence_explicit_on_every_finding(self):
        for f in self.findings:
            self.assertIn(f.confidence, ("high", "medium", "low"))

    def test_dedupe(self):
        doubled = run_analyzers(parse_unified_diff(DIFF)) * 2
        self.assertEqual(len(dedupe_and_rank(doubled)),
                         len(self.findings))


class Guardrails(unittest.TestCase):
    def test_advisory_only_and_human_required(self):
        rep = review(DIFF, {"title": "tweak db"})
        self.assertEqual(rep["verdict"], "ADVISORY_ONLY")
        self.assertTrue(rep["human_review_required"])
        self.assertTrue(rep["coverage"]["not_a_pass_fail_authority"])

    def test_no_code_modification_api(self):
        import prreview.engine as e
        import prreview.analyzers as a
        import prreview.differ as d
        for mod in (e, a, d):
            for name in dir(mod):
                self.assertNotIn("apply", name.lower())
                self.assertNotIn("autofix", name.lower())

    def test_abstains_on_malformed_input(self):
        rep = review("garbage that is not a diff")
        self.assertEqual(rep["status"], "ABSTAINED")
        self.assertEqual(rep["findings"], [])
        self.assertIn("not reviewable", rep["abstention_reason"])
        self.assertEqual(rep["verdict"], "ADVISORY_ONLY")


class Report(unittest.TestCase):
    def setUp(self):
        self.rep = review(DIFF, {"title": "db tweak", "id": "PR-7",
                                 "base": "main", "head": "feat"})

    def test_layered_summary(self):
        s = self.rep["summary"]
        self.assertEqual(s["intent_layer"]["stated_title"], "db tweak")
        self.assertEqual(len(s["change_layer"]["files"]), 2)
        self.assertIn("app", s["change_layer"]["affected_modules"])
        self.assertIn(s["impact_layer"]["highest_severity"],
                      ("Critical", "High"))

    def test_annotations_carry_provenance(self):
        for a in self.rep["annotations"]:
            self.assertTrue(a["provenance"]["hunk_digest"].startswith("sha256:"))
            self.assertEqual(a["provenance"]["analyzer_version"], "0.1.1")

    def test_coverage_names_categories_and_boundaries(self):
        cov = self.rep["coverage"]
        self.assertEqual(cov["categories_checked"],
                         ["maintainability", "performance", "security"])
        self.assertTrue(any("no model inference" in b
                            for b in cov["analysis_boundaries"]))

    def test_deterministic(self):
        r2 = review(DIFF, {"title": "db tweak", "id": "PR-7",
                           "base": "main", "head": "feat"})
        self.assertEqual(self.rep["findings"], r2["findings"])


class StrictParsing(unittest.TestCase):
    """0.1.1-partial regression tests for reproduced baseline defects."""

    def test_surplus_added_line_rejected(self):
        # A004-F2: baseline silently accepted lines beyond the declared
        # counts and fabricated line numbers for them.
        bad = ("--- a/x.py\n+++ b/x.py\n@@ -1,1 +1,1 @@\n"
               "-old\n+new\n+eval(x)\n")
        with self.assertRaises(DiffError):
            parse_unified_diff(bad)
        rep = review(bad)
        self.assertEqual(rep["status"], "ABSTAINED")
        self.assertEqual(rep["findings"], [])

    def test_truncated_hunk_rejected(self):
        # A004-F3: baseline accepted hunks with fewer lines than declared.
        bad = "--- a/x.py\n+++ b/x.py\n@@ -1,5 +1,5 @@\n ctx\n+added\n"
        with self.assertRaises(DiffError):
            parse_unified_diff(bad)
        self.assertEqual(review(bad)["status"], "ABSTAINED")

    def test_junk_line_inside_hunk_rejected(self):
        # A004-F4: baseline silently dropped unrecognized lines mid-hunk.
        bad = ("--- a/x.py\n+++ b/x.py\n@@ -1,2 +1,2 @@\n"
               " ctx\nJUNK NOT DIFF\n+added\n")
        with self.assertRaises(DiffError):
            parse_unified_diff(bad)

    def test_deleted_file_header_lookalike_parsed_as_deletion(self):
        # A004-F5: a deleted line rendered as "--- foo" mid-hunk was
        # misread as a new file section and the deletion silently lost.
        d = "--- a/x.sql\n+++ b/x.sql\n@@ -1,2 +1,1 @@\n ctx\n--- comment line\n"
        files = parse_unified_diff(d)
        self.assertEqual(len(files), 1)
        lines = files[0].hunks[0].lines
        self.assertEqual([(l.kind, l.text) for l in lines],
                         [("ctx", "ctx"), ("del", "-- comment line")])

    def test_valid_diff_still_parses_and_no_newline_marker_ok(self):
        d = ("--- a/a.txt\n+++ b/a.txt\n@@ -1,1 +1,1 @@\n"
             "-old\n\\ No newline at end of file\n+new\n"
             "\\ No newline at end of file\n")
        files = parse_unified_diff(d)
        self.assertEqual([(l.kind, l.text) for l in files[0].hunks[0].lines],
                         [("del", "old"), ("add", "new")])


class MetaContract(unittest.TestCase):
    def test_non_mapping_pr_meta_abstains_not_raises(self):
        # A004-F1: baseline leaked AttributeError, violating the documented
        # "never raises on bad input" contract of review().
        good = "--- a/x\n+++ b/x\n@@ -1,1 +1,1 @@\n-old\n+new\n"
        for bad_meta in (["x"], "title", 42, {1, 2}):
            rep = review(good, bad_meta)
            self.assertEqual(rep["status"], "ABSTAINED")
            self.assertEqual(rep["verdict"], "ADVISORY_ONLY")
            self.assertIn("not reviewable", rep["abstention_reason"])

    def test_dict_and_none_meta_still_reviewed(self):
        good = "--- a/x\n+++ b/x\n@@ -1,1 +1,1 @@\n-old\n+new\n"
        self.assertEqual(review(good)["status"], "REVIEWED")
        self.assertEqual(review(good, {"title": "t"})["status"], "REVIEWED")



if __name__ == "__main__":
    unittest.main()
