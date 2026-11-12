"""Dashboard view showing live profile status and categorized achievement cards."""

from __future__ import annotations

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..widgets.badge_card import BadgeCard
from ..workers import VerifyWorker
from ...core.models import BADGE_CATALOG, AccountSession, BadgeCategory, VerificationReport


class DashboardView(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._primary: AccountSession | None = None
        self._repo_owner = ""
        self._repo_name = "github-achievements-sandbox"
        self._verify_worker: VerifyWorker | None = None
        self._cards: dict[str, BadgeCard] = {}

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

        # Header row
        header = QHBoxLayout()
        header.setSpacing(8)
        title_box = QVBoxLayout()
        title = QLabel("Achievements Dashboard")
        title.setObjectName("SectionTitle")
        title_box.addWidget(title)
        self.subtitle_lbl = QLabel("Connect your primary GitHub account to inspect unlocked badges and sandbox stats.")
        self.subtitle_lbl.setObjectName("Muted")
        self.subtitle_lbl.setWordWrap(True)
        title_box.addWidget(self.subtitle_lbl)
        header.addLayout(title_box, 1)

        self.open_profile_btn = QPushButton("Open Profile")
        self.open_profile_btn.setDisabled(True)
        self.open_profile_btn.clicked.connect(self._open_profile)
        header.addWidget(self.open_profile_btn)

        self.dev_program_btn = QPushButton("Developer Program")
        self.dev_program_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://github.com/settings/developers"))
        )
        header.addWidget(self.dev_program_btn)

        self.refresh_btn = QPushButton("Refresh Live Status")
        self.refresh_btn.setObjectName("PrimaryBtn")
        self.refresh_btn.setDisabled(True)
        self.refresh_btn.clicked.connect(self.refresh_status)
        header.addWidget(self.refresh_btn)
        layout.addLayout(header)

        # Metrics summary bar
        self.metrics_card = QFrame()
        self.metrics_card.setObjectName("Card")
        metrics_row = QHBoxLayout(self.metrics_card)
        metrics_row.setContentsMargins(16, 12, 16, 12)
        metrics_row.setSpacing(24)

        self.metric_labels: dict[str, QLabel] = {}
        for key, label in (
            ("repo_prs", "Repo Merged PRs"),
            ("global_prs", "Global Merged PRs"),
            ("quickdraw", "Quickdraw Issues"),
            ("coauthored", "Co-authored PRs"),
            ("accepted", "Accepted Answers"),
            ("quota", "API Quota"),
        ):
            box = QVBoxLayout()
            val = QLabel("—")
            val.setStyleSheet("font-size: 18px; font-weight: 700;")
            cap = QLabel(label)
            cap.setObjectName("Muted")
            box.addWidget(val)
            box.addWidget(cap)
            metrics_row.addLayout(box)
            self.metric_labels[key] = val
        metrics_row.addStretch(1)
        layout.addWidget(self.metrics_card)

        self.status_banner = QLabel("")
        self.status_banner.setWordWrap(True)
        self.status_banner.hide()
        layout.addWidget(self.status_banner)

        # Categorized badge grids
        sections = (
            ("Automatable (Single Account)", BadgeCategory.AUTO_SINGLE),
            ("Automatable (Requires 2nd Account)", BadgeCategory.AUTO_DUAL),
            ("Manual & Program Highlights", BadgeCategory.MANUAL),
            ("Unavailable (Retired, Disabled, or Staff Only)", BadgeCategory.UNAVAILABLE),
        )
        for heading, category in sections:
            sec_lbl = QLabel(heading)
            sec_lbl.setStyleSheet("font-size: 15px; font-weight: 700; margin-top: 6px;")
            layout.addWidget(sec_lbl)

            grid = QGridLayout()
            grid.setSpacing(12)
            grid.setColumnStretch(0, 1)
            grid.setColumnStretch(1, 1)
            items = [item for item in BADGE_CATALOG if item.category == category]
            for idx, item in enumerate(items):
                card = BadgeCard(item)
                self._cards[item.key] = card
                grid.addWidget(card, idx // 2, idx % 2)
            layout.addLayout(grid)

        layout.addStretch(1)
        scroll.setWidget(content)
        outer.addWidget(scroll)

    def set_context(self, primary: AccountSession | None, repo_owner: str, repo_name: str) -> None:
        self._primary = primary
        self._repo_owner = repo_owner
        self._repo_name = repo_name
        enabled = primary is not None
        self.refresh_btn.setEnabled(enabled)
        self.open_profile_btn.setEnabled(enabled)
        if primary is not None:
            self.subtitle_lbl.setText(
                f"Signed in as @{primary.login} • Target sandbox: {repo_owner}/{repo_name}"
            )
        else:
            self.subtitle_lbl.setText("Connect your primary GitHub account to inspect unlocked badges and sandbox stats.")
            for val in self.metric_labels.values():
                val.setText("—")
            self.status_banner.hide()
            for card in self._cards.values():
                card.set_earned_state(None)

    def refresh_status(self) -> None:
        if self._primary is None:
            return
        if self._verify_worker is not None and self._verify_worker.isRunning():
            return
        self.refresh_btn.setDisabled(True)
        self.refresh_btn.setText("Refreshing...")
        self.status_banner.hide()

        owner = self._repo_owner or self._primary.login
        self._verify_worker = VerifyWorker(self._primary, owner, self._repo_name)
        self._verify_worker.succeeded.connect(self.apply_verification_report)
        self._verify_worker.failed.connect(self._on_verify_failed)
        self._verify_worker.start()

    def apply_verification_report(self, report: VerificationReport) -> None:
        self.refresh_btn.setEnabled(True)
        self.refresh_btn.setText("Refresh Live Status")

        self.metric_labels["repo_prs"].setText(str(report.repo_merged_prs))
        self.metric_labels["global_prs"].setText(str(report.global_merged_prs))
        self.metric_labels["quickdraw"].setText(str(report.quickdraw_issues))
        self.metric_labels["coauthored"].setText(str(report.coauthored_prs))
        self.metric_labels["accepted"].setText(str(report.accepted_answers))
        self.metric_labels["quota"].setText(f"{report.rate_limit_remaining}/{report.rate_limit_limit}")

        lowered_badges = {b.lower(): b for b in report.visible_badges}
        for key, card in self._cards.items():
            matched = None
            for b_low, b_orig in lowered_badges.items():
                if card.item.name.lower() in b_low:
                    matched = b_orig
                    break
            card.set_earned_state(matched)

        if report.visible_badges:
            self.status_banner.setStyleSheet("color: #3fb950; font-weight: 600;")
            self.status_banner.setText(
                f"Live badges visible on github.com/{report.actor}?tab=achievements: {', '.join(report.visible_badges)}"
            )
        else:
            self.status_banner.setStyleSheet("color: #d29922; font-weight: 600;")
            self.status_banner.setText(
                "No public badges scraped yet. GitHub updates some badges (like Pull Shark) asynchronously over hours to 24–48h."
            )
        self.status_banner.show()

    def _on_verify_failed(self, err: str) -> None:
        self.refresh_btn.setEnabled(True)
        self.refresh_btn.setText("Refresh Live Status")
        self.status_banner.setStyleSheet("color: #f85149; font-weight: 600;")
        self.status_banner.setText(f"Status refresh failed: {err}")
        self.status_banner.show()

    def _open_profile(self) -> None:
        if self._primary is not None:
            QDesktopServices.openUrl(QUrl(f"https://github.com/{self._primary.login}?tab=achievements"))

    def shutdown_workers(self) -> None:
        if self._verify_worker is not None and self._verify_worker.isRunning():
            self._verify_worker.wait(2000)
