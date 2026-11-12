"""QThread background workers keeping the PySide6 UI responsive."""

from __future__ import annotations

import threading
from PySide6.QtCore import QThread, Signal

from ..core.auth import (
    DeviceCodeChallenge,
    authenticate_with_token,
    import_gh_cli_token,
    poll_device_access_token,
    request_device_code,
)
from ..core.github_client import GitHubClient
from ..core.models import AccountSession, PlanPreview, ProgressEvent, RunConfig, VerificationReport
from ..core.runners import AchievementEngine, build_execution_plan
from ..core.security import redact_secrets
from ..core.state import StateStore
from ..core.verifier import set_repository_archived, verify_account_achievements


class TokenAuthWorker(QThread):
    succeeded = Signal(object)  # AccountSession
    failed = Signal(str)

    def __init__(self, token: str | None = None, from_gh_cli: bool = False) -> None:
        super().__init__()
        self._token = token or ""
        self._from_gh_cli = from_gh_cli

    def run(self) -> None:
        try:
            raw_token = import_gh_cli_token() if self._from_gh_cli else self._token
            method = "gh_cli" if self._from_gh_cli else "pat"
            session = authenticate_with_token(raw_token, auth_method=method)
            self.succeeded.emit(session)
        except Exception as exc:
            self.failed.emit(redact_secrets(str(exc), [self._token]))


class DeviceFlowWorker(QThread):
    challenge_ready = Signal(object)  # DeviceCodeChallenge
    succeeded = Signal(object)  # AccountSession
    failed = Signal(str)

    def __init__(self, client_id: str) -> None:
        super().__init__()
        self._client_id = client_id
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    def run(self) -> None:
        try:
            challenge: DeviceCodeChallenge = request_device_code(self._client_id)
            self.challenge_ready.emit(challenge)
            token = poll_device_access_token(
                self._client_id,
                challenge,
                should_cancel=self._cancel.is_set,
            )
            session = authenticate_with_token(token, auth_method="oauth_device")
            self.succeeded.emit(session)
        except Exception as exc:
            self.failed.emit(str(exc))


class VerifyWorker(QThread):
    succeeded = Signal(object)  # VerificationReport
    failed = Signal(str)

    def __init__(
        self,
        primary: AccountSession,
        repo_owner: str,
        repo_name: str,
        coauthor_email: str | None = None,
    ) -> None:
        super().__init__()
        self._primary = primary
        self._repo_owner = repo_owner
        self._repo_name = repo_name
        self._coauthor_email = coauthor_email

    def run(self) -> None:
        try:
            client = GitHubClient(self._primary.token)
            report = verify_account_achievements(
                client,
                self._primary,
                self._repo_owner,
                self._repo_name,
                coauthor_email=self._coauthor_email,
            )
            self.succeeded.emit(report)
        except Exception as exc:
            self.failed.emit(redact_secrets(str(exc), [self._primary.token]))


class PlanPreviewWorker(QThread):
    succeeded = Signal(object)  # PlanPreview
    failed = Signal(str)

    def __init__(
        self,
        primary: AccountSession,
        secondary: AccountSession | None,
        config: RunConfig,
    ) -> None:
        super().__init__()
        self._primary = primary
        self._secondary = secondary
        self._config = config

    def run(self) -> None:
        try:
            client = GitHubClient(self._primary.token)
            preview = build_execution_plan(self._primary, client, self._secondary, self._config)
            self.succeeded.emit(preview)
        except Exception as exc:
            secrets = [self._primary.token, self._secondary.token if self._secondary else ""]
            self.failed.emit(redact_secrets(str(exc), secrets))


class ExecutionWorker(QThread):
    event_emitted = Signal(object)  # ProgressEvent
    succeeded = Signal(object)  # PlanPreview
    failed = Signal(str)

    def __init__(
        self,
        primary: AccountSession,
        secondary: AccountSession | None,
        config: RunConfig,
        state_store: StateStore,
    ) -> None:
        super().__init__()
        self._primary = primary
        self._secondary = secondary
        self._config = config
        self._state_store = state_store
        self.cancel_event = threading.Event()
        self.pause_event = threading.Event()

    def pause(self) -> None:
        self.pause_event.set()

    def resume(self) -> None:
        self.pause_event.clear()

    def cancel(self) -> None:
        self.cancel_event.set()

    def run(self) -> None:
        secrets = [self._primary.token, self._secondary.token if self._secondary else ""]

        def forward(evt: ProgressEvent) -> None:
            safe_msg = redact_secrets(evt.message, secrets)
            self.event_emitted.emit(
                ProgressEvent(
                    kind=evt.kind,
                    message=safe_msg,
                    level=evt.level,
                    current=evt.current,
                    total=evt.total,
                    stage=evt.stage,
                )
            )

        try:
            engine = AchievementEngine(
                primary=self._primary,
                secondary=self._secondary,
                config=self._config,
                state_store=self._state_store,
                on_event=forward,
                cancel_event=self.cancel_event,
                pause_event=self.pause_event,
            )
            plan = engine.execute()
            self.succeeded.emit(plan)
        except Exception as exc:
            self.failed.emit(redact_secrets(str(exc), secrets))


class ArchiveRepoWorker(QThread):
    succeeded = Signal(bool)
    failed = Signal(str)

    def __init__(self, token: str, owner: str, repo: str, archived: bool) -> None:
        super().__init__()
        self._token = token
        self._owner = owner
        self._repo = repo
        self._archived = archived

    def run(self) -> None:
        try:
            client = GitHubClient(self._token)
            res = set_repository_archived(client, self._owner, self._repo, self._archived)
            self.succeeded.emit(bool(res.get("archived", self._archived)))
        except Exception as exc:
            self.failed.emit(redact_secrets(str(exc), [self._token]))
