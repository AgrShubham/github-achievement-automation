"""Main application window with sidebar navigation, status bar, and theme switcher."""

from __future__ import annotations

from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from .. import __version__
from ..core.auth import CredentialStore
from ..core.models import AccountSession
from ..core.state import StateStore
from .theme import DARK_QSS, LIGHT_QSS
from .views.dashboard_view import DashboardView
from .views.guide_view import GuideView
from .views.login_view import LoginView
from .views.runner_view import RunnerView
from .views.sandbox_view import SandboxView


class MainWindow(QMainWindow):
    """Primary desktop window coordinating Overview, Accounts, Dashboard, Runner, and Sandbox views."""

    PAGE_DASHBOARD = 0
    PAGE_RUNNER = 1
    PAGE_ACCOUNTS = 2
    PAGE_SANDBOX = 3
    PAGE_GUIDE = 4

    def __init__(
        self,
        state_store: StateStore | None = None,
        cred_store: CredentialStore | None = None,
        icon_path: Path | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.state_store = state_store or StateStore()
        self.cred_store = cred_store or CredentialStore()
        self._primary: AccountSession | None = None
        self._secondary: AccountSession | None = None
        self._theme = str(self.state_store.load().get("theme") or "dark")
        if self._theme not in ("dark", "light"):
            self._theme = "dark"

        self.setWindowTitle("GitHub Achievement Studio")
        self.setMinimumSize(1040, 700)
        self.resize(1180, 760)
        if icon_path and icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Sidebar
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(232)
        sb_layout = QVBoxLayout(sidebar)
        sb_layout.setContentsMargins(14, 18, 14, 16)
        sb_layout.setSpacing(8)

        brand = QLabel("GitHub Achievement\nStudio")
        brand.setStyleSheet("font-size: 16px; font-weight: 700;")
        sb_layout.addWidget(brand)

        ver_lbl = QLabel(f"v{__version__} • Gitless Engine")
        ver_lbl.setObjectName("Muted")
        sb_layout.addWidget(ver_lbl)
        sb_layout.addSpacing(10)

        self._nav_buttons: dict[int, QPushButton] = {}
        nav_items = (
            ("Overview && Guide", self.PAGE_GUIDE),
            ("Dashboard", self.PAGE_DASHBOARD),
            ("Automation Runner", self.PAGE_RUNNER),
            ("Accounts", self.PAGE_ACCOUNTS),
            ("Sandbox && Logs", self.PAGE_SANDBOX),
        )
        for label, page_idx in nav_items:
            btn = QPushButton(label)
            btn.setObjectName("NavBtn")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _checked=False, idx=page_idx: self.switch_page(idx))
            sb_layout.addWidget(btn)
            self._nav_buttons[page_idx] = btn

        sb_layout.addStretch(1)

        # Sidebar account status summary card
        self.sidebar_status_card = QFrame()
        self.sidebar_status_card.setObjectName("Card")
        sc_layout = QVBoxLayout(self.sidebar_status_card)
        sc_layout.setContentsMargins(12, 10, 12, 10)
        sc_layout.setSpacing(6)
        self.sidebar_acct_lbl = QLabel("Not signed in\nOpen Accounts to connect.")
        self.sidebar_acct_lbl.setObjectName("Muted")
        self.sidebar_acct_lbl.setWordWrap(True)
        sc_layout.addWidget(self.sidebar_acct_lbl)
        sb_layout.addWidget(self.sidebar_status_card)

        self.theme_btn = QPushButton("")
        self.theme_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.theme_btn.clicked.connect(self.toggle_theme)
        sb_layout.addWidget(self.theme_btn)

        root.addWidget(sidebar)

        # Main stacked pages
        self.stack = QStackedWidget()
        self.dashboard_view = DashboardView()
        self.runner_view = RunnerView(self.state_store)
        self.login_view = LoginView(self.cred_store)
        self.sandbox_view = SandboxView(logs_provider=self.runner_view.get_logs_snapshot)
        self.guide_view = GuideView(
            page_dashboard=self.PAGE_DASHBOARD,
            page_runner=self.PAGE_RUNNER,
            page_accounts=self.PAGE_ACCOUNTS,
            page_sandbox=self.PAGE_SANDBOX,
        )

        self.stack.addWidget(self.dashboard_view)  # 0
        self.stack.addWidget(self.runner_view)     # 1
        self.stack.addWidget(self.login_view)      # 2
        self.stack.addWidget(self.sandbox_view)    # 3
        self.stack.addWidget(self.guide_view)      # 4
        root.addWidget(self.stack, 1)

        self.setCentralWidget(central)

        # Status bar
        status_bar = QStatusBar()
        self.setStatusBar(status_bar)
        self.status_bar_lbl = QLabel("Ready — Connect a GitHub account to start.")
        status_bar.addWidget(self.status_bar_lbl, 1)

        # Cross-view signal wiring
        self.login_view.accounts_updated.connect(self._on_accounts_updated)
        self.runner_view.repo_target_changed.connect(self._on_repo_target_changed)
        self.runner_view.run_finished.connect(self._on_run_finished)
        self.guide_view.navigate_requested.connect(self.switch_page)

        self.apply_theme(self._theme, persist=False)
        self.switch_page(self.PAGE_DASHBOARD)

    @property
    def current_theme(self) -> str:
        return self._theme

    def switch_page(self, index: int) -> None:
        if index < 0 or index >= self.stack.count():
            return
        self.stack.setCurrentIndex(index)
        for page_idx, btn in self._nav_buttons.items():
            btn.setProperty("active", page_idx == index)
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def apply_theme(self, theme_name: str, persist: bool = True) -> None:
        normalized = "light" if theme_name == "light" else "dark"
        self._theme = normalized
        qss = LIGHT_QSS if normalized == "light" else DARK_QSS
        app = QApplication.instance()
        if isinstance(app, QApplication):
            app.setStyleSheet(qss)
        else:
            self.setStyleSheet(qss)
        self.theme_btn.setText("Switch to Dark Theme" if normalized == "light" else "Switch to Light Theme")
        if persist:
            self.state_store.update({"theme": normalized})

    def toggle_theme(self) -> None:
        next_theme = "light" if self._theme == "dark" else "dark"
        self.apply_theme(next_theme, persist=True)

    def restore_saved_sessions(self) -> bool:
        """Restore DPAPI-encrypted sessions; returns True if a primary session is connected."""
        self.login_view.restore_saved_sessions()
        return self._primary is not None

    def _on_accounts_updated(
        self,
        primary: AccountSession | None,
        secondary: AccountSession | None,
    ) -> None:
        self._primary = primary
        self._secondary = secondary
        self.runner_view.set_accounts(primary, secondary)
        owner, repo = self.runner_view.current_repo_target()
        self.dashboard_view.set_context(primary, owner, repo)
        self.sandbox_view.set_context(primary, secondary, owner, repo)
        self.guide_view.update_account_status(primary, secondary)
        self._update_status_summary(owner, repo)

    def _on_repo_target_changed(self, owner: str, repo: str) -> None:
        self.dashboard_view.set_context(self._primary, owner, repo)
        self.sandbox_view.set_context(self._primary, self._secondary, owner, repo)
        self._update_status_summary(owner, repo)

    def _on_run_finished(self) -> None:
        self.dashboard_view.refresh_status()
        self.sandbox_view.refresh_repo()

    def _update_status_summary(self, owner: str, repo: str) -> None:
        if self._primary is None:
            self.sidebar_acct_lbl.setText("Not signed in\nOpen Accounts to connect.")
            self.status_bar_lbl.setText("Disconnected — Sign in on the Accounts tab.")
            return

        sec_line = f"Secondary: @{self._secondary.login}" if self._secondary else "Secondary: none"
        self.sidebar_acct_lbl.setText(f"Primary: @{self._primary.login}\n{sec_line}")
        target = f"{owner or self._primary.login}/{repo}"
        self.status_bar_lbl.setText(
            f"Primary: @{self._primary.login}  |  {sec_line}  |  Target: {target}"
        )

    def shutdown_workers(self) -> None:
        self.dashboard_view.shutdown_workers()
        self.runner_view.shutdown_workers()
        self.login_view.shutdown_workers()
        self.sandbox_view.shutdown_workers()

    def closeEvent(self, event: QCloseEvent) -> None:
        self.shutdown_workers()
        super().closeEvent(event)
