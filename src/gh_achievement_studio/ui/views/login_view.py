"""Account sign-in view (OAuth Device Flow, PAT, and optional gh CLI import)."""

from __future__ import annotations

import shutil
from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..workers import DeviceFlowWorker, TokenAuthWorker
from ...core.auth import AuthError, CredentialStore, DeviceCodeChallenge
from ...core.models import AccountSession


class AccountAuthCard(QGroupBox):
    session_changed = Signal(object)  # AccountSession | None

    def __init__(
        self,
        title: str,
        subtitle: str,
        slot: str,
        cred_store: CredentialStore,
        allow_gh_import: bool = True,
        parent=None,
    ) -> None:
        super().__init__(title, parent)
        self.slot = slot
        self.cred_store = cred_store
        self._session: AccountSession | None = None
        self._worker: TokenAuthWorker | None = None
        self._device_worker: DeviceFlowWorker | None = None

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 20, 16, 16)

        sub = QLabel(subtitle)
        sub.setObjectName("Muted")
        sub.setWordWrap(True)
        layout.addWidget(sub)

        # Connected state banner
        self.connected_box = QFrame()
        self.connected_box.setObjectName("Card")
        conn_layout = QHBoxLayout(self.connected_box)
        conn_layout.setContentsMargins(12, 10, 12, 10)
        self.connected_lbl = QLabel("")
        self.connected_lbl.setWordWrap(True)
        conn_layout.addWidget(self.connected_lbl, 1)
        self.sign_out_btn = QPushButton("Sign Out")
        self.sign_out_btn.clicked.connect(self._sign_out)
        conn_layout.addWidget(self.sign_out_btn)
        layout.addWidget(self.connected_box)
        self.connected_box.hide()

        # Login methods container
        self.login_panel = QWidget()
        login_layout = QVBoxLayout(self.login_panel)
        login_layout.setContentsMargins(0, 0, 0, 0)
        login_layout.setSpacing(10)

        # Row 1: PAT input + quick link + optional gh CLI import
        pat_row = QHBoxLayout()
        self.pat_input = QLineEdit()
        self.pat_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.pat_input.setPlaceholderText("Paste GitHub Personal Access Token (ghp_... or github_pat_...)")
        pat_row.addWidget(self.pat_input, 1)

        self.pat_login_btn = QPushButton("Connect Token")
        self.pat_login_btn.setObjectName("PrimaryBtn")
        self.pat_login_btn.clicked.connect(self._connect_pat)
        pat_row.addWidget(self.pat_login_btn)
        login_layout.addLayout(pat_row)

        quick_row = QHBoxLayout()
        self.create_pat_btn = QPushButton("Create Token on GitHub")
        self.create_pat_btn.clicked.connect(self._open_pat_page)
        quick_row.addWidget(self.create_pat_btn)

        self.gh_import_btn = QPushButton("Import from GitHub CLI (gh)", self.login_panel)
        self.gh_import_btn.clicked.connect(self._import_gh_cli)
        if allow_gh_import and shutil.which("gh"):
            quick_row.addWidget(self.gh_import_btn)
        else:
            self.gh_import_btn.hide()
        quick_row.addStretch(1)
        login_layout.addLayout(quick_row)

        # Row 2: OAuth Device Flow
        oauth_row = QHBoxLayout()
        self.client_id_input = QLineEdit()
        self.client_id_input.setPlaceholderText("OAuth App Client ID (optional, enables 1-click Device Flow)")
        self.client_id_input.setText(self.cred_store.load_oauth_client_id())
        oauth_row.addWidget(self.client_id_input, 1)

        self.device_btn = QPushButton("Sign In via Browser Code")
        self.device_btn.clicked.connect(self._start_device_flow)
        oauth_row.addWidget(self.device_btn)

        self.device_cancel_btn = QPushButton("Cancel")
        self.device_cancel_btn.clicked.connect(self._cancel_device_flow)
        self.device_cancel_btn.hide()
        oauth_row.addWidget(self.device_cancel_btn)
        login_layout.addLayout(oauth_row)

        self.device_status_lbl = QLabel("")
        self.device_status_lbl.setWordWrap(True)
        self.device_status_lbl.setObjectName("Muted")
        self.device_status_lbl.hide()
        login_layout.addWidget(self.device_status_lbl)

        layout.addWidget(self.login_panel)

        self.error_lbl = QLabel("")
        self.error_lbl.setStyleSheet("color: #f85149; font-weight: 600;")
        self.error_lbl.setWordWrap(True)
        self.error_lbl.hide()
        layout.addWidget(self.error_lbl)

    def set_session(self, session: AccountSession | None, persist: bool = True) -> None:
        self._session = session
        self.error_lbl.hide()
        if session is None:
            self.connected_box.hide()
            self.login_panel.show()
            if persist:
                self.cred_store.clear_session(self.slot)
        else:
            scopes_text = ", ".join(session.scopes) if session.scopes else "fine-grained / scoped"
            self.connected_lbl.setText(
                f"Signed in as @{session.login} ({session.name})\n"
                f"Commit email: {session.commit_email}  •  Auth: {session.auth_method}  •  Scopes: {scopes_text}"
            )
            self.connected_box.show()
            self.login_panel.hide()
            self.pat_input.clear()
            if persist:
                self.cred_store.save_session(self.slot, session)
        self.session_changed.emit(session)

    def _set_busy(self, busy: bool) -> None:
        self.pat_login_btn.setDisabled(busy)
        self.gh_import_btn.setDisabled(busy)
        self.device_btn.setDisabled(busy)
        self.pat_input.setDisabled(busy)

    def _show_error(self, message: str) -> None:
        self.error_lbl.setText(message)
        self.error_lbl.show()

    def _open_pat_page(self) -> None:
        url = (
            "https://github.com/settings/tokens/new"
            "?scopes=repo,read:user,user:email,write:discussion"
            "&description=GitHub%20Achievement%20Studio"
        )
        QDesktopServices.openUrl(QUrl(url))

    def _connect_pat(self) -> None:
        token = self.pat_input.text().strip()
        if not token:
            self._show_error("Please paste a GitHub Personal Access Token first.")
            return
        self.error_lbl.hide()
        self._set_busy(True)
        self._worker = TokenAuthWorker(token=token, from_gh_cli=False)
        self._worker.succeeded.connect(self._on_auth_ok)
        self._worker.failed.connect(self._on_auth_fail)
        self._worker.start()

    def _import_gh_cli(self) -> None:
        self.error_lbl.hide()
        self._set_busy(True)
        self._worker = TokenAuthWorker(from_gh_cli=True)
        self._worker.succeeded.connect(self._on_auth_ok)
        self._worker.failed.connect(self._on_auth_fail)
        self._worker.start()

    def _start_device_flow(self) -> None:
        client_id = self.client_id_input.text().strip()
        if not client_id:
            QMessageBox.information(
                self,
                "GitHub OAuth Client ID Needed",
                "Enter an OAuth App Client ID (with Device Flow enabled in GitHub Developer Settings), "
                "or use 'Create Token on GitHub' / 'Import from GitHub CLI' above.",
            )
            return
        self.cred_store.save_oauth_client_id(client_id)
        self.error_lbl.hide()
        self._set_busy(True)
        self.device_cancel_btn.show()
        self.device_status_lbl.setText("Requesting verification code from GitHub...")
        self.device_status_lbl.show()

        self._device_worker = DeviceFlowWorker(client_id)
        self._device_worker.challenge_ready.connect(self._on_device_challenge)
        self._device_worker.succeeded.connect(self._on_device_ok)
        self._device_worker.failed.connect(self._on_device_fail)
        self._device_worker.start()

    def _cancel_device_flow(self) -> None:
        if self._device_worker is not None:
            self._device_worker.cancel()

    def _on_device_challenge(self, challenge: DeviceCodeChallenge) -> None:
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(challenge.user_code)
        self.device_status_lbl.setText(
            f"Code copied to clipboard: {challenge.user_code}\n"
            f"Approve access at {challenge.verification_uri} — waiting for GitHub confirmation..."
        )
        QDesktopServices.openUrl(QUrl(challenge.verification_uri))

    def _on_device_ok(self, session: AccountSession) -> None:
        self._set_busy(False)
        self.device_cancel_btn.hide()
        self.device_status_lbl.hide()
        self.set_session(session, persist=True)

    def _on_device_fail(self, message: str) -> None:
        self._set_busy(False)
        self.device_cancel_btn.hide()
        self.device_status_lbl.hide()
        self._show_error(message)

    def _on_auth_ok(self, session: AccountSession) -> None:
        self._set_busy(False)
        self.set_session(session, persist=True)

    def _on_auth_fail(self, message: str) -> None:
        self._set_busy(False)
        self._show_error(message)

    def _sign_out(self) -> None:
        self.set_session(None, persist=True)

    def shutdown_workers(self) -> None:
        if self._device_worker is not None and self._device_worker.isRunning():
            self._device_worker.cancel()
            self._device_worker.wait(2000)
        if self._worker is not None and self._worker.isRunning():
            self._worker.wait(2000)


class LoginView(QWidget):
    accounts_updated = Signal(object, object)  # primary, secondary

    def __init__(self, cred_store: CredentialStore, parent=None) -> None:
        super().__init__(parent)
        self.cred_store = cred_store
        self.primary_session: AccountSession | None = None
        self.secondary_session: AccountSession | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        content.setObjectName("ScrollContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 20, 24, 24)
        layout.setSpacing(16)

        title = QLabel("GitHub Account Connections")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)

        desc = QLabel(
            "Tokens are encrypted per-user in Windows DPAPI (%LOCALAPPDATA%) and never stored in plaintext. "
            "Required scopes: repo, read:user, user:email, and write:discussion (for Galaxy Brain)."
        )
        desc.setObjectName("Muted")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        self.primary_card = AccountAuthCard(
            title="Primary Account (Required)",
            subtitle="The GitHub profile where achievements will be unlocked and verified.",
            slot="primary",
            cred_store=self.cred_store,
            allow_gh_import=True,
        )
        self.primary_card.session_changed.connect(self._on_primary_changed)
        layout.addWidget(self.primary_card)

        self.secondary_card = AccountAuthCard(
            title="Secondary / Partner Account (Optional)",
            subtitle=(
                "Enables Pair Extraordinaire, Galaxy Brain (accepted answers), strict YOLO reviewer requests, "
                "and Cross-Owner Pull Shark mode. Must be a different GitHub account from Primary."
            ),
            slot="secondary",
            cred_store=self.cred_store,
            allow_gh_import=False,
        )
        self.secondary_card.session_changed.connect(self._on_secondary_changed)
        layout.addWidget(self.secondary_card)

        self.same_account_warn = QLabel("")
        self.same_account_warn.setStyleSheet("color: #d29922; font-weight: 600;")
        self.same_account_warn.setWordWrap(True)
        self.same_account_warn.hide()
        layout.addWidget(self.same_account_warn)

        layout.addStretch(1)
        scroll.setWidget(content)
        outer.addWidget(scroll)

    def restore_saved_sessions(self) -> None:
        try:
            primary = self.cred_store.load_session("primary")
            if primary is not None:
                self.primary_card.set_session(primary, persist=False)
        except AuthError as exc:
            self.primary_card._show_error(f"Saved primary session could not be restored: {exc}")
        try:
            secondary = self.cred_store.load_session("secondary")
            if secondary is not None:
                self.secondary_card.set_session(secondary, persist=False)
        except AuthError as exc:
            self.secondary_card._show_error(f"Saved secondary session could not be restored: {exc}")

    def _on_primary_changed(self, session: AccountSession | None) -> None:
        self.primary_session = session
        self._check_distinct_accounts()
        self.accounts_updated.emit(self.primary_session, self.secondary_session)

    def _on_secondary_changed(self, session: AccountSession | None) -> None:
        self.secondary_session = session
        self._check_distinct_accounts()
        self.accounts_updated.emit(self.primary_session, self.secondary_session)

    def _check_distinct_accounts(self) -> None:
        if (
            self.primary_session is not None
            and self.secondary_session is not None
            and self.primary_session.login.lower() == self.secondary_session.login.lower()
        ):
            self.same_account_warn.setText(
                f"Warning: Secondary account @{self.secondary_session.login} is the same as Primary. "
                "Galaxy Brain and Cross-Owner Pull Shark require a different GitHub account."
            )
            self.same_account_warn.show()
        else:
            self.same_account_warn.hide()

    def shutdown_workers(self) -> None:
        self.primary_card.shutdown_workers()
        self.secondary_card.shutdown_workers()
