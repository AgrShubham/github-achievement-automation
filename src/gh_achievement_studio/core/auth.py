"""GitHub authentication (OAuth Device Flow, PAT validation, gh CLI import, DPAPI storage)."""

from __future__ import annotations

import dataclasses
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable

from .github_client import GitHubApiError, GitHubClient
from .models import AccountSession
from .security import SecurityError, protect_secret, unprotect_secret
from .state import default_app_dir

# Optional public GitHub OAuth App Client ID (Device Flow enabled, no secret needed).
# Override at runtime via GH_OAUTH_CLIENT_ID or in the Accounts tab.
DEFAULT_OAUTH_CLIENT_ID = ""


class AuthError(RuntimeError):
    """Raised when GitHub authentication or token persistence fails."""


@dataclasses.dataclass(frozen=True)
class DeviceCodeChallenge:
    device_code: str
    user_code: str
    verification_uri: str
    expires_in: int
    interval: int


def _post_oauth_form(url: str, form: dict[str, str], timeout: int = 20) -> dict[str, str]:
    encoded = urllib.parse.urlencode(form).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=encoded,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "GitHubAchievementStudio/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise AuthError(f"OAuth request to {url} failed: {exc}") from exc


def request_device_code(
    client_id: str,
    scope: str = "repo read:user user:email write:discussion",
) -> DeviceCodeChallenge:
    clean_id = client_id.strip()
    if not clean_id:
        raise AuthError("GitHub OAuth Client ID is required for Device Flow login.")
    data = _post_oauth_form(
        "https://github.com/login/device/code",
        {"client_id": clean_id, "scope": scope},
    )
    if data.get("error"):
        raise AuthError(data.get("error_description") or str(data["error"]))
    return DeviceCodeChallenge(
        device_code=str(data["device_code"]),
        user_code=str(data["user_code"]),
        verification_uri=str(data.get("verification_uri") or "https://github.com/login/device"),
        expires_in=int(data.get("expires_in") or 900),
        interval=int(data.get("interval") or 5),
    )


def poll_device_access_token(
    client_id: str,
    challenge: DeviceCodeChallenge,
    should_cancel: Callable[[], bool] | None = None,
) -> str:
    clean_id = client_id.strip()
    interval = max(2, challenge.interval)
    deadline = time.monotonic() + challenge.expires_in

    while time.monotonic() < deadline:
        if should_cancel and should_cancel():
            raise AuthError("Device Flow sign-in cancelled.")
        time.sleep(interval)
        if should_cancel and should_cancel():
            raise AuthError("Device Flow sign-in cancelled.")

        resp = _post_oauth_form(
            "https://github.com/login/oauth/access_token",
            {
                "client_id": clean_id,
                "device_code": challenge.device_code,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            },
        )
        token = resp.get("access_token")
        if token:
            return str(token)

        err = str(resp.get("error") or "")
        if err == "authorization_pending":
            continue
        if err == "slow_down":
            interval += 5
            continue
        if err in ("expired_token", "access_denied", "incorrect_client_credentials"):
            raise AuthError(resp.get("error_description") or f"GitHub Device Flow error: {err}")
        raise AuthError(resp.get("error_description") or f"Unexpected OAuth response: {resp}")

    raise AuthError("Device Flow code expired before authorization completed.")


def resolve_commit_email(client: GitHubClient, user_obj: dict[str, object]) -> str:
    login = str(user_obj["login"])
    user_id = int(user_obj["id"])  # type: ignore[arg-type]
    noreply = f"{user_id}+{login}@users.noreply.github.com"

    try:
        emails = client.rest("GET", "/user/emails")
        if isinstance(emails, list):
            verified = [e for e in emails if isinstance(e, dict) and e.get("verified")]
            primary_verified = [e for e in verified if e.get("primary")]
            if primary_verified and primary_verified[0].get("email"):
                return str(primary_verified[0]["email"])
            if verified and verified[0].get("email"):
                return str(verified[0]["email"])
    except GitHubApiError:
        pass

    public_email = user_obj.get("email")
    if isinstance(public_email, str) and public_email.strip():
        return public_email.strip()
    return noreply


def authenticate_with_token(token: str, auth_method: str = "pat") -> AccountSession:
    clean = token.strip()
    if not clean:
        raise AuthError("GitHub access token cannot be empty.")
    client = GitHubClient(clean, max_retries=2)
    try:
        user_obj = client.rest("GET", "/user")
    except GitHubApiError as exc:
        raise AuthError(f"Failed to authenticate token with GitHub: {exc}") from exc

    if not isinstance(user_obj, dict) or not user_obj.get("login"):
        raise AuthError("GitHub `/user` response did not include a valid account login.")

    commit_email = resolve_commit_email(client, user_obj)
    return AccountSession(
        login=str(user_obj["login"]),
        user_id=int(user_obj["id"]),
        name=str(user_obj.get("name") or user_obj["login"]),
        commit_email=commit_email,
        token=clean,
        avatar_url=str(user_obj.get("avatar_url") or ""),
        scopes=client.last_scopes,
        auth_method=auth_method,
    )


def import_gh_cli_token() -> str:
    gh_bin = shutil.which("gh")
    if not gh_bin:
        raise AuthError("GitHub CLI (`gh`) is not installed on this machine.")
    res = subprocess.run(
        [gh_bin, "auth", "token"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
    )
    token = (res.stdout or "").strip()
    if res.returncode != 0 or not token:
        detail = (res.stderr or "").strip() or "Run `gh auth login` first or paste a Personal Access Token."
        raise AuthError(f"Could not import token from `gh auth token`: {detail}")
    return token


class CredentialStore:
    """Persists encrypted GitHub account sessions using Windows DPAPI."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (default_app_dir() / "credentials.json")

    def _read_raw(self) -> dict[str, object]:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _write_raw(self, payload: dict[str, object]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def save_session(self, slot: str, session: AccountSession) -> None:
        payload = self._read_raw()
        session_dict = session.to_dict()
        token = str(session_dict.pop("token"))
        try:
            session_dict["encrypted_token"] = protect_secret(token)
        except SecurityError as exc:
            raise AuthError(f"Unable to encrypt token securely: {exc}") from exc
        payload[slot] = session_dict
        self._write_raw(payload)

    def load_session(self, slot: str) -> AccountSession | None:
        payload = self._read_raw()
        entry = payload.get(slot)
        if not isinstance(entry, dict) or not entry.get("encrypted_token"):
            return None
        try:
            token = unprotect_secret(str(entry["encrypted_token"]))
        except SecurityError as exc:
            raise AuthError(f"Unable to decrypt saved token for `{slot}`: {exc}") from exc
        restored = dict(entry)
        restored["token"] = token
        return AccountSession.from_dict(restored)

    def clear_session(self, slot: str) -> None:
        payload = self._read_raw()
        if slot in payload:
            del payload[slot]
            self._write_raw(payload)

    def save_oauth_client_id(self, client_id: str) -> None:
        payload = self._read_raw()
        payload["oauth_client_id"] = client_id.strip()
        self._write_raw(payload)

    def load_oauth_client_id(self) -> str:
        env_id = os.environ.get("GH_OAUTH_CLIENT_ID", "").strip()
        if env_id:
            return env_id
        payload = self._read_raw()
        saved = str(payload.get("oauth_client_id") or "").strip()
        if saved:
            return saved
        return DEFAULT_OAUTH_CLIENT_ID.strip()
