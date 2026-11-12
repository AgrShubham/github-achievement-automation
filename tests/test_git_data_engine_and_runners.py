"""Tests for GitHubClient retries, gitless Git Data Engine, planner delta math, and AchievementEngine."""

from __future__ import annotations

import email.message
import io
import json
import ssl
import threading
import urllib.error
from pathlib import Path
from unittest import mock

import pytest

from gh_achievement_studio.core.git_data_engine import (
    build_commit_message,
    ensure_collaborator_link,
    ensure_sandbox_repository,
    format_coauthor_trailer,
    run_gitless_pr_cycle,
)
from gh_achievement_studio.core.github_client import (
    GitHubApiError,
    GitHubClient,
    is_rate_limit_response,
)
from gh_achievement_studio.core.models import AccountSession, ProgressEvent, RunConfig
from gh_achievement_studio.core.runners import (
    AchievementEngine,
    EngineValidationError,
    build_execution_plan,
    validate_run_config,
)
from gh_achievement_studio.core.state import StateStore


def _make_session(login: str, user_id: int, token: str = "ghp_TokenValue123456") -> AccountSession:
    return AccountSession(
        login=login,
        user_id=user_id,
        name=login.title(),
        commit_email=f"{login}@gmail.com",
        token=token,
    )


def _http_error(code: int, body: str, headers: dict[str, str] | None = None) -> urllib.error.HTTPError:
    msg = email.message.Message()
    for k, v in (headers or {}).items():
        msg[k] = v
    return urllib.error.HTTPError(
        url="https://api.github.com/test",
        code=code,
        msg="err",
        hdrs=msg,
        fp=io.BytesIO(body.encode("utf-8")),
    )


class _FakeHTTPResponse:
    def __init__(self, status: int, body: dict[str, object], headers: dict[str, str] | None = None) -> None:
        self.status = status
        self._raw = json.dumps(body).encode("utf-8")
        msg = email.message.Message()
        for k, v in (headers or {}).items():
            msg[k] = v
        self.headers = msg

    def read(self) -> bytes:
        return self._raw

    def __enter__(self) -> _FakeHTTPResponse:
        return self

    def __exit__(self, *_args) -> None:
        return None


def test_github_client_retries_429_and_ssl_errors() -> None:
    assert is_rate_limit_response(429, "")
    assert is_rate_limit_response(403, "You have exceeded a secondary rate limit.")
    assert not is_rate_limit_response(404, "Not Found")

    client = GitHubClient("ghp_abc123456789", max_retries=3)
    err_429 = _http_error(429, "Too Many Requests", {"Retry-After": "3"})
    ok_resp = _FakeHTTPResponse(
        200,
        {"ok": True},
        {"X-OAuth-Scopes": "repo, read:user", "X-RateLimit-Remaining": "4990"},
    )
    with (
        mock.patch("urllib.request.urlopen", side_effect=[ssl.SSLError("unexpected EOF"), err_429, ok_resp]),
        mock.patch("gh_achievement_studio.core.github_client.time.sleep") as m_sleep,
    ):
        data = client.rest("GET", "/user")
        assert data == {"ok": True}
        assert client.last_scopes == ("repo", "read:user")
        assert client.last_rate_remaining == 4990
        assert len(m_sleep.call_args_list) == 2
        assert m_sleep.call_args_list[1] == mock.call(3.0)


def test_github_client_graphql_errors_raise() -> None:
    client = GitHubClient("tok")
    with mock.patch.object(client, "request_raw", return_value=(200, {}, {"errors": [{"message": "bad query"}]})):
        with pytest.raises(GitHubApiError, match="GraphQL error"):
            client.graphql("query { viewer { login } }")


def test_commit_and_coauthor_formatting() -> None:
    trailer = format_coauthor_trailer("Partner", "99+partner@users.noreply.github.com")
    assert trailer == "Co-authored-by: Partner <99+partner@users.noreply.github.com>"
    msg = build_commit_message("chore: pair", "details", trailer)
    assert msg == "chore: pair\n\ndetails\n\nCo-authored-by: Partner <99+partner@users.noreply.github.com>"

    with pytest.raises(ValueError):
        format_coauthor_trailer("", "a@b.com")
    with pytest.raises(ValueError):
        format_coauthor_trailer("Bob", "invalid-email")


def test_ensure_collaborator_link_accepts_invite() -> None:
    owner_client = mock.MagicMock()
    collab_client = mock.MagicMock()
    owner_client.rest.side_effect = [
        GitHubApiError("Not collaborator", status_code=404),
        {},
    ]
    collab_client.rest.side_effect = [
        [{"id": 77, "repository": {"full_name": "Buddy/sandbox"}}],
        {},
    ]
    ensure_collaborator_link(owner_client, collab_client, "Buddy", "sandbox", "Alice")
    owner_client.rest.assert_any_call(
        "PUT",
        "/repos/Buddy/sandbox/collaborators/Alice",
        payload={"permission": "push"},
    )
    collab_client.rest.assert_any_call("PATCH", "/user/repository_invitations/77")


def test_ensure_sandbox_repository_creates_and_initializes_empty_repo() -> None:
    owner_client = mock.MagicMock()
    owner_client.rest.side_effect = [
        GitHubApiError("Not Found", status_code=404),
        {"default_branch": "main"},
        {"object": {"sha": "abc"}},
        {"object": {"sha": "abc"}},
    ]
    repo_obj, branch, created = ensure_sandbox_repository(owner_client, "Alice", "sandbox", "public")
    assert created is True
    assert branch == "main"
    assert repo_obj["default_branch"] == "main"


def test_run_gitless_pr_cycle_cross_owner_pipeline() -> None:
    author_client = mock.MagicMock()
    merger_client = mock.MagicMock()
    author_session = _make_session("alice", 10)

    author_client.rest.side_effect = [
        {"object": {"sha": "base_commit_sha"}},  # GET git/ref
        {"tree": {"sha": "base_tree_sha"}},     # GET git/commits
        GitHubApiError("Not Found", status_code=404),  # GET contents/ACHIEVEMENTS_LOG.md
        {"sha": "new_blob_sha"},                # POST git/blobs
        {"sha": "new_tree_sha"},                # POST git/trees
        {"sha": "new_commit_sha"},              # POST git/commits
        {"ref": "refs/heads/feat"},             # POST git/refs
        {"number": 42},                         # POST pulls
        {},                                     # POST requested_reviewers
    ]
    merger_client.rest.side_effect = [
        {"merged": True},                       # PUT pulls/42/merge
        {},                                     # DELETE git/refs/heads/feat
    ]

    with mock.patch("gh_achievement_studio.core.git_data_engine.time.sleep"):
        pr_num = run_gitless_pr_cycle(
            author_client=author_client,
            merger_client=merger_client,
            author_session=author_session,
            repo_owner="bob",
            repo_name="collab-sandbox",
            default_branch="main",
            branch_name="feat",
            log_entry="- milestone",
            commit_subject="chore: pr",
            pr_title="chore: pr",
            pr_body="body",
            coauthor_trailer="Co-authored-by: Bob <20+bob@users.noreply.github.com>",
            requested_reviewer="bob",
        )

    assert pr_num == 42
    # Confirm commit creation included Co-authored-by trailer
    commit_call = author_client.rest.call_args_list[5]
    assert "Co-authored-by: Bob" in commit_call.kwargs["payload"]["message"]
    # Confirm merger_client (NOT author_client) merged & deleted branch
    merger_client.rest.assert_any_call("PUT", "/repos/bob/collab-sandbox/pulls/42/merge", payload={"merge_method": "merge"})
    merger_client.rest.assert_any_call("DELETE", "/repos/bob/collab-sandbox/git/refs/heads/feat")


def test_validation_guards() -> None:
    primary = _make_session("alice", 10)
    same_sec = _make_session("Alice", 10)
    diff_sec = _make_session("bob", 20)
    client = GitHubClient("tok")

    with pytest.raises(EngineValidationError, match="Cross-Owner"):
        validate_run_config(primary, client, None, RunConfig(cross_owner_mode=True))

    with pytest.raises(EngineValidationError, match="differ from the primary"):
        validate_run_config(primary, client, same_sec, RunConfig(cross_owner_mode=True))

    with pytest.raises(EngineValidationError, match="Galaxy Brain requires"):
        validate_run_config(primary, client, None, RunConfig(galaxy_target=2))

    with pytest.raises(EngineValidationError, match="blocks self-accepted"):
        validate_run_config(primary, client, same_sec, RunConfig(galaxy_target=2))

    with pytest.raises(EngineValidationError, match="placeholder"):
        validate_run_config(
            primary,
            client,
            diff_sec,
            RunConfig(pair_target=1, coauthor_name="Fake", coauthor_email="bot@example.com"),
        )


def test_build_execution_plan_delta_and_batch_cap() -> None:
    primary = _make_session("alice", 10)
    secondary = _make_session("bob", 20)
    client = GitHubClient("tok")

    cfg = RunConfig(
        cross_owner_mode=True,
        visibility="private",
        run_quickdraw=True,
        run_yolo=True,
        pull_shark_target=20,
        pair_target=5,
        galaxy_target=4,
        batch_limit=8,
        delay_seconds=1.0,
    )
    existing_prs = [
        {"number": 1, "commits": {"nodes": [{"commit": {"message": f"Co-authored-by: Bob <{secondary.noreply_email}>"}}]}},
        {"number": 2, "commits": {"nodes": [{"commit": {"message": "plain pr"}}]}},
    ]

    with (
        mock.patch("gh_achievement_studio.core.runners.fetch_repo_info", return_value={"name": "github-achievements-sandbox"}),
        mock.patch("gh_achievement_studio.core.runners.fetch_merged_prs_for_author", return_value=existing_prs),
        mock.patch("gh_achievement_studio.core.runners.fetch_quickdraw_issues", return_value=[]),
        mock.patch("gh_achievement_studio.core.runners.fetch_accepted_discussion_answers", return_value=1),
    ):
        plan = build_execution_plan(primary, client, secondary, cfg)

    assert plan.full_repo == "bob/github-achievements-sandbox"
    assert plan.quickdraw_to_create == 1
    assert plan.pair_prs_to_create == 4  # 5 target - 1 existing = 4
    assert plan.pull_shark_prs_to_create == 4  # batch_limit=8 -> 8 - 4 = 4
    assert plan.galaxy_answers_to_create == 3  # 4 - 1 = 3
    assert any("Private repos" in w for w in plan.warnings)


def test_achievement_engine_dry_run_and_cancel(tmp_path: Path) -> None:
    primary = _make_session("alice", 10)
    state_store = StateStore(tmp_path / "state.json")
    events: list[ProgressEvent] = []

    with (
        mock.patch("gh_achievement_studio.core.runners.fetch_repo_info", return_value=None),
        mock.patch("gh_achievement_studio.core.runners.ensure_sandbox_repository") as m_repo,
    ):
        engine = AchievementEngine(
            primary=primary,
            secondary=None,
            config=RunConfig(pull_shark_target=16, dry_run=True),
            state_store=state_store,
            on_event=events.append,
        )
        plan = engine.execute()
        assert plan.pull_shark_prs_to_create == 16
        m_repo.assert_not_called()
        assert any(e.kind == "completed" for e in events)
        assert not (tmp_path / "state.json").exists()

    # Pre-cancelled run stops cleanly before repo creation
    cancel_evt = threading.Event()
    cancel_evt.set()
    cancel_events: list[ProgressEvent] = []
    with (
        mock.patch("gh_achievement_studio.core.runners.fetch_repo_info", return_value=None),
        mock.patch("gh_achievement_studio.core.runners.ensure_sandbox_repository") as m_repo2,
    ):
        engine2 = AchievementEngine(
            primary=primary,
            secondary=None,
            config=RunConfig(pull_shark_target=2, dry_run=False),
            state_store=state_store,
            on_event=cancel_events.append,
            cancel_event=cancel_evt,
        )
        engine2.execute()
        m_repo2.assert_not_called()
        assert any(e.kind == "cancelled" for e in cancel_events)


def test_achievement_engine_full_multi_account_execute(tmp_path: Path) -> None:
    primary = _make_session("alice", 10)
    secondary = _make_session("bob", 20)
    state_store = StateStore(tmp_path / "state.json")
    events: list[ProgressEvent] = []

    cfg = RunConfig(
        cross_owner_mode=True,
        run_quickdraw=True,
        run_yolo=True,
        request_secondary_reviewer=True,
        pull_shark_target=2,
        pair_target=1,
        galaxy_target=1,
        delay_seconds=0.0,
    )

    engine = AchievementEngine(
        primary=primary,
        secondary=secondary,
        config=cfg,
        state_store=state_store,
        on_event=events.append,
    )
    engine.primary_client = mock.MagicMock()
    engine.secondary_client = mock.MagicMock()

    # Issue open + close
    engine.primary_client.rest.side_effect = [
        {"number": 1},
        {"created_at": "2026-01-01T00:00:00Z", "closed_at": "2026-01-01T00:00:02Z"},
    ]
    # GraphQL: categories query + comment add
    engine.primary_client.graphql.side_effect = [
        {
            "repository": {
                "id": "R_123",
                "discussionCategories": {"nodes": [{"id": "CAT_QA", "name": "Q&A", "isAnswerable": True}]},
            }
        },
        {"addDiscussionComment": {"comment": {"id": "COMM_1"}}},
    ]
    # GraphQL secondary: createDiscussion + markDiscussionCommentAsAnswer
    engine.secondary_client.graphql.side_effect = [
        {"createDiscussion": {"discussion": {"id": "DISC_1", "number": 7, "url": "https://github.com/d/7"}}},
        {"markDiscussionCommentAsAnswer": {"discussion": {"id": "DISC_1"}}},
    ]

    with (
        mock.patch("gh_achievement_studio.core.runners.fetch_repo_info", return_value=None),
        mock.patch("gh_achievement_studio.core.runners.ensure_sandbox_repository", return_value=({"has_discussions": True}, "main", True)),
        mock.patch("gh_achievement_studio.core.runners.ensure_collaborator_link") as m_collab,
        mock.patch("gh_achievement_studio.core.runners.run_gitless_pr_cycle", side_effect=[101, 102]) as m_pr,
    ):
        plan = engine.execute()

    assert plan.pair_prs_to_create == 1
    assert plan.pull_shark_prs_to_create == 1
    m_collab.assert_called_once()
    assert m_pr.call_count == 2
    assert state_store.load()["last_pr_number"] == 102
    assert events[-1].kind == "completed"
