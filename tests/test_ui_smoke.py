"""Offscreen PySide6 GUI controller & widget smoke tests."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QDialog

from gh_achievement_studio.core.auth import CredentialStore
from gh_achievement_studio.core.models import (
    AccountSession,
    PlanPreview,
    ProgressEvent,
    VerificationReport,
)
from gh_achievement_studio.core.state import StateStore
from gh_achievement_studio.ui.main_window import MainWindow
from gh_achievement_studio.ui.views.runner_view import PlanConfirmDialog


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    existing = QApplication.instance()
    if isinstance(existing, QApplication):
        return existing
    return QApplication([sys.argv[0]])


def _session(login: str, user_id: int) -> AccountSession:
    return AccountSession(
        login=login,
        user_id=user_id,
        name=login.title(),
        commit_email=f"{login}@gmail.com",
        token="ghp_TestTokenValue12345678",
        scopes=("repo", "read:user"),
    )


def test_main_window_navigation_theme_and_account_wiring(qapp: QApplication, tmp_path: Path) -> None:
    state_store = StateStore(tmp_path / "state.json")
    cred_store = CredentialStore(tmp_path / "credentials.json")

    win = MainWindow(state_store=state_store, cred_store=cred_store)
    assert win.stack.currentIndex() == MainWindow.PAGE_DASHBOARD
    assert not win.runner_view.start_btn.isEnabled()
    assert not win.dashboard_view.refresh_btn.isEnabled()
    assert not win.sandbox_view.inspect_btn.isEnabled()

    # Tab switching + active nav state
    win.switch_page(MainWindow.PAGE_GUIDE)
    assert win.stack.currentIndex() == MainWindow.PAGE_GUIDE
    assert win._nav_buttons[MainWindow.PAGE_GUIDE].property("active") is True
    assert win._nav_buttons[MainWindow.PAGE_DASHBOARD].property("active") is False

    win.switch_page(MainWindow.PAGE_ACCOUNTS)
    assert win.stack.currentIndex() == MainWindow.PAGE_ACCOUNTS
    assert win._nav_buttons[MainWindow.PAGE_ACCOUNTS].property("active") is True
    win.switch_page(MainWindow.PAGE_RUNNER)
    assert win.stack.currentIndex() == MainWindow.PAGE_RUNNER

    # GuideView navigation CTAs jump directly to target views
    assert win.guide_view.step1_status_pill.text() == "Not Connected"
    assert win.guide_view.get_started_btn.text() == "Connect Account"
    win.guide_view.step1_nav_btn.click()
    assert win.stack.currentIndex() == MainWindow.PAGE_ACCOUNTS
    win.guide_view.step2_nav_btn.click()
    assert win.stack.currentIndex() == MainWindow.PAGE_RUNNER
    win.guide_view.step3_nav_btn.click()
    assert win.stack.currentIndex() == MainWindow.PAGE_DASHBOARD
    win.guide_view.step4_nav_btn.click()
    assert win.stack.currentIndex() == MainWindow.PAGE_SANDBOX
    win.guide_view.get_started_btn.click()
    assert win.stack.currentIndex() == MainWindow.PAGE_ACCOUNTS

    # Theme switching persists to StateStore
    assert win.current_theme == "dark"
    win.toggle_theme()
    assert win.current_theme == "light"
    assert state_store.load()["theme"] == "light"
    win.toggle_theme()
    assert win.current_theme == "dark"

    # Two-account controls start disabled until a distinct 2nd account is connected
    assert not win.runner_view.galaxy_combo.isEnabled()
    assert not win.runner_view.cross_owner_chk.isEnabled()
    assert not win.runner_view.strict_yolo_chk.isEnabled()

    # Connect same primary & secondary -> same-account warning shown & dual controls remain disabled
    p = _session("alice", 1)
    win.login_view.primary_card.set_session(p, persist=False)
    assert win.runner_view.start_btn.isEnabled()
    assert win.dashboard_view.refresh_btn.isEnabled()
    assert win.sandbox_view.inspect_btn.isEnabled()
    assert not win.runner_view.galaxy_combo.isEnabled()
    assert win.guide_view.step1_status_pill.text() == "Primary Connected"
    assert "@alice" in win.guide_view.step1_status_note.text()
    assert win.guide_view.get_started_btn.text() == "Manage Accounts"

    win.login_view.secondary_card.set_session(_session("Alice", 1), persist=False)
    assert not win.login_view.same_account_warn.isHidden()
    assert not win.runner_view.galaxy_combo.isEnabled()
    assert not win.runner_view.cross_owner_chk.isEnabled()
    assert win.guide_view.step1_status_pill.text() == "Primary Connected"

    # Switch secondary to distinct account + enable Cross-Owner Mode
    sec = _session("bob", 2)
    win.login_view.secondary_card.set_session(sec, persist=False)
    assert win.login_view.same_account_warn.isHidden()
    assert win.runner_view.galaxy_combo.isEnabled()
    assert win.runner_view.cross_owner_chk.isEnabled()
    assert win.runner_view.strict_yolo_chk.isEnabled()
    assert win.guide_view.step1_status_pill.text() == "Dual Connected"
    assert "@alice" in win.guide_view.step1_status_note.text()
    assert "@bob" in win.guide_view.step1_status_note.text()

    win.runner_view.cross_owner_chk.setChecked(True)
    assert win.runner_view.current_repo_target() == ("bob", "github-achievements-sandbox")
    assert "@alice" in win.status_bar_lbl.text()

    # Signing out secondary resets & disables dual-account controls
    win.login_view.secondary_card.set_session(None, persist=False)
    assert not win.runner_view.cross_owner_chk.isEnabled()
    assert not win.runner_view.cross_owner_chk.isChecked()
    assert not win.runner_view.galaxy_combo.isEnabled()
    assert win.runner_view.galaxy_combo.currentData() == 0

    # Reconnect distinct secondary for remaining assertions
    win.login_view.secondary_card.set_session(sec, persist=False)
    win.runner_view.cross_owner_chk.setChecked(True)

    # Dashboard verification report updates cards and metrics
    report = VerificationReport(
        actor="alice",
        repo_full_name="bob/github-achievements-sandbox",
        repo_exists=True,
        repo_archived=False,
        repo_url="https://github.com/bob/github-achievements-sandbox",
        profile_url="https://github.com/alice",
        achievements_url="https://github.com/alice?tab=achievements",
        repo_merged_prs=16,
        global_merged_prs=18,
        coauthored_prs=4,
        quickdraw_issues=1,
        accepted_answers=2,
        visible_badges=("Quickdraw", "Pull Shark (x2)", "YOLO"),
        rate_limit_remaining=4900,
        rate_limit_limit=5000,
    )
    win.dashboard_view.apply_verification_report(report)
    assert win.dashboard_view.metric_labels["repo_prs"].text() == "16"
    assert win.dashboard_view.metric_labels["quota"].text() == "4900/5000"
    assert win.dashboard_view._cards["pull-shark"].status_lbl.text() == "Pull Shark (x2)"
    assert win.dashboard_view._cards["quickdraw"].status_lbl.text() == "Quickdraw"

    # Sandbox view updates archive button label
    win.sandbox_view.apply_report(report)
    assert win.sandbox_view.archive_btn.isEnabled()
    assert win.sandbox_view.archive_btn.text() == "Archive Sandbox Repo"

    # Runner event updates progress & stage label
    win.runner_view._on_exec_event(
        ProgressEvent(kind="completed", message="Done cleanly.", current=4, total=4)
    )
    assert win.runner_view.progress_bar.value() == 100
    assert win.runner_view.stage_lbl.text() == "Done cleanly."

    # Signing out primary resets Guide Step 1 status & Dashboard metrics
    win.login_view.primary_card.set_session(None, persist=False)
    assert win.guide_view.step1_status_pill.text() == "Not Connected"
    assert win.guide_view.get_started_btn.text() == "Connect Account"
    assert win.dashboard_view.metric_labels["repo_prs"].text() == "—"
    assert win.dashboard_view.status_banner.isHidden()

    win.close()


def test_plan_confirm_dialog_and_runner_form(qapp: QApplication, tmp_path: Path) -> None:
    state_store = StateStore(tmp_path / "state.json")
    cred_store = CredentialStore(tmp_path / "credentials.json")
    win = MainWindow(state_store=state_store, cred_store=cred_store)

    # Custom Pull Shark count toggle
    custom_idx = win.runner_view.pull_tier_combo.findData("custom")
    win.runner_view.pull_tier_combo.setCurrentIndex(custom_idx)
    assert win.runner_view.pull_custom_spin.isEnabled()
    win.runner_view.pull_custom_spin.setValue(33)
    cfg = win.runner_view.build_config_from_ui()
    assert cfg.pull_shark_target == 33

    preview = PlanPreview(
        repo_owner="alice",
        repo_name="github-achievements-sandbox",
        visibility="public",
        repo_exists=False,
        cross_owner_mode=False,
        existing_merged_prs=0,
        existing_coauthored_prs=0,
        existing_quickdraw_issues=0,
        existing_accepted_answers=0,
        quickdraw_to_create=1,
        pair_prs_to_create=0,
        pull_shark_prs_to_create=33,
        galaxy_answers_to_create=0,
        estimated_seconds=120.0,
        warnings=("Solo self-merged PRs may lag.",),
    )
    dlg = PlanConfirmDialog(preview, dry_run=True, parent=win)
    assert "Simulation" in dlg.windowTitle()
    dlg.close()

    # Rejecting PlanConfirmDialog must not start ExecutionWorker and must re-enable Start
    win.login_view.primary_card.set_session(_session("alice", 1), persist=False)
    win.runner_view._pending_config = cfg
    win.runner_view.start_btn.setDisabled(True)
    with (
        mock.patch.object(PlanConfirmDialog, "exec", return_value=QDialog.DialogCode.Rejected),
        mock.patch("gh_achievement_studio.ui.views.runner_view.ExecutionWorker") as m_worker,
    ):
        win.runner_view._on_preview_ready(preview)
    m_worker.assert_not_called()
    assert win.runner_view.start_btn.isEnabled()
    assert "cancelled" in win.runner_view.stage_lbl.text().lower()

    # Diagnostics export redacts secrets before writing to disk
    win.runner_view.append_log("Authorization leaked ghp_TestTokenValue12345678")
    diag_path = tmp_path / "diag.json"
    with (
        mock.patch("gh_achievement_studio.ui.views.sandbox_view.QFileDialog.getSaveFileName", return_value=(str(diag_path), "JSON Files (*.json)")),
        mock.patch("gh_achievement_studio.ui.views.sandbox_view.QMessageBox.information"),
    ):
        win.sandbox_view._export_diagnostics()
    written = diag_path.read_text(encoding="utf-8")
    assert "ghp_TestTokenValue12345678" not in written
    assert "***REDACTED***" in written
    assert json.loads(written)["primary_login"] == "alice"

    # Device Flow challenge reveals Copy Code button and updates clipboard
    from gh_achievement_studio.core.auth import DeviceCodeChallenge

    with mock.patch("gh_achievement_studio.ui.views.login_view.QDesktopServices.openUrl"):
        win.login_view.primary_card._on_device_challenge(
            DeviceCodeChallenge(
                device_code="dev123",
                user_code="WXYZ-5678",
                verification_uri="https://github.com/login/device",
                expires_in=900,
                interval=5,
            )
        )
    assert not win.login_view.primary_card.device_copy_btn.isHidden()
    assert "WXYZ-5678" in win.login_view.primary_card.device_status_lbl.text()

    win.close()


def test_app_startup_landing_page(qapp: QApplication) -> None:
    from gh_achievement_studio import app as app_mod
    from gh_achievement_studio.ui.views.dashboard_view import DashboardView

    created_windows: list[MainWindow] = []
    orig_init = MainWindow.__init__

    def _capture_init(self, *args, **kwargs):
        orig_init(self, *args, **kwargs)
        created_windows.append(self)

    with (
        mock.patch.object(MainWindow, "__init__", _capture_init),
        mock.patch.object(MainWindow, "show"),
        mock.patch.object(MainWindow, "restore_saved_sessions", return_value=False),
        mock.patch.object(QApplication, "exec", return_value=0),
    ):
        rc = app_mod.main([])

    assert rc == 0
    assert created_windows[-1].stack.currentIndex() == MainWindow.PAGE_GUIDE
    created_windows[-1].close()

    with (
        mock.patch.object(MainWindow, "__init__", _capture_init),
        mock.patch.object(MainWindow, "show"),
        mock.patch.object(MainWindow, "restore_saved_sessions", return_value=True),
        mock.patch.object(DashboardView, "refresh_status"),
        mock.patch.object(QApplication, "exec", return_value=0),
    ):
        rc2 = app_mod.main([])

    assert rc2 == 0
    assert created_windows[-1].stack.currentIndex() == MainWindow.PAGE_DASHBOARD
    created_windows[-1].close()
