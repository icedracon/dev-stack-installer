"""Integration tests: full pipeline over fixtures, persistence, repeated runs, CLI output."""
import contextlib
import copy
import io
import unittest
from datetime import date
from unittest import mock

from helpers import EnvHome, FakeHttp, fixture, make_home, PROFILE_TOML

from jobhunter import cli, pipeline
from jobhunter.config import load
from jobhunter.db import DB

TODAY = date(2026, 9, 24)
GH = "https://boards-api.greenhouse.io/v1/boards/acme/jobs"


def run(home, http=None):
    cfg = load(home)
    db = DB(cfg.db_path)
    http = http or FakeHttp()
    stats = pipeline.Pipeline(cfg, db, http, TODAY).run()
    return cfg, db, stats, http


def row(db, jid):
    return db.get(jid)


class TestPipeline(unittest.TestCase):
    def setUp(self):
        self.home = make_home()

    def test_funnel_and_hard_filters(self):
        cfg, db, stats, _ = run(self.home)
        self.assertEqual(stats.boards_ok, 6)
        self.assertEqual(row(db, "greenhouse:acme:1003")["filtered_reason"][:14], "excluded title")   # SOC L1
        self.assertIn("excluded title", row(db, "greenhouse:acme:1007")["filtered_reason"])            # Director
        self.assertIn("ineligible", row(db, "greenhouse:acme:1002")["filtered_reason"])                # US only
        self.assertIn("clearance", row(db, "greenhouse:acme:1004")["eligibility_reason"])              # TS/SCI
        self.assertIn("ineligible", row(db, "greenhouse:acme:1005")["filtered_reason"])                # London hybrid
        self.assertIn("ineligible", row(db, "lever:beta:0a1b2c3d-0000-4000-8000-000000000001")["filtered_reason"])  # EU-only
        self.assertIn("not a target role", row(db, "remotive:software-dev:556")["filtered_reason"])
        # 10+ yrs staff researcher in Yerevan: eligible, but the test profile has no research
        # skills, so it must rank as a poor match rather than be hidden or inflated.
        staff = row(db, "greenhouse:acme:1008")
        self.assertIsNone(staff["filtered_reason"])
        self.assertEqual(staff["eligible"], "yes")
        self.assertEqual(staff["experience_min"], 10)
        self.assertEqual(staff["label"], "Poor match")

    def test_eligible_jobs_kept_with_labels(self):
        cfg, db, *_ = run(self.home)
        top = row(db, "greenhouse:acme:1001")
        self.assertIsNone(top["filtered_reason"])
        self.assertEqual(top["eligible"], "uncertain")        # EMEA
        self.assertEqual(top["category"], "offensive")
        self.assertIn("active_directory", top["skills_required"])
        self.assertIn("osep", top["certs"])
        self.assertEqual(top["salary"]["currency"], "EUR")
        self.assertEqual(top["url"], "https://job-boards.greenhouse.io/acme/jobs/1001")  # canonical, no gh_src
        wz = row(db, "greenhouse:acme:1006")
        self.assertEqual(wz["eligible"], "yes")
        self.assertTrue(wz["injection_flags"])
        self.assertEqual(row(db, "ashby:gamma:11111111-2222-4333-8444-555555555555")["eligible"], "yes")

    def test_smartrecruiters_detail_only_for_survivors(self):
        _, db, _, http = run(self.home)
        detail_calls = [c for c in http.calls if c.endswith("/744000001")]
        self.assertEqual(len(detail_calls), 1)
        self.assertFalse(any(c.endswith("/744000002") for c in http.calls))  # Marketing Manager: no detail fetch
        self.assertIn("threat_modeling", row(db, "smartrecruiters:epsilon:744000001")["skills_required"])

    def test_cross_source_dedup_prefers_ats(self):
        _, db, stats, _ = run(self.home)
        agg = row(db, "remotive:software-dev:555")
        self.assertEqual(agg["dup_of"], "greenhouse:acme:1001")
        self.assertIsNone(row(db, "greenhouse:acme:1001")["dup_of"])
        self.assertGreaterEqual(stats.duplicates, 1)

    def test_repeated_run_skips_unchanged(self):
        cfg, db, s1, _ = run(self.home)
        db.conn.close()
        cfg, db, s2, _ = run(self.home)
        self.assertEqual(s2.new, 0)
        self.assertEqual(s2.updated, 0)
        self.assertEqual(s2.unchanged, s1.fetched)
        self.assertEqual(s2.title_filtered, 0)

    def test_changed_posting_is_reprocessed_and_llm_cache_invalidated(self):
        cfg, db, *_ = run(self.home)
        db.update_fields("greenhouse:acme:1001", llm_label="Strong", llm_note="x", llm_hash=row(db, "greenhouse:acme:1001")["raw_hash"])
        db.commit()
        payload = fixture("greenhouse_acme.json")
        payload["jobs"][0]["content"] += "&lt;p&gt;After a re-org this role now requires 8+ years of professional experience in offensive security.&lt;/p&gt;"
        _, db, s2, _ = run(self.home, FakeHttp(overrides={GH: payload}))
        self.assertEqual(s2.updated, 1)
        j = row(db, "greenhouse:acme:1001")
        self.assertEqual(j["experience_min"], 8)
        self.assertNotEqual(j["llm_hash"], j["raw_hash"])  # stale LLM verdict no longer displayed

    def test_removed_job_closed_only_after_successful_fetch(self):
        run(self.home)
        # board fails: nothing may be closed
        _, db, s2, _ = run(self.home, FakeHttp(fail={GH}))
        self.assertEqual(s2.closed, 0)
        self.assertIsNone(row(db, "greenhouse:acme:1001")["closed_at"])
        self.assertEqual(db.source("greenhouse:acme")["consecutive_failures"], 1)
        # board succeeds without job 1001: it is closed
        payload = fixture("greenhouse_acme.json")
        payload["jobs"] = [j for j in payload["jobs"] if not (isinstance(j, dict) and j.get("id") == 1001)]
        _, db, s3, _ = run(self.home, FakeHttp(overrides={GH: payload}))
        self.assertGreaterEqual(s3.closed, 1)
        self.assertIsNotNone(row(db, "greenhouse:acme:1001")["closed_at"])
        # and it re-opens if it comes back
        _, db, *_ = run(self.home)
        self.assertIsNone(row(db, "greenhouse:acme:1001")["closed_at"])

    def test_boards_skipped_after_repeated_failures(self):
        for _ in range(pipeline.DISABLE_AFTER_FAILURES):
            run(self.home, FakeHttp(fail={GH}))
        _, _, stats, http = run(self.home)
        self.assertIn("greenhouse:acme", stats.boards_skipped)
        self.assertNotIn(GH, http.calls)

    def test_total_outage_does_not_disable_boards(self):
        everything = set(FakeHttp().routes)
        for _ in range(pipeline.DISABLE_AFTER_FAILURES + 1):
            _, db, stats, _ = run(self.home, FakeHttp(fail=everything))
        self.assertEqual(stats.boards_skipped, [])
        self.assertEqual(db.source("greenhouse:acme")["consecutive_failures"], 0)

    def test_user_state_survives_reingest_and_reposts_inherit(self):
        cfg, db, *_ = run(self.home)
        db.set_state("greenhouse:acme:1006", "rejected", reason="not interested")
        db.commit()
        payload = fixture("greenhouse_acme.json")
        repost = copy.deepcopy(payload["jobs"][5])
        repost["id"] = 2006
        payload["jobs"] = [j for j in payload["jobs"] if not (isinstance(j, dict) and j.get("id") == 1006)] + [repost]
        _, db, s2, _ = run(self.home, FakeHttp(overrides={GH: payload}))
        self.assertEqual(db.state("greenhouse:acme:1006")["status"], "rejected")
        self.assertEqual(db.state("greenhouse:acme:2006")["status"], "rejected")
        self.assertEqual(s2.inherited, 1)

    def test_blocked_company_rule(self):
        cfg, db, *_ = run(self.home)
        db.add_rule("company", "Acme")
        db.commit()
        db.conn.close()
        payload = fixture("greenhouse_acme.json")
        payload["jobs"][0]["title"] += " "  # force reprocessing of one job
        _, db, *_ = run(self.home, FakeHttp(overrides={GH: payload}))
        self.assertEqual(row(db, "greenhouse:acme:1001")["filtered_reason"], "blocked company")

    def test_profile_change_triggers_rescore_without_refetch_changes(self):
        cfg, db, *_ = run(self.home)
        before = row(db, "greenhouse:acme:1001")["score"]
        (self.home / "config" / "profile.toml").write_text(PROFILE_TOML.replace("years_experience = 3", "years_experience = 0"))
        cfg2, db2, s2, _ = run(self.home)
        after = row(db2, "greenhouse:acme:1001")["score"]
        self.assertLess(after, before)
        self.assertEqual(s2.new, 0)


class TestCli(unittest.TestCase):
    def setUp(self):
        self.home = make_home()

    def jh(self, *argv) -> str:
        buf = io.StringIO()
        with EnvHome(self.home), mock.patch.object(pipeline, "Http", lambda *a, **k: FakeHttp()), \
                contextlib.redirect_stdout(buf):
            cli.main(list(argv))
        return buf.getvalue()

    def test_find_output_has_apply_links_only_at_bottom(self):
        text = self.jh("find", "20")
        head, sep, tail = text.partition("\nAPPLY\n")
        self.assertTrue(sep, text)
        self.assertNotIn("https://", head)
        self.assertIn("https://job-boards.greenhouse.io/acme/jobs/1001", tail)
        self.assertNotIn("SOC Analyst", text)
        self.assertNotIn("Director", text)
        self.assertNotIn("Remote, US", text)

    def test_new_then_nothing_new(self):
        self.jh("find")
        self.assertIn("No matching jobs.", self.jh("new"))

    def test_reject_shortlist_applied_by_number(self):
        self.jh("find", "20")
        self.assertIn("rejected:", self.jh("reject", "1", "too", "senior"))
        self.assertIn("shortlisted:", self.jh("shortlist", "2"))
        self.assertIn("applied:", self.jh("applied", "2", "--cv", "redteam"))
        self.assertIn("applied", self.jh("show", "applied"))
        self.assertIn("rejected", self.jh("show", "rejected"))

    def test_applied_job_not_shown_again(self):
        self.jh("find", "20")
        self.jh("show", "best", "20")
        self.jh("applied", "1")
        with EnvHome(self.home):
            cfg = load()
            db = DB(cfg.db_path)
            applied_id = db.conn.execute("SELECT job_id FROM user_state WHERE status='applied'").fetchone()[0]
            title = db.get(applied_id)["title"]
            company = db.get(applied_id)["company"]
        best = self.jh("show", "best", "20")
        self.assertNotIn(f"{company} — {title}  [", best)

    def test_views_and_why(self):
        self.jh("find", "20")
        appsec = self.jh("show", "appsec")
        self.assertIn("Product Security Engineer", appsec)
        self.assertNotIn("Red Team", appsec.split("\nAPPLY")[0])
        why = self.jh("why", "1")
        self.assertIn("Score components", why)
        self.assertIn("=", why)

    def test_apply_pack_fences_untrusted_text(self):
        self.jh("find", "20")
        self.jh("show", "appsec")
        pack = self.jh("apply", "1")
        self.assertIn("<<<UNTRUSTED_JOB_TEXT", pack)
        self.assertIn("SUBMISSION: human only", pack)
        self.assertIn("CV ROUTING", pack)
        self.assertTrue(list((self.home / "applications").glob("*/pack.md")))

    def test_digest_and_assess_cache(self):
        self.jh("find", "20")
        d = self.jh("digest", "3")
        self.assertIn('"n":1', d)
        self.jh("assess", "1", "--label", "Reasonable match", "--note", "EMEA ok per careers page")
        d2 = self.jh("digest", "3")
        self.assertNotEqual(d.splitlines()[2], d2.splitlines()[2] if len(d2.splitlines()) > 2 else "")

    def test_add_manual_url(self):
        tf = self.home / "jd.txt"
        tf.write_text("Remote (worldwide). 2+ years of experience with Active Directory and Kerberos attacks.")
        out = self.jh("add", "https://www.linkedin.com/jobs/view/red-team-operator-123456789/?trk=abc",
                      "--title", "Red Team Operator", "--company", "Zeta", "--text-file", str(tf))
        self.assertIn("Zeta — Red Team Operator", out)
        self.assertIn("\nAPPLY\n", out)


if __name__ == "__main__":
    unittest.main()
