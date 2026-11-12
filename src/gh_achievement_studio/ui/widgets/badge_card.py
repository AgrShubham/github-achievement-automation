"""Reusable achievement card widget."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout

from ...core.models import BadgeCatalogItem, BadgeCategory


class BadgeCard(QFrame):
    def __init__(self, item: BadgeCatalogItem, parent=None) -> None:
        super().__init__(parent)
        self.item = item
        self.setObjectName("Card")
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(6)

        header = QHBoxLayout()
        header.setSpacing(8)
        self.title_lbl = QLabel(item.name)
        self.title_lbl.setStyleSheet("font-size: 14px; font-weight: 700; background-color: transparent;")
        self.title_lbl.setWordWrap(True)
        header.addWidget(self.title_lbl, 1)

        self.status_lbl = QLabel("Not Earned")
        self.status_lbl.setObjectName("StatusPill")
        self.status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.addWidget(self.status_lbl)
        root.addLayout(header)

        cat_text = {
            BadgeCategory.AUTO_SINGLE: "Auto (Single Account)",
            BadgeCategory.AUTO_DUAL: "Auto (2-Account)",
            BadgeCategory.MANUAL: "Manual / Program",
            BadgeCategory.UNAVAILABLE: "Unavailable",
        }[item.category]
        self.meta_lbl = QLabel(f"{cat_text}  •  {item.tiers}")
        self.meta_lbl.setObjectName("Muted")
        self.meta_lbl.setWordWrap(True)
        self.meta_lbl.setMinimumWidth(0)
        root.addWidget(self.meta_lbl)

        self.summary_lbl = QLabel(item.summary)
        self.summary_lbl.setWordWrap(True)
        self.summary_lbl.setMinimumWidth(0)
        root.addWidget(self.summary_lbl)

        self.notes_lbl = QLabel(item.notes)
        self.notes_lbl.setObjectName("Muted")
        self.notes_lbl.setWordWrap(True)
        self.notes_lbl.setMinimumWidth(0)
        self.notes_lbl.setStyleSheet("font-size: 11.5px; background-color: transparent;")
        root.addWidget(self.notes_lbl)

        self.set_earned_state(None)

    def set_earned_state(self, live_label: str | None) -> None:
        if live_label:
            self.status_lbl.setText(live_label)
            self.status_lbl.setStyleSheet(
                "background-color: #238636; color: #ffffff; border-radius: 10px; padding: 2px 9px; font-size: 11px; font-weight: 700;"
            )
            return

        if self.item.category == BadgeCategory.UNAVAILABLE:
            self.status_lbl.setText("Unavailable")
            self.status_lbl.setStyleSheet(
                "background-color: #484f58; color: #ffffff; border-radius: 10px; padding: 2px 9px; font-size: 11px; font-weight: 700;"
            )
        elif self.item.category == BadgeCategory.MANUAL:
            self.status_lbl.setText("Manual")
            self.status_lbl.setStyleSheet(
                "background-color: #9e6a03; color: #ffffff; border-radius: 10px; padding: 2px 9px; font-size: 11px; font-weight: 700;"
            )
        elif self.item.category == BadgeCategory.AUTO_DUAL:
            self.status_lbl.setText("2-Account")
            self.status_lbl.setStyleSheet(
                "background-color: #6e40c9; color: #ffffff; border-radius: 10px; padding: 2px 9px; font-size: 11px; font-weight: 700;"
            )
        else:
            self.status_lbl.setText("Ready")
            self.status_lbl.setStyleSheet(
                "background-color: #1f6feb; color: #ffffff; border-radius: 10px; padding: 2px 9px; font-size: 11px; font-weight: 700;"
            )
