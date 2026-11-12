"""Tests for GitHub OAuth Device Flow, PAT validation, email lookup, and gh import."""

from __future__ import annotations

import subprocess
from unittest import mock

import pytest

from gh_achievement_studio.core.auth import (
    AuthError,
    DeviceCodeChallenge,
    authenticate_with_token,
    import_gh_cli_token,
    poll_device_access_token,
    request_device_code,
    resolve_commit_email,
)
from gh_achievement_studio.core.github_client import GitHubApiError, GitHubClient


def test_request_device_code_validation_and_success() -> None:
    with pytest.raises(AuthError):
        request_device_code("   ")

    fake_resp = {
        "device_code": "dev123",
        "user_code": "ABCD-1234",
        "verification_uri": "https://github.com/login/device",
        "expires_in": 900,
        "interval": 5,
    }
    with mock.patch("gh_achievement_studio.core.auth._post_oauth_form", return_value=fake_resp):
        challenge = request_device_code("Ov23liTest")
        assert challenge.device_code == "dev123"
        assert challenge.user_code == "ABCD-1234"
        assert challenge.interval == 5


def test_poll_device_access_token_states() -> None:
    challenge = DeviceCodeChallenge(
        device_code="dev123",
        user_code="ABCD-1234",
        verification_uri="https://github.com/login/device",
        expires_in=60,
        interval=2,
    )
    responses = [
        {"error": "authorization_pending"},
        {"error": "slow_down"},
        {"access_token": "gho_validDeviceToken999"},
    ]
    with (
        mock.patch("gh_achievement_studio.core.auth._post_oauth_form", side_effect=responses),
        mock.patch("gh_achievement_studio.core.auth.time.sleep") as m_sleep,
    ):
        token = poll_device_access_token("Ov23liTest", challenge)
        assert token == "gho_validDeviceToken999"
        # slow_down bumps interval from 2 -> 7
        assert m_sleep.call_args_list == [mock.call(2), mock.call(2), mock.call(7)]

    # Cancelled during poll
    with pytest.raises(AuthError, match="cancelled"):
        poll_device_access_token("Ov23liTest", challenge, should_cancel=lambda: True)

    # Expired token error
    with (
        mock.patch("gh_achievement_studio.core.auth._post_oauth_form", return_value={"error": "expired_token"}),
        mock.patch("gh_achievement_studio.core.auth.time.sleep"),
    ):
        with pytest.raises(AuthError, match="expired_token"):
            poll_device_access_token("Ov23liTest", challenge)


def test_resolve_commit_email_priority() -> None:
    user_obj = {"login": "alice", "id": 101, "email": "public@alice.dev"}
    client = GitHubClient("tok")

    # 1. Primary verified email wins
    with mock.patch.object(
        client,
        "rest",
        return_value=[
            {"email": "secondary@alice.dev", "verified": True, "primary": False},
            {"email": "primary@alice.dev", "verified": True, "primary": True},
        ],
    ):
        assert resolve_commit_email(client, user_obj) == "primary@alice.dev"

    # 2. Verified non-primary beats public profile email
    with mock.patch.object(
        client,
        "rest",
        return_value=[
            {"email": "unverified@alice.dev", "verified": False, "primary": True},
            {"email": "verified@alice.dev", "verified": True, "primary": False},
        ],
    ):
        assert resolve_commit_email(client, user_obj) == "verified@alice.dev"

    # 3. API 403 falls back to public email, then noreply
    with mock.patch.object(client, "rest", side_effect=GitHubApiError("forbidden", status_code=403)):
        assert resolve_commit_email(client, user_obj) == "public@alice.dev"
        assert (
            resolve_commit_email(client, {"login": "alice", "id": 101, "email": ""})
            == "101+alice@users.noreply.github.com"
        )


def test_authenticate_with_token_and_gh_import() -> None:
    with pytest.raises(AuthError):
        authenticate_with_token("   ")

    with mock.patch("gh_achievement_studio.core.auth.GitHubClient") as mock_cls:
        inst = mock_cls.return_value
        inst.last_scopes = ("repo", "read:user")
        inst.rest.side_effect = [
            {"login": "bob", "id": 42, "name": "Bob Dev", "avatar_url": "https://avatars/bob"},
            [{"email": "bob@example.org", "verified": True, "primary": True}],
        ]
        sess = authenticate_with_token("ghp_1234567890", auth_method="pat")
        assert sess.login == "bob"
        assert sess.user_id == 42
        assert sess.commit_email == "bob@example.org"
        assert sess.noreply_email == "42+bob@users.noreply.github.com"
        assert sess.scopes == ("repo", "read:user")

    with mock.patch("gh_achievement_studio.core.auth.shutil.which", return_value=None):
        with pytest.raises(AuthError, match="not installed"):
            import_gh_cli_token()

    with (
        mock.patch("gh_achievement_studio.core.auth.shutil.which", return_value="C:/gh.exe"),
        mock.patch(
            "gh_achievement_studio.core.auth.subprocess.run",
            return_value=subprocess.CompletedProcess(["gh"], 0, "gho_cliToken123\n", ""),
        ),
    ):
        assert import_gh_cli_token() == "gho_cliToken123"
