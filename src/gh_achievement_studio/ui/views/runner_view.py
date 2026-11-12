"""Automation runner view with Plan Preview confirmation, Pause/Resume/Cancel, and live logs."""

from __future__ import annotations

import datetime as dt
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..workers import ExecutionWorker, PlanPreviewWorker
from ...core.models import (
    GALAXY_TIERS,
    PAIR_TIERS,
    PULL_SHARK_TIERS,
    AccountSession,
    PlanPreview,
    ProgressEvent,
    RunConfig,
)
from ...core.state import StateStore


class PlanConfirmDialog(QDialog):
    def __init__(self, preview: PlanPreview, dry_run: bool, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Confirm Achievement Run Plan" if not dry_run else "Confirm Dry-Run Simulation")
        self.setMinimumWidth(480)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        mode = "DRY RUN (zero GitHub changes)" if dry_run else f"LIVE EXECUTION ({preview.visibility.upper()})"
        header = QLabel(f"<b>Mode:</b> {mode}<br><b>Target Repo:</b> {preview.full_repo}")
        header.setWordWrap(True)
        layout.addWidget(header)

        est_min = preview.estimated_seconds / 60.0
        summary_lines = [
            f"Repository exists: {'Yes' if preview.repo_exists else 'No (will create)'}",
            f"Cross-Owner Mode: {'Enabled (2nd account owns/merges)' if preview.cross_owner_mode else 'Off (single owner)'}",
            "",
            f"Existing merged PRs: {preview.existing_merged_prs} (co-authored: {preview.existing_coauthored_prs})",
            f"Existing Quickdraw issues: {preview.existing_quickdraw_issues}",
            f"Existing accepted Q&A answers: {preview.existing_accepted_answers}",
            "",
            f"To create — Quickdraw issues: {preview.quickdraw_to_create}",
            f"To create — Pair Extraordinaire PRs: {preview.pair_prs_to_create}",
            f"To create — Pull Shark / YOLO PRs: {preview.pull_shark_prs_to_create}",
            f"To create — Galaxy Brain answers: {preview.galaxy_answers_to_create}",
            f"Estimated duration: ~{preview.estimated_seconds:.0f}s (~{est_min:.1f} min)",
        ]
        if preview.coauthor_display:
            summary_lines.append(f"Co-author trailer: {preview.coauthor_display}")

        box = QPlainTextEdit("\n".join(summary_lines))
        box.setReadOnly(True)
        box.setMinimumHeight(210)
        layout.addWidget(box)

        if preview.warnings:
            warn_lbl = QLabel("Warnings:\n• " + "\n• ".join(preview.warnings))
            warn_lbl.setStyleSheet("color: #d29922; font-weight: 600;")
            warn_lbl.setWordWrap(True)
            layout.addWidget(warn_lbl)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok_btn = buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok_btn.setText("Run Simulation" if dry_run else "Execute Now")
        ok_btn.setObjectName("PrimaryBtn")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class RunnerView(QWidget):
    run_finished = Signal()
    repo_target_changed = Signal(str, str)  # owner, repo

    def __init__(self, state_store: StateStore, parent=None) -> None:
        super().__init__(parent)
        self.state_store = state_store
        self._primary: AccountSession | None = None
        self._secondary: AccountSession | None = None
        self._preview_worker: PlanPreviewWorker | None = None
        self._exec_worker: ExecutionWorker | None = None
        self._pending_config: RunConfig | None = None
        self._logs: list[str] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)

        title = QLabel("Automation Runner")
        title.setObjectName("SectionTitle")
        root.addWidget(title)

        split = QHBoxLayout()
        split.setSpacing(16)

        # Left column: scrollable settings form
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        left_scroll.setMinimumWidth(465)
        left_widget = QWidget()
        left_widget.setObjectName("ScrollContent")
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 12, 0)
        left_layout.setSpacing(12)

        # Repository settings
        repo_group = QGroupBox("Sandbox Repository")
        repo_form = QFormLayout(repo_group)
        repo_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self.repo_input = QLineEdit("github-achievements-sandbox")
        self.repo_input.setMinimumWidth(0)
        self.repo_input.textChanged.connect(self._emit_repo_target)
        repo_form.addRow("Repo Name:", self.repo_input)

        self.visibility_combo = QComboBox()
        self.visibility_combo.setMinimumWidth(0)
        self.visibility_combo.addItems(["public", "private"])
        repo_form.addRow("Visibility:", self.visibility_combo)

        self.cross_owner_chk = QCheckBox("Cross-Owner Mode (2nd owns && merges)")
        self.cross_owner_chk.setToolTip(
            "When enabled, your 2nd account creates the sandbox repository and merges PRs opened by Primary."
        )
        self.cross_owner_chk.setEnabled(False)
        self.cross_owner_chk.stateChanged.connect(self._emit_repo_target)
        repo_form.addRow("", self.cross_owner_chk)
        left_layout.addWidget(repo_group)

        # Single-account targets
        single_group = QGroupBox("Single-Account Achievements")
        single_form = QFormLayout(single_group)
        single_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self.quickdraw_chk = QCheckBox("Quickdraw (open && close issue < 5 min)")
        self.quickdraw_chk.setChecked(True)
        single_form.addRow("", self.quickdraw_chk)

        self.yolo_chk = QCheckBox("YOLO (merge PR without code review)")
        self.yolo_chk.setChecked(True)
        single_form.addRow("", self.yolo_chk)

        self.strict_yolo_chk = QCheckBox("Strict YOLO (request 2nd account reviewer)")
        self.strict_yolo_chk.setToolTip(
            "Requests your 2nd account as a PR reviewer before merging without review approval."
        )
        self.strict_yolo_chk.setEnabled(False)
        single_form.addRow("", self.strict_yolo_chk)

        self.pull_tier_combo = QComboBox()
        self.pull_tier_combo.addItem("None (0 PRs)", "none")
        self.pull_tier_combo.addItem("Default (2 PRs)", "default")
        self.pull_tier_combo.addItem("Bronze x2 (16 PRs)", "bronze")
        self.pull_tier_combo.addItem("Silver x3 (128 PRs)", "silver")
        self.pull_tier_combo.addItem("Gold x4 (1,024 PRs)", "gold")
        self.pull_tier_combo.addItem("Custom Count...", "custom")
        self.pull_tier_combo.setCurrentIndex(2)
        self.pull_tier_combo.currentIndexChanged.connect(self._on_pull_tier_changed)
        single_form.addRow("Pull Shark:", self.pull_tier_combo)

        self.pull_custom_spin = QSpinBox()
        self.pull_custom_spin.setRange(0, 5000)
        self.pull_custom_spin.setValue(16)
        self.pull_custom_spin.setEnabled(False)
        single_form.addRow("Custom PRs:", self.pull_custom_spin)
        left_layout.addWidget(single_group)

        # Multi-account targets
        multi_group = QGroupBox("Two-Account Achievements")
        multi_form = QFormLayout(multi_group)
        multi_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self.pair_combo = QComboBox()
        self.pair_combo.addItem("Skip (0)", 0)
        self.pair_combo.addItem("Default (1 PR)", PAIR_TIERS["default"])
        self.pair_combo.addItem("Bronze x2 (10 PRs)", PAIR_TIERS["bronze"])
        self.pair_combo.addItem("Silver x3 (24 PRs)", PAIR_TIERS["silver"])
        self.pair_combo.addItem("Gold x4 (48 PRs)", PAIR_TIERS["gold"])
        multi_form.addRow("Pair Extraordinaire:", self.pair_combo)

        self.coauthor_user_input = QLineEdit()
        self.coauthor_user_input.setMinimumWidth(0)
        self.coauthor_user_input.setPlaceholderText("Auto (2nd account) or username")
        multi_form.addRow("Co-author User:", self.coauthor_user_input)

        self.coauthor_email_input = QLineEdit()
        self.coauthor_email_input.setMinimumWidth(0)
        self.coauthor_email_input.setPlaceholderText("Optional verified/noreply email")
        multi_form.addRow("Co-author Email:", self.coauthor_email_input)

        self.galaxy_combo = QComboBox()
        self.galaxy_combo.addItem("Skip (0)", 0)
        self.galaxy_combo.addItem("Default (2 answers)", GALAXY_TIERS["default"])
        self.galaxy_combo.addItem("Bronze x2 (8 answers)", GALAXY_TIERS["bronze"])
        self.galaxy_combo.addItem("Silver x3 (16 answers)", GALAXY_TIERS["silver"])
        self.galaxy_combo.addItem("Gold x4 (32 answers)", GALAXY_TIERS["gold"])
        self.galaxy_combo.setEnabled(False)
        self.galaxy_combo.setToolTip("Requires connecting a distinct secondary GitHub account on the Accounts tab.")
        multi_form.addRow("Galaxy Brain:", self.galaxy_combo)

        self.dual_account_hint = QLabel(
            "Connect a distinct 2nd account on the Accounts tab to unlock Galaxy Brain, Strict YOLO, and Cross-Owner Mode."
        )
        self.dual_account_hint.setObjectName("Muted")
        self.dual_account_hint.setWordWrap(True)
        multi_form.addRow("", self.dual_account_hint)
        left_layout.addWidget(multi_group)

        # Pacing & safety
        safety_group = QGroupBox("Rate-Limit && Safety Controls")
        safety_form = QFormLayout(safety_group)
        safety_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self.delay_spin = QDoubleSpinBox()
        self.delay_spin.setRange(0.5, 60.0)
        self.delay_spin.setSingleStep(0.5)
        self.delay_spin.setValue(2.5)
        self.delay_spin.setSuffix(" s")
        safety_form.addRow("Delay Between Ops:", self.delay_spin)

        self.batch_spin = QSpinBox()
        self.batch_spin.setRange(1, 500)
        self.batch_spin.setValue(50)
        safety_form.addRow("Max PRs Per Burst:", self.batch_spin)

        self.dry_run_chk = QCheckBox("Dry-Run Simulation Only (no remote mutations)")
        safety_form.addRow("", self.dry_run_chk)
        left_layout.addWidget(safety_group)

        left_layout.addStretch(1)
        left_scroll.setWidget(left_widget)
        split.addWidget(left_scroll, 5)

        # Right column: Execution controls & logs
        right_group = QGroupBox("Execution && Live Logs")
        right_layout = QVBoxLayout(right_group)
        right_layout.setContentsMargins(16, 20, 16, 16)
        right_layout.setSpacing(10)

        btn_row = QHBoxLayout()
        self.start_btn = QPushButton("Preview Plan && Start")
        self.start_btn.setObjectName("PrimaryBtn")
        self.start_btn.setDisabled(True)
        self.start_btn.clicked.connect(self._on_start_clicked)
        btn_row.addWidget(self.start_btn)

        self.pause_btn = QPushButton("Pause")
        self.pause_btn.setDisabled(True)
        self.pause_btn.clicked.connect(self._on_pause_resume)
        btn_row.addWidget(self.pause_btn)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("DangerBtn")
        self.cancel_btn.setDisabled(True)
        self.cancel_btn.clicked.connect(self._on_cancel)
        btn_row.addWidget(self.cancel_btn)
        right_layout.addLayout(btn_row)

        self.stage_lbl = QLabel("Idle — Connect primary account to begin.")
        self.stage_lbl.setObjectName("Muted")
        right_layout.addWidget(self.stage_lbl)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        right_layout.addWidget(self.progress_bar)

        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setPlaceholderText("Execution logs will appear here...")
        right_layout.addWidget(self.log_output, 1)

        log_btn_row = QHBoxLayout()
        log_btn_row.addStretch(1)
        self.copy_logs_btn = QPushButton("Copy Logs")
        self.copy_logs_btn.clicked.connect(self._copy_logs)
        log_btn_row.addWidget(self.copy_logs_btn)

        self.clear_logs_btn = QPushButton("Clear Logs")
        self.clear_logs_btn.clicked.connect(self._clear_logs)
        log_btn_row.addWidget(self.clear_logs_btn)
        right_layout.addLayout(log_btn_row)

        split.addWidget(right_group, 5)
        root.addLayout(split, 1)

    def set_accounts(self, primary: AccountSession | None, secondary: AccountSession | None) -> None:
        self._primary = primary
        self._secondary = secondary
        is_running = self._exec_worker is not None and self._exec_worker.isRunning()
        has_distinct_secondary = (
            primary is not None
            and secondary is not None
            and secondary.login.lower() != primary.login.lower()
        )
        self.start_btn.setEnabled(primary is not None and not is_running)
        self.cross_owner_chk.setEnabled(has_distinct_secondary)
        self.strict_yolo_chk.setEnabled(has_distinct_secondary)
        self.galaxy_combo.setEnabled(has_distinct_secondary)
        if not has_distinct_secondary:
            self.cross_owner_chk.setChecked(False)
            self.strict_yolo_chk.setChecked(False)
            self.galaxy_combo.setCurrentIndex(0)
            self.dual_account_hint.show()
        else:
            self.dual_account_hint.hide()

        if secondary is not None and not self.coauthor_user_input.text().strip():
            self.coauthor_user_input.setPlaceholderText(f"Default: @{secondary.login} ({secondary.noreply_email})")
        elif secondary is None:
            self.coauthor_user_input.setPlaceholderText("Auto (2nd account) or username")
        if primary is None:
            self.stage_lbl.setText("Idle — Connect primary account to begin.")
        elif not is_running:
            self.stage_lbl.setText(f"Ready for @{primary.login}.")
        self._emit_repo_target()

    def current_repo_target(self) -> tuple[str, str]:
        raw = self.repo_input.text().strip() or "github-achievements-sandbox"
        if "/" in raw:
            owner, name = raw.split("/", 1)
            return owner.strip(), name.strip()
        if self.cross_owner_chk.isChecked() and self._secondary is not None:
            return self._secondary.login, raw
        return (self._primary.login if self._primary else ""), raw

    def _emit_repo_target(self) -> None:
        owner, repo = self.current_repo_target()
        self.repo_target_changed.emit(owner, repo)

    def _on_pull_tier_changed(self) -> None:
        key = self.pull_tier_combo.currentData()
        if key == "custom":
            self.pull_custom_spin.setEnabled(True)
        else:
            self.pull_custom_spin.setEnabled(False)
            self.pull_custom_spin.setValue(PULL_SHARK_TIERS.get(str(key), 16))

    def build_config_from_ui(self) -> RunConfig:
        tier_key = str(self.pull_tier_combo.currentData())
        pull_target = self.pull_custom_spin.value() if tier_key == "custom" else PULL_SHARK_TIERS[tier_key]
        return RunConfig(
            repo_name=self.repo_input.text().strip() or "github-achievements-sandbox",
            visibility=self.visibility_combo.currentText(),
            cross_owner_mode=self.cross_owner_chk.isChecked(),
            run_quickdraw=self.quickdraw_chk.isChecked(),
            run_yolo=self.yolo_chk.isChecked(),
            request_secondary_reviewer=self.strict_yolo_chk.isChecked(),
            pull_shark_target=pull_target,
            pair_target=int(self.pair_combo.currentData()),
            coauthor_username=self.coauthor_user_input.text().strip(),
            coauthor_email=self.coauthor_email_input.text().strip(),
            galaxy_target=int(self.galaxy_combo.currentData()),
            delay_seconds=float(self.delay_spin.value()),
            batch_limit=int(self.batch_spin.value()),
            dry_run=self.dry_run_chk.isChecked(),
        )

    def append_log(self, text: str, level: str = "INFO") -> None:
        stamp = dt.datetime.now().strftime("%H:%M:%S")
        line = f"{stamp} [{level}] {text}"
        self._logs.append(line)
        self.log_output.appendPlainText(line)

    def _on_start_clicked(self) -> None:
        if self._primary is None:
            return
        cfg = self.build_config_from_ui()
        self._pending_config = cfg
        self.start_btn.setDisabled(True)
        self.stage_lbl.setText("Inspecting live GitHub state and calculating delta plan...")
        self.append_log("Computing execution plan...")

        self._preview_worker = PlanPreviewWorker(self._primary, self._secondary, cfg)
        self._preview_worker.succeeded.connect(self._on_preview_ready)
        self._preview_worker.failed.connect(self._on_preview_failed)
        self._preview_worker.start()

    def _on_preview_failed(self, err: str) -> None:
        self.start_btn.setEnabled(self._primary is not None)
        self.stage_lbl.setText("Plan check failed.")
        self.append_log(err, "ERROR")
        QMessageBox.warning(self, "Configuration Error", err)

    def _on_preview_ready(self, preview: PlanPreview) -> None:
        cfg = self._pending_config
        if cfg is None or self._primary is None:
            self.start_btn.setEnabled(self._primary is not None)
            return

        dlg = PlanConfirmDialog(preview, cfg.dry_run, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            self.start_btn.setEnabled(True)
            self.stage_lbl.setText("Run cancelled at preview confirmation.")
            self.append_log("User cancelled execution from preview dialog.")
            return

        self.progress_bar.setValue(0)
        self.pause_btn.setEnabled(True)
        self.pause_btn.setText("Pause")
        self.cancel_btn.setEnabled(True)
        self.stage_lbl.setText("Starting execution...")

        self._exec_worker = ExecutionWorker(self._primary, self._secondary, cfg, self.state_store)
        self._exec_worker.event_emitted.connect(self._on_exec_event)
        self._exec_worker.succeeded.connect(self._on_exec_finished)
        self._exec_worker.failed.connect(self._on_exec_failed)
        self._exec_worker.start()

    def _on_exec_event(self, evt: ProgressEvent) -> None:
        if evt.message:
            self.append_log(evt.message, evt.level)
        if evt.stage:
            self.stage_lbl.setText(f"{evt.stage}: {evt.message}")
        elif evt.kind in ("completed", "cancelled") and evt.message:
            self.stage_lbl.setText(evt.message)
        if evt.total > 0:
            pct = int(min(100, round((evt.current / evt.total) * 100)))
            self.progress_bar.setValue(pct)
            self.progress_bar.setFormat(f"{evt.current}/{evt.total} ({pct}%)")

    def _on_exec_finished(self, _plan: PlanPreview) -> None:
        self.start_btn.setEnabled(self._primary is not None)
        self.pause_btn.setDisabled(True)
        self.pause_btn.setText("Pause")
        self.cancel_btn.setDisabled(True)
        self.run_finished.emit()

    def _on_exec_failed(self, err: str) -> None:
        self.start_btn.setEnabled(self._primary is not None)
        self.pause_btn.setDisabled(True)
        self.pause_btn.setText("Pause")
        self.cancel_btn.setDisabled(True)
        self.stage_lbl.setText("Execution failed.")
        self.append_log(err, "ERROR")
        QMessageBox.critical(self, "Execution Error", err)

    def _on_pause_resume(self) -> None:
        if self._exec_worker is None or not self._exec_worker.isRunning():
            return
        if self._exec_worker.pause_event.is_set():
            self._exec_worker.resume()
            self.pause_btn.setText("Pause")
            self.stage_lbl.setText("Resumed execution...")
            self.append_log("Execution resumed.")
        else:
            self._exec_worker.pause()
            self.pause_btn.setText("Resume")
            self.stage_lbl.setText("Paused (will pause after active request).")
            self.append_log("Pause requested.")

    def _on_cancel(self) -> None:
        if self._exec_worker is not None and self._exec_worker.isRunning():
            self._exec_worker.cancel()
            self.cancel_btn.setDisabled(True)
            self.pause_btn.setDisabled(True)
            self.stage_lbl.setText("Cancelling...")
            self.append_log("Cancellation requested by user.", "WARN")

    def _copy_logs(self) -> None:
        cb = QGuiApplication.clipboard()
        if cb is not None:
            cb.setText("\n".join(self._logs))

    def _clear_logs(self) -> None:
        self._logs.clear()
        self.log_output.clear()

    def get_logs_snapshot(self) -> list[str]:
        return list(self._logs)

    def shutdown_workers(self) -> None:
        if self._preview_worker is not None and self._preview_worker.isRunning():
            self._preview_worker.wait(2000)
        if self._exec_worker is not None and self._exec_worker.isRunning():
            self._exec_worker.cancel()
            self._exec_worker.wait(3000)
