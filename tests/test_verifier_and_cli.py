"""Tests for verifier metrics, HTML badge parsing, and headless CLI wrapper."""

from __future__ import annotations

from unittest import mock

from gh_achievement_studio.cli import main as cli_main
from gh_achievement_studio.core.github_client import GitHubClient
from gh_achievement_studio.core.models import AccountSession
from gh_achievement_studio.core.verifier import (
    count_coauthored_prs,
    fetch_quickdraw_issues,
    parse_achievement_badges,
    verify_account_achievements,
)


def test_parse_achievement_badges_tiered_and_sidebar() -> None:
    html = """
    <div class="achievement-badge-card">
      <h3 class="f4 ws-normal">Pull Shark</h3>
      <span class="Label achievement-tier-label">x2</span>
    </div>
    <div class="achievement-badge-card">
      <h3 class="f4 ws-normal">Quickdraw</h3>
    </div>
    <div class="achievement-badge-card">
      <h3 class="f4 ws-normal">Pull Shark</h3>
      <span class="Label achievement-tier-label">x2</span>
    </div>
    """
    assert parse_achievement_badges(html) == ["Pull Shark (x2)", "Quickdraw"]

    sidebar_html = '<img alt="Achievement: YOLO" class="achievement-badge-sidebar" />'
    assert parse_achievement_badges(sidebar_html) == ["YOLO"]


def test_fetch_quickdraw_issues_and_coauthored_count() -> None:
    client = GitHubClient("tok")
    issues_payload = [
        {
            "number": 1,
            "created_at": "2026-01-01T00:00:00Z",
            "closed_at": "2026-01-01T00:00:04Z",
        },
        {
            "number": 2,
            "pull_request": {"url": "https://api.github.com/pulls/2"},
            "created_at": "2026-01-01T00:00:00Z",
            "closed_at": "2026-01-01T00:00:02Z",
        },
        {
            "number": 3,
            "created_at": "2026-01-01T00:10:00Z",
            "closed_at": "2026-01-01T00:25:00Z",
        },
    ]
    with mock.patch.object(client, "rest", return_value=issues_payload):
        qualifying = fetch_quickdraw_issues(client, "alice", "sandbox")
    assert len(qualifying) == 1
    assert qualifying[0]["number"] == 1
    assert qualifying[0]["elapsed_seconds"] == 4.0

    merged = [
        {"number": 1, "commits": {"nodes": [{"commit": {"message": "feat: x\n\nCo-authored-by: Bob <2+bob@users.noreply.github.com>"}}]}},
        {"number": 2, "commits": {"nodes": [{"commit": {"message": "feat: y"}}]}},
    ]
    assert count_coauthored_prs(merged) == 1
    assert count_coauthored_prs(merged, "2+bob@users.noreply.github.com") == 1
    assert count_coauthored_prs(merged, "9+other@users.noreply.github.com") == 0


def test_verify_account_achievements_and_cli_modes(capsys) -> None:
    session = AccountSession(
        login="alice",
        user_id=10,
        name="Alice",
        commit_email="alice@gmail.com",
        token="ghp_testToken123456",
    )
    client = GitHubClient(session.token)
    with (
        mock.patch("gh_achievement_studio.core.verifier.fetch_repo_info", return_value={"archived": False}),
        mock.patch(
            "gh_achievement_studio.core.verifier.fetch_merged_prs_for_author",
            return_value=[{"number": 1, "commits": {"nodes": []}}, {"number": 2, "commits": {"nodes": []}}],
        ),
        mock.patch("gh_achievement_studio.core.verifier.fetch_quickdraw_issues", return_value=[{"number": 1}]),
        mock.patch("gh_achievement_studio.core.verifier.fetch_accepted_discussion_answers", return_value=0),
        mock.patch("gh_achievement_studio.core.verifier.fetch_global_merged_prs_count", return_value=16),
        mock.patch("gh_achievement_studio.core.verifier.scrape_profile_achievements", return_value=["Quickdraw", "YOLO"]),
        mock.patch.object(client, "get_rate_limit", return_value=(4950, 5000)),
    ):
        report = verify_account_achievements(client, session, "alice", "sandbox")

    assert report.repo_merged_prs == 2
    assert report.global_merged_prs == 16
    assert report.quickdraw_issues == 1
    assert report.visible_badges == ("Quickdraw", "YOLO")
    assert report.rate_limit_remaining == 4950

    with (
        mock.patch("gh_achievement_studio.cli.main._resolve_sessions", return_value=(session, None)),
        mock.patch("gh_achievement_studio.cli.main.verify_account_achievements", return_value=report),
    ):
        rc = cli_main.main(["--verify-only"])
    assert rc == 0
    captured = capsys.readouterr()
    assert "Quickdraw, YOLO" in captured.out
    assert "4950/5000" in captured.out

    with (
        mock.patch("gh_achievement_studio.cli.main._resolve_sessions", return_value=(session, None)),
        mock.patch("gh_achievement_studio.core.runners.fetch_repo_info", return_value=None),
    ):
        rc_dry = cli_main.main(["--dry-run", "--pull-shark-target", "default"])
    assert rc_dry == 0
    assert "[DRY RUN]" in capsys.readouterr().out
