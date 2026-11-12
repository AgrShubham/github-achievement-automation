"""Desktop GUI application entrypoint with PyInstaller frozen-path & crash logging support."""

from __future__ import annotations

import datetime as dt
import os
from pathlib import Path
import re
import sys
import traceback

from .core.state import default_app_dir

_TOKEN_PATTERN = re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{12,}|github_pat_[A-Za-z0-9_]{16,})\b")


def _scrub_tokens(text: str) -> str:
    return _TOKEN_PATTERN.sub("***REDACTED_TOKEN***", text)


def resolve_icon_path() -> Path | None:
    """Locate packaging/icon.ico both in source runs and frozen PyInstaller builds."""
    candidates: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(str(meipass)) / "packaging" / "icon.ico")
        candidates.append(Path(str(meipass)) / "icon.ico")
    repo_root = Path(__file__).resolve().parents[2]
    candidates.append(repo_root / "packaging" / "icon.ico")
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _write_crash_log(exc_type: type[BaseException], exc_value: BaseException, exc_tb) -> Path | None:
    try:
        log_path = default_app_dir() / "crash.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        stamp = dt.datetime.now(dt.timezone.utc).isoformat()
        tb_text = _scrub_tokens("".join(traceback.format_exception(exc_type, exc_value, exc_tb)))
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(f"\n=== Crash {stamp} ===\n{tb_text}\n")
        return log_path
    except OSError:
        return None


def _attach_parent_console_if_needed() -> None:
    """Attach to parent console for `--cli` runs in windowed PyInstaller builds."""
    if sys.platform != "win32":
        return
    if sys.stdout is not None and sys.stderr is not None:
        return
    try:
        import ctypes

        if ctypes.windll.kernel32.AttachConsole(-1):
            if sys.stdout is None:
                sys.stdout = open("CONOUT$", "w", encoding="utf-8", errors="replace", buffering=1)
            if sys.stderr is None:
                sys.stderr = open("CONOUT$", "w", encoding="utf-8", errors="replace", buffering=1)
            if sys.stdin is None:
                sys.stdin = open("CONIN$", "r", encoding="utf-8", errors="replace")
    except OSError:
        pass


def main(argv: list[str] | None = None) -> int:
    raw_args = list(sys.argv[1:] if argv is None else argv)
    if "--cli" in raw_args:
        _attach_parent_console_if_needed()
        cli_args = [arg for arg in raw_args if arg != "--cli"]
        from .cli.main import main as cli_main

        return cli_main(cli_args)

    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication, QIcon
    from PySide6.QtWidgets import QApplication, QMessageBox

    from .ui.main_window import MainWindow

    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication([sys.argv[0], *raw_args])
    app.setApplicationName("GitHub Achievement Studio")
    app.setOrganizationName("GitHubAchievementStudio")

    icon_path = resolve_icon_path()
    if icon_path is not None:
        app.setWindowIcon(QIcon(str(icon_path)))

    def _excepthook(exc_type, exc_value, exc_tb) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        log_path = _write_crash_log(exc_type, exc_value, exc_tb)
        detail = _scrub_tokens(f"{exc_value}")
        if log_path is not None:
            detail += f"\n\nCrash log written to:\n{log_path}"
        if os.environ.get("QT_QPA_PLATFORM") != "offscreen":
            QMessageBox.critical(None, "Unexpected Error", detail)
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = _excepthook

    window = MainWindow(icon_path=icon_path)
    window.show()

    has_primary = window.restore_saved_sessions()
    if has_primary:
        window.switch_page(MainWindow.PAGE_DASHBOARD)
        window.dashboard_view.refresh_status()
    else:
        window.switch_page(MainWindow.PAGE_ACCOUNTS)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
