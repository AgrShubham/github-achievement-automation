"""Pure-HTTPS GitHub REST and GraphQL client with retry and rate-limit handling."""

from __future__ import annotations

import http.client
import json
import random
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

RETRY_AFTER_RE = re.compile(r"retry[- ]after[:\s]+(\d+)", re.IGNORECASE)


class GitHubApiError(RuntimeError):
    """Raised on GitHub REST/GraphQL errors after retries are exhausted."""

    def __init__(self, message: str, status_code: int | None = None, body: str = "") -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body


def is_rate_limit_response(status_code: int | None, text: str) -> bool:
    if status_code == 429:
        return True
    lowered = (text or "").lower()
    if status_code == 403 and any(
        k in lowered
        for k in ("rate limit", "secondary rate limit", "abuse detection", "try again later")
    ):
        return True
    return "secondary rate limit" in lowered or "api rate limit exceeded" in lowered


def compute_backoff_seconds(
    attempt: int,
    base_backoff: float = 4.0,
    retry_after_header: str | None = None,
    body_text: str = "",
) -> float:
    if retry_after_header and retry_after_header.strip().isdigit():
        return max(1.0, float(int(retry_after_header.strip())))
    match = RETRY_AFTER_RE.search(body_text or "")
    if match:
        return max(1.0, float(int(match.group(1))))
    return (base_backoff * (2 ** attempt)) + random.uniform(0.25, 1.25)


class GitHubClient:
    """Thread-safe pure-Python GitHub REST + GraphQL client."""

    def __init__(
        self,
        token: str,
        api_base: str = "https://api.github.com",
        max_retries: int = 5,
        timeout: int = 30,
    ) -> None:
        self.token = token.strip()
        self.api_base = api_base.rstrip("/")
        self.max_retries = max_retries
        self.timeout = timeout
        self.last_scopes: tuple[str, ...] = ()
        self.last_rate_remaining: int | None = None

    def request_raw(
        self,
        method: str,
        path_or_url: str,
        payload: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, str], Any]:
        url = path_or_url if path_or_url.startswith("http") else f"{self.api_base}/{path_or_url.lstrip('/')}"
        raw_body = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "GitHubAchievementStudio/1.0",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if raw_body is not None:
            headers["Content-Type"] = "application/json"
        if extra_headers:
            headers.update(extra_headers)

        for attempt in range(self.max_retries + 1):
            req = urllib.request.Request(url, data=raw_body, headers=headers, method=method.upper())
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    resp_headers = {k.lower(): v for k, v in resp.headers.items()}
                    self._capture_headers(resp_headers)
                    raw_text = resp.read().decode("utf-8", errors="replace")
                    parsed = json.loads(raw_text) if raw_text.strip() else {}
                    return resp.status, resp_headers, parsed
            except urllib.error.HTTPError as exc:
                resp_headers = {k.lower(): v for k, v in (exc.headers.items() if exc.headers else [])}
                self._capture_headers(resp_headers)
                err_text = exc.read().decode("utf-8", errors="replace")
                transient_merge = exc.code in (405, 409, 422) and any(
                    marker in err_text.lower()
                    for marker in ("not mergeable", "mergeability", "base branch was modified", "try again")
                )
                if attempt < self.max_retries and (
                    is_rate_limit_response(exc.code, err_text)
                    or transient_merge
                    or exc.code in (500, 502, 503, 504)
                ):
                    wait_s = (
                        2.0
                        if transient_merge and not is_rate_limit_response(exc.code, err_text)
                        else compute_backoff_seconds(
                            attempt,
                            retry_after_header=resp_headers.get("retry-after"),
                            body_text=err_text,
                        )
                    )
                    time.sleep(wait_s)
                    continue
                raise GitHubApiError(
                    f"GitHub HTTP {exc.code} on {method} {url}: {err_text}",
                    status_code=exc.code,
                    body=err_text,
                ) from exc
            except (
                urllib.error.URLError,
                http.client.HTTPException,
                ssl.SSLError,
                TimeoutError,
                OSError,
            ) as exc:
                if attempt < self.max_retries:
                    time.sleep(compute_backoff_seconds(attempt, base_backoff=2.0))
                    continue
                raise GitHubApiError(f"Network error on {method} {url}: {exc}") from exc

        raise GitHubApiError(f"Exhausted retries on {method} {url}")

    def _capture_headers(self, headers: dict[str, str]) -> None:
        if "x-oauth-scopes" in headers:
            scopes = [s.strip() for s in headers["x-oauth-scopes"].split(",") if s.strip()]
            self.last_scopes = tuple(scopes)
        if "x-ratelimit-remaining" in headers and headers["x-ratelimit-remaining"].isdigit():
            self.last_rate_remaining = int(headers["x-ratelimit-remaining"])

    def rest(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        target = path
        if params:
            qs = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
            if qs:
                sep = "&" if "?" in target else "?"
                target = f"{target}{sep}{qs}"
        _, _, data = self.request_raw(method, target, payload=payload)
        return data

    def graphql(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        _, _, resp = self.request_raw(
            "POST",
            "/graphql",
            payload={"query": query, "variables": variables or {}},
        )
        if isinstance(resp, dict) and resp.get("errors"):
            raise GitHubApiError(f"GraphQL error: {json.dumps(resp['errors'])}", body=json.dumps(resp))
        return (resp or {}).get("data", {}) if isinstance(resp, dict) else {}

    def get_rate_limit(self) -> tuple[int, int]:
        data = self.rest("GET", "/rate_limit")
        core = (data or {}).get("resources", {}).get("core", {})
        return int(core.get("remaining", 0)), int(core.get("limit", 5000))
