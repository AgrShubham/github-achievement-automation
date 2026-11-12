"""Windows DPAPI token encryption and secret-redaction helpers."""

from __future__ import annotations

import base64
import binascii
import ctypes
from ctypes import wintypes
import re
import sys
from typing import Iterable

_GITHUB_TOKEN_RE = re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{12,}|github_pat_[A-Za-z0-9_]{16,})\b")


class SecurityError(RuntimeError):
    """Raised when Windows DPAPI encryption or decryption fails."""


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_byte)),
    ]


def _make_blob(raw: bytes) -> tuple[_DataBlob, ctypes.Array[ctypes.c_char]]:
    buf = ctypes.create_string_buffer(raw, len(raw))
    blob = _DataBlob(
        cbData=len(raw),
        pbData=ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte)),
    )
    return blob, buf


def dpapi_encrypt_bytes(raw: bytes, entropy: bytes = b"GitHubAchievementStudio-v1") -> bytes:
    if sys.platform != "win32":
        raise SecurityError("Windows DPAPI is only supported on Windows hosts.")

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    in_blob, _in_buf = _make_blob(raw)
    ent_blob, _ent_buf = _make_blob(entropy)
    out_blob = _DataBlob()

    # CRYPTPROTECT_UI_FORBIDDEN = 0x1
    ok = crypt32.CryptProtectData(
        ctypes.byref(in_blob),
        "GitHubAchievementStudioToken",
        ctypes.byref(ent_blob),
        None,
        None,
        0x1,
        ctypes.byref(out_blob),
    )
    if not ok:
        raise SecurityError(f"CryptProtectData failed with error code {ctypes.GetLastError()}.")
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        kernel32.LocalFree(out_blob.pbData)


def dpapi_decrypt_bytes(encrypted: bytes, entropy: bytes = b"GitHubAchievementStudio-v1") -> bytes:
    if sys.platform != "win32":
        raise SecurityError("Windows DPAPI is only supported on Windows hosts.")

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    in_blob, _in_buf = _make_blob(encrypted)
    ent_blob, _ent_buf = _make_blob(entropy)
    out_blob = _DataBlob()

    ok = crypt32.CryptUnprotectData(
        ctypes.byref(in_blob),
        None,
        ctypes.byref(ent_blob),
        None,
        None,
        0x1,
        ctypes.byref(out_blob),
    )
    if not ok:
        raise SecurityError(f"CryptUnprotectData failed with error code {ctypes.GetLastError()}.")
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        kernel32.LocalFree(out_blob.pbData)


def protect_secret(plaintext: str) -> str:
    encrypted = dpapi_encrypt_bytes(plaintext.encode("utf-8"))
    return base64.b64encode(encrypted).decode("ascii")


def unprotect_secret(encoded: str) -> str:
    try:
        raw = base64.b64decode(encoded.encode("ascii"), validate=True)
        return dpapi_decrypt_bytes(raw).decode("utf-8")
    except (binascii.Error, ValueError, UnicodeError) as exc:
        raise SecurityError(f"Invalid encrypted secret payload: {exc}") from exc


def redact_secrets(text: str, secrets: Iterable[str]) -> str:
    masked = text
    for secret in secrets:
        clean = (secret or "").strip()
        if len(clean) >= 6:
            masked = masked.replace(clean, "***REDACTED***")
    return _GITHUB_TOKEN_RE.sub("***REDACTED***", masked)
