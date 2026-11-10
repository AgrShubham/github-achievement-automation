import argparse
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import execute_achievements as ea


class ExecuteAchievementsTests(unittest.TestCase):
    def test_pull_shark_tiers_mapping(self) -> None:
        ns = ea.parse_args(["--pull-shark-target", "bronze"])
        cfg = ea.config_from_args(ns)
        self.assertEqual(cfg.pull_shark_count, 16)

        ns_gold = ea.parse_args(["--pull-shark-target", "gold", "--batch-limit", "50"])
        cfg_gold = ea.config_from_args(ns_gold)
        self.assertEqual(cfg_gold.pull_shark_count, 1024)
        self.assertEqual(cfg_gold.batch_limit, 50)

        ns_custom = ea.parse_args(["--pr-count", "7"])
        cfg_custom = ea.config_from_args(ns_custom)
        self.assertEqual(cfg_custom.pull_shark_count, 7)

    def test_validation_rejects_negative_values(self) -> None:
        with self.assertRaises(ea.AutomationError):
            ea.config_from_args(ea.parse_args(["--delay-seconds", "-1"]))
        with self.assertRaises(ea.AutomationError):
            ea.config_from_args(ea.parse_args(["--batch-limit", "0"]))
        with self.assertRaises(ea.AutomationError):
            ea.config_from_args(ea.parse_args(["--pr-count", "-5"]))

    def test_coauthor_trailer_formatting_and_commit_message(self) -> None:
        trailer = ea.format_coauthor_trailer("Octocat", "583231+octocat@users.noreply.github.com")
        self.assertEqual(trailer, "Co-authored-by: Octocat <583231+octocat@users.noreply.github.com>")

        msg = ea.build_commit_message("chore: test", coauthor_trailer=trailer)
        self.assertEqual(
            msg,
            "chore: test\n\nCo-authored-by: Octocat <583231+octocat@users.noreply.github.com>",
        )

        with self.assertRaises(ea.AutomationError):
            ea.format_coauthor_trailer("", "a@b.com")
        with self.assertRaises(ea.AutomationError):
            ea.format_coauthor_trailer("Bob", "not-an-email")

    def test_placeholder_email_detection(self) -> None:
        self.assertTrue(ea.is_placeholder_email("bot@example.com"))
        self.assertTrue(ea.is_placeholder_email("user@fake.com"))
        self.assertFalse(ea.is_placeholder_email("98349772+AgrShubham@users.noreply.github.com"))
        self.assertFalse(ea.is_placeholder_email("real.user@gmail.com"))

    def test_count_coauthored_prs(self) -> None:
        merged = [
            {
                "number": 1,
                "commits": {
                    "nodes": [
                        {"commit": {"message": "feat: one\n\nCo-authored-by: Alice <123+alice@users.noreply.github.com>"}}
                    ]
                },
            },
            {
                "number": 2,
                "commits": {
                    "nodes": [
                        {"commit": {"message": "feat: two"}}
                    ]
                },
            },
            {
                "number": 3,
                "commits": {
                    "nodes": [
                        {"commit": {"message": "feat: three\n\nCo-authored-by: Bob <456+bob@users.noreply.github.com>"}}
                    ]
                },
            },
        ]
        self.assertEqual(ea.count_coauthored_prs(merged), 2)
        self.assertEqual(ea.count_coauthored_prs(merged, "123+alice@users.noreply.github.com"), 1)

    def test_rate_limit_detection_and_retry(self) -> None:
        self.assertTrue(ea.is_rate_limit_message("You have exceeded a secondary rate limit"))
        self.assertTrue(ea.is_rate_limit_message("HTTP 429 Too Many Requests"))
        self.assertFalse(ea.is_rate_limit_message("fatal: remote branch not found"))

        fail = subprocess.CompletedProcess(["gh"], 1, "", "HTTP 429 Too Many Requests\nRetry-After: 2")
        ok = subprocess.CompletedProcess(["gh"], 0, "success", "")
        with mock.patch.object(ea, "run_subprocess", side_effect=[fail, ok]) as m_sub, mock.patch("time.sleep") as m_sleep:
            res = ea.run_gh_with_retry(["pr", "list"], max_retries=2, base_backoff=1.0)
            self.assertEqual(res.stdout, "success")
            self.assertEqual(m_sub.call_count, 2)
            m_sleep.assert_called_once_with(2.0)

    def test_galaxy_brain_rejects_same_account_token(self) -> None:
        cfg = ea.AutomationConfig(galaxy_count=2, helper_token_env="TEST_HELPER_TOKEN")
        with (
            mock.patch.object(ea.shutil, "which", return_value="/usr/bin/tool"),
            mock.patch.object(ea, "run_subprocess", return_value=subprocess.CompletedProcess(["gh"], 0, "ok", "")),
            mock.patch.object(ea, "resolve_user_identity", return_value={"login": "AgrShubham", "id": 98349772}),
            mock.patch.object(ea, "gh_api_json", return_value={"resources": {"core": {"remaining": 4900, "limit": 5000}}}),
            mock.patch.dict(ea.os.environ, {"TEST_HELPER_TOKEN": "fake-secret-value"}),
            mock.patch.object(ea, "http_github_api", return_value={"login": "AgrShubham"}),
        ):
            with self.assertRaises(ea.AutomationError) as ctx:
                ea.validate_tools_and_preflight(cfg)
            self.assertIn("same as the primary account", str(ctx.exception))

    def test_dry_run_end_to_end_makes_no_mutations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "state.json"
            with (
                mock.patch.object(ea.shutil, "which", return_value="/usr/bin/tool"),
                mock.patch.object(ea, "run_subprocess", return_value=subprocess.CompletedProcess(["gh"], 0, "ok", "")),
                mock.patch.object(ea, "resolve_user_identity", return_value={"login": "AgrShubham", "id": 98349772}),
                mock.patch.object(ea, "gh_api_json", return_value={"resources": {"core": {"remaining": 4900, "limit": 5000}}}),
                mock.patch.object(ea, "fetch_repo_metadata", return_value=None),
            ):
                rc = ea.main([
                    "--dry-run",
                    "--pull-shark-target",
                    "bronze",
                    "--workdir",
                    tmp,
                    "--state-file",
                    str(state_path),
                ])
                self.assertEqual(rc, 0)
                self.assertFalse(state_path.exists())

    def test_idempotent_delta_calculation_with_existing_merged_prs(self) -> None:
        cfg = ea.AutomationConfig(
            repo_name="github-achievements-sandbox",
            owner="AgrShubham",
            pull_shark_count=16,
            delay_seconds=0.0,
        )
        existing_prs = [{"number": i, "commits": {"nodes": []}} for i in range(1, 13)]  # 12 already merged
        with (
            mock.patch.object(ea, "fetch_merged_prs_stats", return_value=existing_prs),
            mock.patch.object(ea, "execute_single_pr_cycle", side_effect=[13, 14, 15, 16]) as m_cycle,
            mock.patch.object(ea, "save_state"),
        ):
            existing, created = ea.run_pr_achievements(cfg, Path("."), "main", {})
            self.assertEqual(existing, 12)
            self.assertEqual(created, 4)
            self.assertEqual(m_cycle.call_count, 4)

    def test_parse_achievement_badges_with_tiers_and_fallback(self) -> None:
        tiered_html = """
        <img alt="Achievement: Pull Shark" class="achievement-badge-card" />
        <div class="d-flex">
          <h3 class="f4 ws-normal">Pull Shark</h3>
          <span class="Label achievement-tier-label achievement-tier-label--bronze">x2</span>
        </div>
        <img alt="Achievement: YOLO" class="achievement-badge-card" />
        <div class="d-flex">
          <h3 class="f4 ws-normal">YOLO</h3>
        </div>
        """
        self.assertEqual(ea.parse_achievement_badges(tiered_html), ["Pull Shark (x2)", "YOLO"])

        sidebar_only_html = '<img alt="Achievement: Quickdraw" class="achievement-badge-sidebar" />'
        self.assertEqual(ea.parse_achievement_badges(sidebar_only_html), ["Quickdraw"])


if __name__ == "__main__":
    unittest.main()

