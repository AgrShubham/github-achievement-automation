"""Tests for DPAPI secret encryption, secret redaction, StateStore, and CredentialStore."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

import pytest

from gh_achievement_studio.core.auth import AuthError, CredentialStore
from gh_achievement_studio.core.models import AccountSession
from gh_achievement_studio.core.security import (
    SecurityError,
    protect_secret,
    redact_secrets,
    unprotect_secret,
)
from gh_achievement_studio.core.state import StateStore


def test_dpapi_roundtrip_on_windows(tmp_path: Path) -> None:
    if sys.platform != "win32":
        pytest.skip("DPAPI is Windows-only")
    secret = "github_pat_11ABCDEF0123456789_Unicode✓"
    encrypted = protect_secret(secret)
    assert encrypted != secret
    assert secret not in encrypted
    assert unprotect_secret(encrypted) == secret


def test_dpapi_rejects_tampered_ciphertext() -> None:
    if sys.platform != "win32":
        pytest.skip("DPAPI is Windows-only")
    with pytest.raises(SecurityError):
        unprotect_secret("bm90LWEtdmFsaWQtZHBhcGktYmxvYg==")


def test_redact_secrets_explicit_and_pattern() -> None:
    explicit_secret = "custom-token-secret-value"
    gh_pat = "ghp_1234567890abcdefghijklmnop"
    text = f"Header Bearer {explicit_secret} and fallback {gh_pat}"
    masked = redact_secrets(text, [explicit_secret, "short"])
    assert explicit_secret not in masked
    assert gh_pat not in masked
    assert "***REDACTED***" in masked


def test_state_store_persistence_and_corruption_recovery(tmp_path: Path) -> None:
    state_file = tmp_path / "nested" / "state.json"
    store = StateStore(state_file)
    assert store.load() == {}

    store.save({"theme": "light", "last_pr_number": 10})
    assert store.load() == {"theme": "light", "last_pr_number": 10}

    updated = store.update({"last_repo": "alice/sandbox"})
    assert updated["theme"] == "light"
    assert updated["last_repo"] == "alice/sandbox"

    state_file.write_text("{broken json", encoding="utf-8")
    assert store.load() == {}


def test_credential_store_encrypts_token_and_reads_client_id(tmp_path: Path) -> None:
    if sys.platform != "win32":
        pytest.skip("DPAPI is Windows-only")
    cred_path = tmp_path / "credentials.json"
    store = CredentialStore(cred_path)

    session = AccountSession(
        login="octocat",
        user_id=583231,
        name="The Octocat",
        commit_email="octocat@github.com",
        token="ghp_TopSecretTestTokenValue123456",
        scopes=("repo", "read:user"),
        auth_method="pat",
    )
    store.save_session("primary", session)

    raw_disk = cred_path.read_text(encoding="utf-8")
    assert session.token not in raw_disk
    parsed = json.loads(raw_disk)
    assert "encrypted_token" in parsed["primary"]
    assert "token" not in parsed["primary"]

    restored = store.load_session("primary")
    assert restored == session

    store.save_oauth_client_id("Ov23liTestClientId")
    assert store.load_oauth_client_id() == "Ov23liTestClientId"

    with mock.patch.dict("os.environ", {"GH_OAUTH_CLIENT_ID": "EnvClientOverride"}):
        assert store.load_oauth_client_id() == "EnvClientOverride"

    store.clear_session("primary")
    assert store.load_session("primary") is None

    # Corrupt encrypted token should raise AuthError cleanly
    parsed["primary"] = {
        "login": "octocat",
        "user_id": 583231,
        "commit_email": "octocat@github.com",
        "encrypted_token": "invalid-blob",
    }
    cred_path.write_text(json.dumps(parsed), encoding="utf-8")
    with pytest.raises(AuthError):
        store.load_session("primary")
