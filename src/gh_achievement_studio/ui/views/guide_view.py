"""Overview and interactive getting-started guide view for new users."""

from __future__ import annotations

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ...core.models import AccountSession


class GuideView(QWidget):
    """Explains architecture, workflow steps, badge rules, and safety controls."""

    navigate_requested = Signal(int)

    def __init__(
        self,
        page_dashboard: int = 0,
        page_runner: int = 1,
        page_accounts: int = 2,
        page_sandbox: int = 3,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._page_dashboard = page_dashboard
        self._page_runner = page_runner
        self._page_accounts = page_accounts
        self._page_sandbox = page_sandbox

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

        # Header
        header = QHBoxLayout()
        header.setSpacing(10)
        title_box = QVBoxLayout()
        title = QLabel("Overview & User Guide")
        title.setObjectName("SectionTitle")
        title_box.addWidget(title)

        subtitle = QLabel(
            "Learn how GitHub Achievement Studio unlocks, tracks, and verifies earnable GitHub profile badges "
            "safely without local git, GitHub CLI, or Python prerequisites."
        )
        subtitle.setObjectName("Muted")
        subtitle.setWordWrap(True)
        title_box.addWidget(subtitle)
        header.addLayout(title_box, 1)

        self.profile_settings_btn = QPushButton("GitHub Profile Settings")
        self.profile_settings_btn.setToolTip(
            "Ensure 'Show Achievements on my profile' is enabled at github.com/settings/profile."
        )
        self.profile_settings_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://github.com/settings/profile"))
        )
        header.addWidget(self.profile_settings_btn)

        self.get_started_btn = QPushButton("Connect Account")
        self.get_started_btn.setObjectName("PrimaryBtn")
        self.get_started_btn.clicked.connect(lambda: self.navigate_requested.emit(self._page_accounts))
        header.addWidget(self.get_started_btn)
        layout.addLayout(header)

        # Section 1: Architecture & Safety Highlights (3 cards)
        pillars_heading = QLabel("How This Application Works")
        pillars_heading.setStyleSheet("font-size: 15px; font-weight: 700; margin-top: 4px;")
        layout.addWidget(pillars_heading)

        pillars_row = QHBoxLayout()
        pillars_row.setSpacing(12)
        for heading, pill_text, pill_color, body in (
            (
                "Gitless HTTPS Engine",
                "Zero CLI",
                "#1f6feb",
                "Uses GitHub's Git Data REST API (blobs, trees, commits, refs, PRs) and GraphQL directly over HTTPS. "
                "No local git binary, gh CLI, or cloned folders are required.",
            ),
            (
                "Windows DPAPI Security",
                "Encrypted",
                "#238636",
                "Account tokens are encrypted per Windows user profile in %LOCALAPPDATA%\\GitHubAchievementStudio "
                "and automatically redacted from live logs and exported diagnostics.",
            ),
            (
                "Safe Sandbox & Pacing",
                "Idempotent",
                "#6e40c9",
                "Operations run strictly inside your own dedicated sandbox repo. Re-runs measure existing merged PRs "
                "first and create only the remaining delta with rate-limit backoff.",
            ),
        ):
            pillars_row.addWidget(self._make_info_card(heading, pill_text, pill_color, body), 1)
        layout.addLayout(pillars_row)

        # Section 2: Step-by-Step Workflow (2x2 grid with live Step 1 badge + navigation buttons)
        steps_heading = QLabel("Quick-Start Workflow (4 Steps)")
        steps_heading.setStyleSheet("font-size: 15px; font-weight: 700; margin-top: 4px;")
        layout.addWidget(steps_heading)

        steps_grid = QGridLayout()
        steps_grid.setSpacing(12)
        steps_grid.setColumnStretch(0, 1)
        steps_grid.setColumnStretch(1, 1)

        step1_card, self.step1_status_pill, self.step1_status_note, self.step1_nav_btn = self._make_step_card(
            step_num="Step 1",
            title="Connect GitHub Account(s)",
            pill_text="Not Connected",
            pill_color="#9e6a03",
            body=(
                "Sign in with your Primary GitHub account using a Personal Access Token (PAT), OAuth Browser Code, "
                "or existing gh CLI session. Optionally connect a distinct 2nd account to unlock multi-account badges "
                "and Cross-Owner Mode."
            ),
            footer_hint="Connect a Primary account to unlock the Runner",
            btn_label="Open Accounts",
            target_page=self._page_accounts,
        )
        steps_grid.addWidget(step1_card, 0, 0)

        step2_card, _, _, self.step2_nav_btn = self._make_step_card(
            step_num="Step 2",
            title="Preview Plan & Run Automation",
            pill_text="Dry-Run Ready",
            pill_color="#1f6feb",
            body=(
                "Choose target badges and tiers (e.g., Quickdraw, YOLO, Pull Shark Bronze = 16 PRs). "
                "Click 'Preview Plan & Start' to review exact API counts and warnings before any mutation, "
                "then monitor progress with Pause, Resume, or Cancel."
            ),
            footer_hint="Supports Dry-Run Preview, Pause, Resume & Cancel",
            btn_label="Open Runner",
            target_page=self._page_runner,
        )
        steps_grid.addWidget(step2_card, 0, 1)

        step3_card, _, _, self.step3_nav_btn = self._make_step_card(
            step_num="Step 3",
            title="Verify Stats & Live Profile Badges",
            pill_text="Verification",
            pill_color="#238636",
            body=(
                "Check Repo Merged PRs, Global Merged PRs, Quickdraw closures (< 300s), Co-authored PRs, "
                "Accepted Answers, and remaining API quota. Note: badges like Pull Shark are indexed "
                "asynchronously by GitHub (minutes up to 24–48 hours)."
            ),
            footer_hint="Inspects live GitHub profile & remaining API quota",
            btn_label="Open Dashboard",
            target_page=self._page_dashboard,
        )
        steps_grid.addWidget(step3_card, 1, 0)

        step4_card, _, _, self.step4_nav_btn = self._make_step_card(
            step_num="Step 4",
            title="Archive Sandbox When Complete",
            pill_text="Cleanup",
            pill_color="#6e40c9",
            body=(
                "Once your badges appear on github.com/<username>?tab=achievements, use 'Archive Sandbox Repo' "
                "to lock the repository read-only while preserving merged PRs and badge links. "
                "(Avoid deleting the repo if you want badge evidence retained.)"
            ),
            footer_hint="Locks repo read-only while keeping badge history",
            btn_label="Open Sandbox && Logs",
            target_page=self._page_sandbox,
        )
        steps_grid.addWidget(step4_card, 1, 1)
        layout.addLayout(steps_grid)

        # Section 3: Badge Playbook & Rules
        rules_heading = QLabel("Achievement Rules & Multi-Account Guide")
        rules_heading.setStyleSheet("font-size: 15px; font-weight: 700; margin-top: 4px;")
        layout.addWidget(rules_heading)

        rules_grid = QGridLayout()
        rules_grid.setSpacing(12)
        rules_grid.setColumnStretch(0, 1)
        rules_grid.setColumnStretch(1, 1)

        rules_grid.addWidget(
            self._make_info_card(
                "Single-Account Badges",
                "Solo Mode",
                "#1f6feb",
                "• Quickdraw: Opens and closes an issue within seconds (< 300s required).\n"
                "• YOLO: Merges a PR without review approval (Strict YOLO requests a 2nd reviewer first).\n"
                "• Pull Shark: Merges 2 / 16 / 128 / 1,024 PRs into the default branch of a public repo.",
            ),
            0,
            0,
        )
        rules_grid.addWidget(
            self._make_info_card(
                "Two-Account & Cross-Owner Mode",
                "2 Accounts",
                "#6e40c9",
                "• Cross-Owner Mode: 2nd account owns the sandbox repo and merges PRs opened by Primary — "
                "useful if GitHub delays self-merged solo PRs.\n"
                "• Pair Extraordinaire: Adds a verified/noreply Co-authored-by trailer using merge commits.\n"
                "• Galaxy Brain: 2nd account opens Q&A Discussions and marks Primary's reply as Accepted.",
            ),
            0,
            1,
        )
        layout.addLayout(rules_grid)

        # Section 4: Safety & Troubleshooting Tips
        tips_card = QFrame()
        tips_card.setObjectName("Card")
        tips_layout = QVBoxLayout(tips_card)
        tips_layout.setContentsMargins(16, 14, 16, 14)
        tips_layout.setSpacing(6)

        tips_title = QLabel("Best Practices & Troubleshooting")
        tips_title.setStyleSheet("font-size: 14px; font-weight: 700; background-color: transparent;")
        tips_layout.addWidget(tips_title)

        tips_body = QLabel(
            "1. Keep visibility set to 'public': private repositories rarely trigger profile achievements.\n"
            "2. Scaling to Silver (128) or Gold (1,024): keep Max PRs Per Burst at 50 and Delay >= 2.5s; "
            "re-running later automatically resumes from your live merged PR count.\n"
            "3. Required PAT scopes: repo, read:user, user:email, plus write:discussion for Galaxy Brain.\n"
            "4. Badges missing on your profile? Open GitHub Profile Settings and verify "
            "'Show Achievements on my profile' is checked, then wait up to 24–48h for Pull Shark indexing."
        )
        tips_body.setObjectName("Muted")
        tips_body.setWordWrap(True)
        tips_layout.addWidget(tips_body)
        layout.addWidget(tips_card)

        layout.addStretch(1)
        scroll.setWidget(content)
        outer.addWidget(scroll)

    def _make_pill(self, text: str, color_hex: str) -> QLabel:
        pill = QLabel(text)
        pill.setObjectName("StatusPill")
        pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pill.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        pill.setStyleSheet(
            f"background-color: {color_hex}; color: #ffffff; border-radius: 10px; "
            "padding: 2px 9px; font-size: 11px; font-weight: 700;"
        )
        return pill

    def _make_info_card(self, title: str, pill_text: str, pill_color: str, body: str) -> QFrame:
        card = QFrame()
        card.setObjectName("Card")
        card.setMinimumWidth(0)
        card.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        vbox = QVBoxLayout(card)
        vbox.setContentsMargins(14, 12, 14, 12)
        vbox.setSpacing(6)

        head = QHBoxLayout()
        head.setSpacing(8)
        t_lbl = QLabel(title)
        t_lbl.setStyleSheet("font-size: 14px; font-weight: 700; background-color: transparent;")
        t_lbl.setWordWrap(True)
        head.addWidget(t_lbl, 1, Qt.AlignmentFlag.AlignTop)
        head.addWidget(self._make_pill(pill_text, pill_color), 0, Qt.AlignmentFlag.AlignTop)
        vbox.addLayout(head)

        b_lbl = QLabel(body)
        b_lbl.setObjectName("Muted")
        b_lbl.setWordWrap(True)
        b_lbl.setMinimumWidth(0)
        vbox.addWidget(b_lbl)
        vbox.addStretch(1)
        return card

    def _make_step_card(
        self,
        step_num: str,
        title: str,
        pill_text: str,
        pill_color: str,
        body: str,
        footer_hint: str,
        btn_label: str,
        target_page: int,
    ) -> tuple[QFrame, QLabel, QLabel, QPushButton]:
        card = QFrame()
        card.setObjectName("Card")
        card.setMinimumWidth(0)
        card.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        vbox = QVBoxLayout(card)
        vbox.setContentsMargins(14, 12, 14, 12)
        vbox.setSpacing(8)

        head = QHBoxLayout()
        head.setSpacing(8)
        t_lbl = QLabel(f"{step_num}: {title}")
        t_lbl.setStyleSheet("font-size: 14px; font-weight: 700; background-color: transparent;")
        t_lbl.setWordWrap(True)
        head.addWidget(t_lbl, 1, Qt.AlignmentFlag.AlignTop)

        pill = self._make_pill(pill_text, pill_color)
        head.addWidget(pill, 0, Qt.AlignmentFlag.AlignTop)
        vbox.addLayout(head)

        b_lbl = QLabel(body)
        b_lbl.setObjectName("Muted")
        b_lbl.setWordWrap(True)
        b_lbl.setMinimumWidth(0)
        vbox.addWidget(b_lbl, 1)

        footer = QHBoxLayout()
        footer.setSpacing(10)
        status_note = QLabel(footer_hint)
        status_note.setObjectName("Muted")
        status_note.setWordWrap(True)
        status_note.setStyleSheet("font-size: 11.5px; background-color: transparent;")
        footer.addWidget(status_note, 1)

        nav_btn = QPushButton(btn_label)
        nav_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        nav_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        nav_btn.clicked.connect(lambda _checked=False, page=target_page: self.navigate_requested.emit(page))
        footer.addWidget(nav_btn)
        vbox.addLayout(footer)

        return card, pill, status_note, nav_btn

    def update_account_status(
        self,
        primary: AccountSession | None,
        secondary: AccountSession | None,
    ) -> None:
        if primary is None:
            self.step1_status_pill.setText("Not Connected")
            self.step1_status_pill.setStyleSheet(
                "background-color: #9e6a03; color: #ffffff; border-radius: 10px; "
                "padding: 2px 9px; font-size: 11px; font-weight: 700;"
            )
            self.step1_status_note.setText("Connect a Primary account to unlock the Runner")
            self.get_started_btn.setText("Connect Account")
            return

        if secondary is not None and secondary.login.lower() != primary.login.lower():
            self.step1_status_pill.setText("Dual Connected")
            self.step1_status_note.setText(f"Primary: @{primary.login}  •  Partner: @{secondary.login}")
        else:
            self.step1_status_pill.setText("Primary Connected")
            self.step1_status_note.setText(f"Signed in as @{primary.login}")
        self.step1_status_pill.setStyleSheet(
            "background-color: #238636; color: #ffffff; border-radius: 10px; "
            "padding: 2px 9px; font-size: 11px; font-weight: 700;"
        )
        self.get_started_btn.setText("Manage Accounts")
