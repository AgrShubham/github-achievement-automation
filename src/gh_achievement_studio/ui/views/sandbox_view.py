"""Sandbox repository management, archive controls, and diagnostics export view."""

from __future__ import annotations

import datetime as dt
import json
from typing import Callable
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..workers import ArchiveRepoWorker, VerifyWorker
from ...core.models import AccountSession, VerificationReport
from ...core.security import redact_secrets
from ...core.state import default_app_dir


class SandboxView(QWidget):
    def __init__(self, logs_provider: Callable[[], list[str]], parent=None) -> None:
        super().__init__(parent)
        self._logs_provider = logs_provider
        self._primary: AccountSession | None = None
        self._secondary: AccountSession | None = None
        self._repo_owner = ""
        self._repo_name = "github-achievements-sandbox"
        self._last_report: VerificationReport | None = None
        self._verify_worker: VerifyWorker | None = None
        self._archive_worker: ArchiveRepoWorker | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 24)
        layout.setSpacing(14)

        title = QLabel("Sandbox & Diagnostics")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)

        card = QFrame()
        card.setObjectName("Card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 16, 18, 16)
        card_layout.setSpacing(10)

        self.repo_status_lbl = QLabel("Connect a GitHub account to inspect your sandbox repository.")
        self.repo_status_lbl.setWordWrap(True)
        card_layout.addWidget(self.repo_status_lbl)

        row1 = QHBoxLayout()
        self.inspect_btn = QPushButton("Inspect Sandbox Status")
        self.inspect_btn.setObjectName("PrimaryBtn")
        self.inspect_btn.setDisabled(True)
        self.inspect_btn.clicked.connect(self.refresh_repo)
        row1.addWidget(self.inspect_btn)

        self.open_repo_btn = QPushButton("Open Repo on GitHub")
        self.open_repo_btn.setDisabled(True)
        self.open_repo_btn.clicked.connect(self._open_repo)
        row1.addWidget(self.open_repo_btn)

        self.archive_btn = QPushButton("Archive Sandbox Repo")
        self.archive_btn.setDisabled(True)
        self.archive_btn.clicked.connect(self._toggle_archive)
        row1.addWidget(self.archive_btn)
        row1.addStretch(1)
        card_layout.addLayout(row1)

        note = QLabel(
            "Tip: Archive (rather than delete) your sandbox repository once all badges appear so it stays read-only "
            "while preserving badge history."
        )
        note.setObjectName("Muted")
        note.setWordWrap(True)
        card_layout.addWidget(note)
        layout.addWidget(card)

        diag_card = QFrame()
        diag_card.setObjectName("Card")
        diag_layout = QVBoxLayout(diag_card)
        diag_layout.setContentsMargins(18, 16, 18, 16)
        diag_layout.setSpacing(10)

        diag_lbl = QLabel(f"Local AppData folder: {default_app_dir()}")
        diag_lbl.setWordWrap(True)
        diag_lbl.setObjectName("Muted")
        diag_layout.addWidget(diag_lbl)

        diag_row = QHBoxLayout()
        self.open_appdata_btn = QPushButton("Open AppData Folder")
        self.open_appdata_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(default_app_dir())))
        )
        diag_row.addWidget(self.open_appdata_btn)

        self.export_btn = QPushButton("Export Redacted Diagnostics (.json)")
        self.export_btn.clicked.connect(self._export_diagnostics)
        diag_row.addWidget(self.export_btn)
        diag_row.addStretch(1)
        diag_layout.addLayout(diag_row)
        layout.addWidget(diag_card)

        layout.addStretch(1)

    def set_context(
        self,
        primary: AccountSession | None,
        secondary: AccountSession | None,
        repo_owner: str,
        repo_name: str,
    ) -> None:
        self._primary = primary
        self._secondary = secondary
        self._repo_owner = repo_owner
        self._repo_name = repo_name
        enabled = primary is not None
        self.inspect_btn.setEnabled(enabled)
        self.open_repo_btn.setEnabled(enabled)
        self.archive_btn.setEnabled(False)
        if primary is not None:
            owner = repo_owner or primary.login
            self.repo_status_lbl.setText(f"Target repository: {owner}/{repo_name} (click 'Inspect Sandbox Status' to check).")
        else:
            self.repo_status_lbl.setText("Connect a GitHub account to inspect your sandbox repository.")

    def refresh_repo(self) -> None:
        if self._primary is None:
            return
        self.inspect_btn.setDisabled(True)
        owner = self._repo_owner or self._primary.login
        self._verify_worker = VerifyWorker(self._primary, owner, self._repo_name)
        self._verify_worker.succeeded.connect(self.apply_report)
        self._verify_worker.failed.connect(self._on_error)
        self._verify_worker.start()

    def apply_report(self, report: VerificationReport) -> None:
        self._last_report = report
        self.inspect_btn.setEnabled(True)
        if report.repo_exists:
            arch = "ARCHIVED (Read-Only)" if report.repo_archived else "ACTIVE"
            self.repo_status_lbl.setText(
                f"Repository: {report.repo_full_name} — Status: {arch}\n"
                f"Merged PRs: {report.repo_merged_prs} (Global: {report.global_merged_prs})  •  "
                f"Quickdraw Issues: {report.quickdraw_issues}  •  Accepted Answers: {report.accepted_answers}"
            )
            self.archive_btn.setEnabled(True)
            self.archive_btn.setText("Unarchive Sandbox Repo" if report.repo_archived else "Archive Sandbox Repo")
        else:
            self.repo_status_lbl.setText(f"Repository `{report.repo_full_name}` has not been created yet.")
            self.archive_btn.setDisabled(True)

    def _toggle_archive(self) -> None:
        if self._primary is None or self._last_report is None or not self._last_report.repo_exists:
            return
        target_archived = not self._last_report.repo_archived
        owner, short_repo = self._last_report.repo_full_name.split("/", 1)
        token = self._primary.token
        if self._secondary is not None and owner.lower() == self._secondary.login.lower():
            token = self._secondary.token

        action = "archive" if target_archived else "unarchive"
        reply = QMessageBox.question(
            self,
            f"Confirm {action.title()}",
            f"Are you sure you want to {action} `{self._last_report.repo_full_name}`?",
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.archive_btn.setDisabled(True)
        self._archive_worker = ArchiveRepoWorker(token, owner, short_repo, target_archived)
        self._archive_worker.succeeded.connect(lambda _arch: self.refresh_repo())
        self._archive_worker.failed.connect(self._on_error)
        self._archive_worker.start()

    def _open_repo(self) -> None:
        if self._primary is None:
            return
        owner = self._repo_owner or self._primary.login
        QDesktopServices.openUrl(QUrl(f"https://github.com/{owner}/{self._repo_name}"))

    def _export_diagnostics(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Diagnostics",
            "gh-achievement-diagnostics.json",
            "JSON Files (*.json)",
        )
        if not path:
            return
        secrets = [
            self._primary.token if self._primary else "",
            self._secondary.token if self._secondary else "",
        ]
        safe_logs = [redact_secrets(line, secrets) for line in self._logs_provider()]
        payload = {
            "exported_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "primary_login": self._primary.login if self._primary else None,
            "secondary_login": self._secondary.login if self._secondary else None,
            "repo_target": f"{self._repo_owner}/{self._repo_name}",
            "last_report": (
                {
                    "repo_exists": self._last_report.repo_exists,
                    "repo_archived": self._last_report.repo_archived,
                    "repo_merged_prs": self._last_report.repo_merged_prs,
                    "global_merged_prs": self._last_report.global_merged_prs,
                    "quickdraw_issues": self._last_report.quickdraw_issues,
                    "visible_badges": list(self._last_report.visible_badges),
                }
                if self._last_report
                else None
            ),
            "logs": safe_logs,
        }
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
        QMessageBox.information(self, "Export Complete", f"Redacted diagnostics saved to:\n{path}")

    def _on_error(self, err: str) -> None:
        self.inspect_btn.setEnabled(self._primary is not None)
        self.archive_btn.setEnabled(self._last_report is not None and self._last_report.repo_exists)
        QMessageBox.warning(self, "Sandbox Action Failed", err)

    def shutdown_workers(self) -> None:
        if self._verify_worker is not None and self._verify_worker.isRunning():
            self._verify_worker.wait(2000)
        if self._archive_worker is not None and self._archive_worker.isRunning():
            self._archive_worker.wait(2000)
