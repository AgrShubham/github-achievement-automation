"""Modern Windows 11-inspired Light & Dark QSS themes."""

from __future__ import annotations

DARK_QSS = """
QMainWindow, QDialog {
    background-color: #0d1117;
    color: #e6edf3;
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 13px;
}
QWidget {
    color: #e6edf3;
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 13px;
}
QStackedWidget, QScrollArea, QWidget#ScrollContent {
    background-color: #0d1117;
}
QLabel, QCheckBox, QRadioButton {
    background-color: transparent;
}
QFrame#Sidebar {
    background-color: #161b22;
    border-right: 1px solid #30363d;
}
QFrame#Card, QGroupBox {
    background-color: #161b22;
    border: 1px solid #30363d;
    border-radius: 10px;
}
QGroupBox {
    margin-top: 10px;
    padding-top: 14px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: #8b949e;
}
QPushButton {
    background-color: #21262d;
    color: #e6edf3;
    border: 1px solid #30363d;
    border-radius: 7px;
    padding: 7px 14px;
    font-weight: 600;
}
QPushButton:hover {
    background-color: #30363d;
    border-color: #8b949e;
}
QPushButton:disabled {
    color: #6e7681;
    background-color: #161b22;
    border-color: #21262d;
}
QPushButton#PrimaryBtn {
    background-color: #238636;
    border-color: #2ea043;
    color: #ffffff;
}
QPushButton#PrimaryBtn:hover {
    background-color: #2ea043;
}
QPushButton#PrimaryBtn:disabled {
    background-color: #194225;
    border-color: #1f532d;
    color: #7d9b85;
}
QPushButton#DangerBtn {
    background-color: #8e2228;
    border-color: #da3633;
    color: #ffffff;
}
QPushButton#DangerBtn:hover {
    background-color: #b62324;
}
QPushButton#NavBtn {
    text-align: left;
    padding: 10px 14px;
    border: none;
    border-radius: 8px;
    background-color: transparent;
    color: #8b949e;
    font-size: 13px;
}
QPushButton#NavBtn:hover {
    background-color: #21262d;
    color: #e6edf3;
}
QPushButton#NavBtn[active="true"] {
    background-color: #1f6feb33;
    color: #58a6ff;
    border-left: 3px solid #58a6ff;
}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit {
    background-color: #0d1117;
    color: #e6edf3;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 6px 10px;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QPlainTextEdit:focus {
    border-color: #58a6ff;
}
QProgressBar {
    background-color: #21262d;
    border: 1px solid #30363d;
    border-radius: 6px;
    text-align: center;
    height: 18px;
    color: #e6edf3;
    font-weight: 600;
}
QProgressBar::chunk {
    background-color: #2f81f7;
    border-radius: 5px;
}
QLabel#Muted {
    color: #8b949e;
}
QLabel#SectionTitle {
    font-size: 18px;
    font-weight: 700;
    color: #f0f6fc;
}
QLabel#StatusPill {
    border-radius: 10px;
    padding: 2px 9px;
    font-size: 11px;
    font-weight: 700;
}
QScrollArea {
    border: none;
    background-color: transparent;
}
"""

LIGHT_QSS = """
QMainWindow, QDialog {
    background-color: #f6f8fa;
    color: #1f2328;
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 13px;
}
QWidget {
    color: #1f2328;
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 13px;
}
QStackedWidget, QScrollArea, QWidget#ScrollContent {
    background-color: #f6f8fa;
}
QLabel, QCheckBox, QRadioButton {
    background-color: transparent;
}
QFrame#Sidebar {
    background-color: #ffffff;
    border-right: 1px solid #d0d7de;
}
QFrame#Card, QGroupBox {
    background-color: #ffffff;
    border: 1px solid #d0d7de;
    border-radius: 10px;
}
QGroupBox {
    margin-top: 10px;
    padding-top: 14px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: #656d76;
}
QPushButton {
    background-color: #f6f8fa;
    color: #1f2328;
    border: 1px solid #d0d7de;
    border-radius: 7px;
    padding: 7px 14px;
    font-weight: 600;
}
QPushButton:hover {
    background-color: #eaeef2;
    border-color: #8c959f;
}
QPushButton:disabled {
    color: #8c959f;
    background-color: #f6f8fa;
}
QPushButton#PrimaryBtn {
    background-color: #1f883d;
    border-color: #1a7f37;
    color: #ffffff;
}
QPushButton#PrimaryBtn:hover {
    background-color: #1a7f37;
}
QPushButton#DangerBtn {
    background-color: #cf222e;
    border-color: #a40e26;
    color: #ffffff;
}
QPushButton#NavBtn {
    text-align: left;
    padding: 10px 14px;
    border: none;
    border-radius: 8px;
    background-color: transparent;
    color: #656d76;
    font-size: 13px;
}
QPushButton#NavBtn:hover {
    background-color: #eaeef2;
    color: #1f2328;
}
QPushButton#NavBtn[active="true"] {
    background-color: #ddf4ff;
    color: #0969da;
    border-left: 3px solid #0969da;
}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit {
    background-color: #ffffff;
    color: #1f2328;
    border: 1px solid #d0d7de;
    border-radius: 6px;
    padding: 6px 10px;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QPlainTextEdit:focus {
    border-color: #0969da;
}
QProgressBar {
    background-color: #eaeef2;
    border: 1px solid #d0d7de;
    border-radius: 6px;
    text-align: center;
    height: 18px;
    color: #1f2328;
    font-weight: 600;
}
QProgressBar::chunk {
    background-color: #0969da;
    border-radius: 5px;
}
QLabel#Muted {
    color: #656d76;
}
QLabel#SectionTitle {
    font-size: 18px;
    font-weight: 700;
    color: #1f2328;
}
QLabel#StatusPill {
    border-radius: 10px;
    padding: 2px 9px;
    font-size: 11px;
    font-weight: 700;
}
QScrollArea {
    border: none;
    background-color: transparent;
}
"""
