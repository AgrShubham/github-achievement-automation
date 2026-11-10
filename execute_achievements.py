#!/usr/bin/env python3
"""
GitHub Profile Achievement Automation Engine.

Automates earnable GitHub Profile Achievements safely and idempotently in a
dedicated sandbox repository using the GitHub CLI (`gh`), `git`, and the GitHub
REST/GraphQL APIs.

Supported achievements:
  Single-account:
    - Quickdraw: Close an issue within 5 minutes of opening it.
    - Pull Shark: Merge pull requests into the default branch (2 / 16 / 128 / 1,024).
    - YOLO: Merge a pull request without code review (supports optional --reviewer).

  Multi-account (opt-in via flags):
    - Pair Extraordinaire: Merge PRs with validated `Co-authored-by:` trailers (1 / 10 / 24 / 48).
    - Galaxy Brain: Answer Q&A Discussions marked accepted by a second account (2 / 8 / 16 / 32).
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json
import logging
import os
import random
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

PULL_SHARK_TIERS: dict[str, int] = {
    "none": 0,
    "default": 2,
    "bronze": 16,
    "silver": 128,
    "gold": 1024,
}

PAIR_TIERS: dict[str, int] = {
    "default": 1,
    "bronze": 10,
    "silver": 24,
    "gold": 48,
}

GALAXY_TIERS: dict[str, int] = {
    "default": 2,
    "bronze": 8,
    "silver": 16,
    "gold": 32,
}

PLACEHOLDER_EMAIL_DOMAINS = {
    "example.com",
    "example.org",
    "example.net",
    "test.com",
    "fake.com",
    "invalid",
    "localhost",
}

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
COAUTHOR_EMAIL_RE = re.compile(r"^Co-authored-by:\s+.+?<([^>\s]+)>\s*$", re.IGNORECASE | re.MULTILINE)
RETRY_AFTER_RE = re.compile(r"retry[- ]after[:\s]+(\d+)", re.IGNORECASE)

LOG = logging.getLogger("github_achievements")


class AutomationError(RuntimeError):
    """Raised for recoverable/validation failures during achievement automation."""


@dataclasses.dataclass(frozen=True)
class AutomationConfig:
    repo_name: str = "github-achievements-sandbox"
    owner: str | None = None
    actor: str | None = None
    visibility: str = "public"
    pull_shark_count: int = 16
    run_quickdraw: bool = True
    run_yolo: bool = True
    reviewer: str | None = None
    pair_count: int = 0
    coauthor_username: str | None = None
    coauthor_name: str | None = None
    coauthor_email: str | None = None
    allow_custom_email: bool = False
    galaxy_count: int = 0
    helper_token_env: str = "GH_HELPER_TOKEN"
    delay_seconds: float = 2.5
    batch_limit: int | None = None
    max_retries: int = 5
    workdir: Path = Path(".sandbox")
    state_file: Path = Path(".achievements-state.json")
    dry_run: bool = False
    verify_only: bool = False

    @property
    def full_repo(self) -> str:
        if "/" in self.repo_name:
            return self.repo_name
        if not self.owner:
            raise AutomationError("Repository owner is not resolved yet.")
        return f"{self.owner}/{self.repo_name}"

    @property
    def short_repo(self) -> str:
        return self.repo_name.split("/")[-1]


@dataclasses.dataclass
class VerificationSummary:
    owner: str
    repo: str
    merged_prs_count: int
    global_merged_prs_count: int
    coauthored_prs_count: int
    quickdraw_issue_count: int
    accepted_discussion_answers: int
    visible_profile_badges: list[str]
    profile_url: str


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )


def parse_iso_datetime(value: str) -> dt.datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    return dt.datetime.fromisoformat(normalized)


def format_coauthor_trailer(name: str, email: str) -> str:
    clean_name = name.strip()
    clean_email = email.strip()
    if not clean_name:
        raise AutomationError("Co-author name cannot be empty.")
    if not EMAIL_RE.match(clean_email):
        raise AutomationError(f"Invalid co-author email format: {clean_email}")
    return f"Co-authored-by: {clean_name} <{clean_email}>"


def is_placeholder_email(email: str) -> bool:
    parts = email.strip().lower().split("@")
    if len(parts) != 2:
        return True
    domain = parts[1]
    return domain in PLACEHOLDER_EMAIL_DOMAINS or "noreply" in domain and "users.noreply.github.com" not in domain


def build_commit_message(subject: str, body: str = "", coauthor_trailer: str | None = None) -> str:
    lines = [subject.strip()]
    clean_body = body.strip()
    if clean_body:
        lines.extend(["", clean_body])
    if coauthor_trailer:
        lines.extend(["", coauthor_trailer.strip()])
    return "\n".join(lines)


def is_rate_limit_message(text: str) -> bool:
    lowered = text.lower()
    indicators = (
        "secondary rate limit",
        "api rate limit exceeded",
        "rate limit",
        "http 429",
        "status 429",
        "429 too many requests",
        "try again later",
        "abuse detection",
    )
    return any(marker in lowered for marker in indicators)


def extract_retry_after_seconds(text: str, attempt: int, base_backoff: float) -> float:
    match = RETRY_AFTER_RE.search(text)
    if match:
        seconds = int(match.group(1))
        return max(1.0, float(seconds))
    jitter = random.uniform(0.25, 1.5)
    return (base_backoff * (2 ** attempt)) + jitter


def run_subprocess(
    cmd: list[str],
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    check: bool = True,
    timeout: int = 120,
) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    merged_env["GIT_TERMINAL_PROMPT"] = "0"
    if env:
        merged_env.update(env)

    LOG.debug("Exec (%s): %s", cwd or Path.cwd(), " ".join(cmd))
    result = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        env=merged_env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise AutomationError(f"Command failed ({result.returncode}): {' '.join(cmd)}\n{detail}")
    return result


def run_git(
    args: list[str],
    cwd: Path | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    cmd = [
        "git",
        "-c",
        "credential.helper=",
        "-c",
        "credential.helper=!gh auth git-credential",
        *args,
    ]
    return run_subprocess(cmd, cwd=cwd, check=check)


def run_gh_with_retry(
    args: list[str],
    cwd: Path | None = None,
    max_retries: int = 5,
    base_backoff: float = 5.0,
) -> subprocess.CompletedProcess[str]:
    cmd = ["gh", *args]
    for attempt in range(max_retries + 1):
        result = run_subprocess(cmd, cwd=cwd, check=False)
        if result.returncode == 0:
            return result
        combined = f"{result.stderr}\n{result.stdout}".strip()
        transient_merge_error = "not mergeable" in combined.lower() or "base branch was modified" in combined.lower()
        if attempt < max_retries and (is_rate_limit_message(combined) or transient_merge_error):
            wait_s = 2.5 if transient_merge_error and not is_rate_limit_message(combined) else extract_retry_after_seconds(combined, attempt, base_backoff)
            LOG.warning(
                "Transient GitHub error on `%s` (attempt %d/%d): %s. Sleeping %.1fs...",
                " ".join(args[:4]),
                attempt + 1,
                max_retries,
                combined.splitlines()[0] if combined else "unknown error",
                wait_s,
            )
            time.sleep(wait_s)
            continue
        raise AutomationError(f"gh command failed ({result.returncode}): {' '.join(cmd)}\n{combined}")
    raise AutomationError(f"gh command exhausted retries: {' '.join(cmd)}")


def gh_api_json(endpoint: str, method: str = "GET", fields: dict[str, Any] | None = None, max_retries: int = 5) -> Any:
    args = ["api", endpoint, "-X", method]
    if fields:
        for k, v in fields.items():
            if isinstance(v, bool):
                args.extend(["-F", f"{k}={'true' if v else 'false'}"])
            elif isinstance(v, int):
                args.extend(["-F", f"{k}={v}"])
            else:
                args.extend(["-f", f"{k}={v}"])
    res = run_gh_with_retry(args, max_retries=max_retries)
    text = res.stdout.strip()
    return json.loads(text) if text else {}


def gh_graphql(query: str, variables: dict[str, Any] | None = None, max_retries: int = 5) -> dict[str, Any]:
    args = ["api", "graphql", "-f", f"query={query}"]
    if variables:
        for k, v in variables.items():
            if v is None:
                continue
            if isinstance(v, bool):
                args.extend(["-F", f"{k}={'true' if v else 'false'}"])
            elif isinstance(v, int):
                args.extend(["-F", f"{k}={v}"])
            else:
                args.extend(["-f", f"{k}={v}"])
    res = run_gh_with_retry(args, max_retries=max_retries)
    payload = json.loads(res.stdout)
    if payload.get("errors"):
        raise AutomationError(f"GraphQL errors: {json.dumps(payload['errors'])}")
    return payload.get("data", {})


def http_github_api(
    url: str,
    token: str,
    method: str = "GET",
    body: dict[str, Any] | None = None,
    max_retries: int = 5,
    base_backoff: float = 5.0,
) -> Any:
    raw_body = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "github-achievement-automation",
        "Content-Type": "application/json",
    }

    for attempt in range(max_retries + 1):
        req = urllib.request.Request(url, data=raw_body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                text = resp.read().decode("utf-8")
                return json.loads(text) if text else {}
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            if exc.code in (403, 429) and attempt < max_retries and (is_rate_limit_message(err_body) or exc.code == 429):
                retry_header = exc.headers.get("Retry-After")
                wait_s = float(retry_header) if retry_header and retry_header.isdigit() else extract_retry_after_seconds(err_body, attempt, base_backoff)
                LOG.warning("GitHub HTTP %d rate limit; retrying in %.1fs...", exc.code, wait_s)
                time.sleep(wait_s)
                continue
            raise AutomationError(f"GitHub HTTP {exc.code} on {method} {url}: {err_body}") from exc
    raise AutomationError(f"Exhausted HTTP retries on {method} {url}")


def http_graphql_with_token(query: str, variables: dict[str, Any], token: str, max_retries: int = 5) -> dict[str, Any]:
    resp = http_github_api(
        "https://api.github.com/graphql",
        token=token,
        method="POST",
        body={"query": query, "variables": variables},
        max_retries=max_retries,
    )
    if resp.get("errors"):
        raise AutomationError(f"GraphQL error (secondary token): {json.dumps(resp['errors'])}")
    return resp.get("data", {})


def get_primary_gh_token() -> str:
    res = run_gh_with_retry(["auth", "token"])
    token = res.stdout.strip()
    if not token:
        raise AutomationError("Could not obtain token from `gh auth token`.")
    return token


def resolve_user_identity() -> dict[str, Any]:
    user = gh_api_json("user")
    if not user.get("login"):
        raise AutomationError("Unable to determine authenticated GitHub user via `gh api user`.")
    return user


def resolve_coauthor(config: AutomationConfig) -> tuple[str | None, str | None]:
    if config.pair_count <= 0:
        return None, None

    name = config.coauthor_name
    email = config.coauthor_email

    if config.coauthor_username and not email:
        info = gh_api_json(f"users/{config.coauthor_username}")
        uid = info["id"]
        login = info["login"]
        email = f"{uid}+{login}@users.noreply.github.com"
        if not name:
            name = info.get("name") or login

    if not name and config.coauthor_username:
        name = config.coauthor_username
    if not name or not email:
        raise AutomationError(
            "Pair Extraordinaire requires either `--coauthor-username` or both `--coauthor-name` and `--coauthor-email`."
        )
    if not config.allow_custom_email and is_placeholder_email(email):
        raise AutomationError(
            f"Co-author email `{email}` looks like a placeholder/invalid address and will not trigger Pair Extraordinaire. "
            "Provide a real GitHub account's verified/noreply email (or pass `--allow-custom-email` to override)."
        )
    format_coauthor_trailer(name, email)
    return name, email


def validate_tools_and_preflight(config: AutomationConfig) -> tuple[AutomationConfig, dict[str, Any]]:
    for binary in ("git", "gh"):
        if not shutil.which(binary):
            raise AutomationError(f"Required tool `{binary}` was not found on PATH.")

    auth_res = run_subprocess(["gh", "auth", "status"], check=False)
    if auth_res.returncode != 0:
        raise AutomationError(f"GitHub CLI is not authenticated. Run `gh auth login`.\n{auth_res.stderr}")

    user = resolve_user_identity()
    login = user["login"]

    resolved_owner = config.owner or (config.repo_name.split("/")[0] if "/" in config.repo_name else login)
    if resolved_owner != login and not config.verify_only:
        LOG.info("Target repository owner is `%s` while authenticated user is `%s`.", resolved_owner, login)

    rate = gh_api_json("rate_limit").get("resources", {}).get("core", {})
    remaining = rate.get("remaining", 0)
    LOG.info("Authenticated as @%s (id=%s). Core API rate limit remaining: %s/%s.", login, user.get("id"), remaining, rate.get("limit"))
    if remaining < 50 and not config.verify_only and not config.dry_run:
        raise AutomationError(f"GitHub API rate limit is too low ({remaining} remaining). Wait for reset before running.")

    updated = dataclasses.replace(config, owner=resolved_owner, actor=login)

    if updated.pair_count > 0:
        co_name, co_email = resolve_coauthor(updated)
        updated = dataclasses.replace(updated, coauthor_name=co_name, coauthor_email=co_email)

    if updated.galaxy_count > 0 and not updated.verify_only:
        helper_token = os.environ.get(updated.helper_token_env, "").strip()
        if not helper_token:
            raise AutomationError(
                f"Galaxy Brain requires a second GitHub account token in environment variable `{updated.helper_token_env}`."
            )
        helper_user = http_github_api("https://api.github.com/user", token=helper_token)
        helper_login = helper_user.get("login")
        if not helper_login:
            raise AutomationError("Failed to authenticate helper token against GitHub `/user`.")
        if helper_login.lower() == login.lower():
            raise AutomationError(
                f"Helper token belongs to @{helper_login}, which is the same as the primary account @{login}. "
                "GitHub blocks self-accepted answers from counting toward Galaxy Brain."
            )
        LOG.info("Validated secondary Galaxy Brain account: @%s", helper_login)

    return updated, user


def fetch_repo_metadata(full_repo: str) -> dict[str, Any] | None:
    res = run_subprocess(
        [
            "gh",
            "repo",
            "view",
            full_repo,
            "--json",
            "name,owner,visibility,isPrivate,defaultBranchRef,hasDiscussionsEnabled,url",
        ],
        check=False,
    )
    if res.returncode != 0:
        return None
    return json.loads(res.stdout)


def ensure_sandbox_repo(config: AutomationConfig, user: dict[str, Any]) -> tuple[Path, str]:
    full_repo = config.full_repo
    local_dir = config.workdir / config.short_repo
    meta = fetch_repo_metadata(full_repo)

    if meta is None:
        if config.dry_run:
            LOG.info("[DRY RUN] Would create %s repository `%s` with initial README.", config.visibility, full_repo)
            return local_dir, "main"
        LOG.info("Creating %s GitHub repository `%s`...", config.visibility, full_repo)
        vis_flag = f"--{config.visibility}"
        run_gh_with_retry(
            [
                "repo",
                "create",
                full_repo,
                vis_flag,
                "--description",
                "Automated GitHub profile achievements sandbox repository",
                "--add-readme",
            ],
            max_retries=config.max_retries,
        )
        # Wait briefly for GitHub to finalize initial commit/default branch
        for _ in range(8):
            meta = fetch_repo_metadata(full_repo)
            if meta and meta.get("defaultBranchRef"):
                break
            time.sleep(1.0)
    else:
        LOG.info("Using existing repository `%s` (%s).", full_repo, meta.get("visibility", "unknown"))

    default_branch = ((meta or {}).get("defaultBranchRef") or {}).get("name") or "main"

    if config.dry_run:
        LOG.info("[DRY RUN] Would clone/sync `%s` (branch `%s`) into `%s`.", full_repo, default_branch, local_dir)
        return local_dir, default_branch

    config.workdir.mkdir(parents=True, exist_ok=True)
    remote_url = f"https://github.com/{full_repo}.git"

    if (local_dir / ".git").exists():
        LOG.info("Updating existing local clone at `%s`...", local_dir)
        run_git(["fetch", "origin", "--prune"], cwd=local_dir)
        run_git(["checkout", default_branch], cwd=local_dir)
        run_git(["pull", "--ff-only", "origin", default_branch], cwd=local_dir)
    else:
        if local_dir.exists():
            shutil.rmtree(local_dir)
        LOG.info("Cloning `%s` into `%s`...", remote_url, local_dir)
        run_git(["clone", remote_url, str(local_dir)])

    # Ensure repo-local git author matches authenticated account if missing
    local_name = run_git(["config", "user.name"], cwd=local_dir, check=False).stdout.strip()
    local_email = run_git(["config", "user.email"], cwd=local_dir, check=False).stdout.strip()
    if not local_name:
        run_git(["config", "user.name", user.get("name") or user["login"]], cwd=local_dir)
    if not local_email:
        fallback_email = user.get("email") or f"{user['id']}+{user['login']}@users.noreply.github.com"
        run_git(["config", "user.email", fallback_email], cwd=local_dir)

    # Handle edge case where repository exists but is completely empty (no commits yet)
    has_head = run_git(["rev-parse", "--verify", "HEAD"], cwd=local_dir, check=False).returncode == 0
    if not has_head:
        LOG.info("Repository has no commits yet; pushing initial README.md to `%s`...", default_branch)
        run_git(["checkout", "-B", default_branch], cwd=local_dir)
        readme = local_dir / "README.md"
        readme.write_text(
            f"# {config.short_repo}\n\nSandbox repository for automated GitHub profile achievements.\n",
            encoding="utf-8",
        )
        run_git(["add", "README.md"], cwd=local_dir)
        run_git(["commit", "-m", "chore: initialize achievement sandbox repository"], cwd=local_dir)
        run_git(["push", "-u", "origin", default_branch], cwd=local_dir)

    return local_dir, default_branch


def fetch_merged_prs_stats(owner: str, repo: str, author_login: str) -> list[dict[str, Any]]:
    query = """
    query($owner: String!, $repo: String!, $cursor: String) {
      repository(owner: $owner, name: $repo) {
        pullRequests(states: MERGED, first: 100, after: $cursor, orderBy: {field: CREATED_AT, direction: ASC}) {
          pageInfo {
            hasNextPage
            endCursor
          }
          nodes {
            number
            title
            headRefName
            mergedAt
            author { login }
            commits(first: 10) {
              nodes {
                commit {
                  message
                }
              }
            }
          }
        }
      }
    }
    """
    results: list[dict[str, Any]] = []
    cursor: str | None = None
    while True:
        data = gh_graphql(query, {"owner": owner, "repo": repo, "cursor": cursor})
        pr_conn = (data.get("repository") or {}).get("pullRequests") or {}
        for node in pr_conn.get("nodes") or []:
            node_author = (node.get("author") or {}).get("login")
            if node_author and node_author.lower() == author_login.lower():
                results.append(node)
        page_info = pr_conn.get("pageInfo") or {}
        if not page_info.get("hasNextPage"):
            break
        cursor = page_info.get("endCursor")
    return results


def count_coauthored_prs(merged_prs: list[dict[str, Any]], coauthor_email: str | None = None) -> int:
    count = 0
    for pr in merged_prs:
        commits = (pr.get("commits") or {}).get("nodes") or []
        matched = False
        for c in commits:
            msg = ((c or {}).get("commit") or {}).get("message") or ""
            found_emails = [m.lower() for m in COAUTHOR_EMAIL_RE.findall(msg)]
            if not found_emails:
                continue
            if coauthor_email is None or coauthor_email.lower() in found_emails:
                matched = True
                break
        if matched:
            count += 1
    return count


def fetch_quickdraw_issues(full_repo: str) -> list[dict[str, Any]]:
    res = run_gh_with_retry(
        [
            "issue",
            "list",
            "--repo",
            full_repo,
            "--state",
            "closed",
            "--limit",
            "50",
            "--json",
            "number,title,createdAt,closedAt,url",
        ]
    )
    issues = json.loads(res.stdout or "[]")
    qualifying: list[dict[str, Any]] = []
    for issue in issues:
        created = parse_iso_datetime(issue["createdAt"])
        closed = parse_iso_datetime(issue["closedAt"])
        delta = (closed - created).total_seconds()
        if 0 <= delta < 300:
            issue["elapsed_seconds"] = round(delta, 2)
            qualifying.append(issue)
    return qualifying


def save_state(state_file: Path, payload: dict[str, Any]) -> None:
    state_file.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def run_quickdraw(config: AutomationConfig) -> str | None:
    if not config.run_quickdraw:
        return None
    if config.dry_run:
        LOG.info("[DRY RUN] Would check/create & immediately close a Quickdraw issue on `%s`.", config.full_repo)
        return "dry-run://quickdraw-issue"

    existing = fetch_quickdraw_issues(config.full_repo)
    if existing:
        first = existing[0]
        LOG.info(
            "Quickdraw already satisfied by issue #%s (%s, closed in %ss).",
            first["number"],
            first["url"],
            first["elapsed_seconds"],
        )
        return first["url"]

    LOG.info("Creating Quickdraw verification issue on `%s`...", config.full_repo)
    create_res = run_gh_with_retry(
        [
            "issue",
            "create",
            "--repo",
            config.full_repo,
            "--title",
            "[Achievement] Quickdraw verification",
            "--body",
            "Automated issue created and closed within 5 minutes for the GitHub Quickdraw achievement.",
        ],
        max_retries=config.max_retries,
    )
    issue_url = create_res.stdout.strip().splitlines()[-1].strip()
    LOG.info("Created issue %s; closing immediately...", issue_url)

    run_gh_with_retry(
        [
            "issue",
            "close",
            issue_url,
            "--repo",
            config.full_repo,
            "--reason",
            "completed",
            "--comment",
            "Closed immediately (< 5 minutes) to satisfy Quickdraw achievement criteria.",
        ],
        max_retries=config.max_retries,
    )

    view_res = run_gh_with_retry(
        ["issue", "view", issue_url, "--repo", config.full_repo, "--json", "createdAt,closedAt,url"],
        max_retries=config.max_retries,
    )
    info = json.loads(view_res.stdout)
    elapsed = (parse_iso_datetime(info["closedAt"]) - parse_iso_datetime(info["createdAt"])).total_seconds()
    if elapsed >= 300:
        raise AutomationError(f"Quickdraw issue took {elapsed:.1f}s to close (must be < 300s).")
    LOG.info("Quickdraw issue verified: closed in %.1fs (%s).", elapsed, issue_url)
    return issue_url


def execute_single_pr_cycle(
    config: AutomationConfig,
    local_dir: Path,
    default_branch: str,
    branch_name: str,
    log_entry: str,
    commit_subject: str,
    pr_title: str,
    pr_body: str,
    coauthor_trailer: str | None = None,
    reviewer: str | None = None,
) -> int:
    run_git(["checkout", default_branch], cwd=local_dir)
    run_git(["pull", "--ff-only", "origin", default_branch], cwd=local_dir)
    run_git(["checkout", "-B", branch_name], cwd=local_dir)

    log_file = local_dir / "ACHIEVEMENTS_LOG.md"
    if not log_file.exists():
        log_file.write_text("# Achievement Automation Log\n\n", encoding="utf-8")
    with log_file.open("a", encoding="utf-8") as fh:
        fh.write(log_entry + "\n")

    commit_msg = build_commit_message(commit_subject, coauthor_trailer=coauthor_trailer)
    run_git(["add", "ACHIEVEMENTS_LOG.md"], cwd=local_dir)
    run_git(["commit", "-m", commit_msg], cwd=local_dir)
    run_git(["push", "-u", "origin", branch_name, "--force-with-lease"], cwd=local_dir)

    create_args = [
        "pr",
        "create",
        "--repo",
        config.full_repo,
        "--base",
        default_branch,
        "--head",
        branch_name,
        "--title",
        pr_title,
        "--body",
        pr_body,
    ]
    if reviewer:
        create_args.extend(["--reviewer", reviewer])

    create_res = run_gh_with_retry(create_args, cwd=local_dir, max_retries=config.max_retries)
    pr_url = create_res.stdout.strip().splitlines()[-1].strip()
    pr_num_match = re.search(r"/pull/(\d+)$", pr_url)
    pr_number = int(pr_num_match.group(1)) if pr_num_match else 0

    # Brief pause so GitHub computes PR mergeability cleanly
    time.sleep(0.8)

    run_gh_with_retry(
        [
            "pr",
            "merge",
            pr_url,
            "--repo",
            config.full_repo,
            "--merge",
            "--delete-branch",
        ],
        cwd=local_dir,
        max_retries=config.max_retries,
    )

    run_git(["checkout", default_branch], cwd=local_dir)
    run_git(["pull", "--ff-only", "origin", default_branch], cwd=local_dir)
    run_git(["branch", "-D", branch_name], cwd=local_dir, check=False)
    return pr_number


def run_pr_achievements(
    config: AutomationConfig,
    local_dir: Path,
    default_branch: str,
    state: dict[str, Any],
) -> tuple[int, int]:
    assert config.owner is not None
    actor = config.actor or config.owner
    existing_prs = [] if config.dry_run and fetch_repo_metadata(config.full_repo) is None else fetch_merged_prs_stats(
        config.owner, config.short_repo, actor
    )
    existing_total = len(existing_prs)
    existing_pair = count_coauthored_prs(existing_prs, config.coauthor_email)

    pair_needed = max(0, config.pair_count - existing_pair)
    expected_total_after_pair = existing_total + pair_needed

    effective_pull_shark_target = config.pull_shark_count
    if config.run_yolo and effective_pull_shark_target == 0 and expected_total_after_pair == 0:
        effective_pull_shark_target = 1

    pull_shark_needed = max(0, effective_pull_shark_target - expected_total_after_pair)

    total_planned = pair_needed + pull_shark_needed
    if config.batch_limit is not None:
        total_planned = min(total_planned, config.batch_limit)

    LOG.info(
        "PR plan for `%s`: existing merged=%d (co-authored=%d) | to create: pair=%d, pull_shark=%d (batch cap=%s).",
        config.full_repo,
        existing_total,
        existing_pair,
        pair_needed,
        pull_shark_needed,
        config.batch_limit if config.batch_limit is not None else "none",
    )

    if config.dry_run:
        if pair_needed > 0:
            trailer = format_coauthor_trailer(config.coauthor_name or "", config.coauthor_email or "")
            LOG.info("[DRY RUN] Would create & merge %d Pair Extraordinaire PR(s) with trailer `%s`.", pair_needed, trailer)
        if pull_shark_needed > 0:
            LOG.info("[DRY RUN] Would create & merge %d Pull Shark / YOLO PR(s) into `%s`.", pull_shark_needed, default_branch)
        return existing_total, 0

    created_pair = 0
    created_pull = 0
    remaining_budget = config.batch_limit if config.batch_limit is not None else total_planned
    seq = existing_total + 1

    # 1. Pair Extraordinaire PRs (also count toward Pull Shark & YOLO)
    if pair_needed > 0 and remaining_budget > 0:
        trailer = format_coauthor_trailer(config.coauthor_name or "", config.coauthor_email or "")
        to_run = min(pair_needed, remaining_budget)
        for idx in range(1, to_run + 1):
            ts = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            branch = f"achievement/pair-{seq:04d}-{ts.lower()}"
            entry = f"- [{ts}] Milestone #{seq:04d} — Pair Extraordinaire + Pull Shark (`{branch}`)"
            pr_num = execute_single_pr_cycle(
                config=config,
                local_dir=local_dir,
                default_branch=default_branch,
                branch_name=branch,
                log_entry=entry,
                commit_subject=f"chore(achievements): pair milestone #{seq:04d}",
                pr_title=f"chore(achievements): pair milestone #{seq:04d}",
                pr_body="Automated co-authored milestone PR for Pair Extraordinaire and Pull Shark.",
                coauthor_trailer=trailer,
                reviewer=config.reviewer if seq == 1 else None,
            )
            created_pair += 1
            remaining_budget -= 1
            seq += 1
            state["last_pr_number"] = pr_num
            state["pair_prs_created"] = state.get("pair_prs_created", 0) + 1
            save_state(config.state_file, state)
            LOG.info("Merged Pair Extraordinaire PR #%s (%d/%d).", pr_num, created_pair, to_run)
            if remaining_budget > 0 or pull_shark_needed > 0:
                time.sleep(config.delay_seconds)

    # 2. Pull Shark + YOLO PRs
    if pull_shark_needed > 0 and remaining_budget > 0:
        to_run = min(pull_shark_needed, remaining_budget)
        for idx in range(1, to_run + 1):
            ts = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            branch = f"achievement/pr-{seq:04d}-{ts.lower()}"
            entry = f"- [{ts}] Milestone #{seq:04d} — Pull Shark / YOLO (`{branch}`)"
            pr_num = execute_single_pr_cycle(
                config=config,
                local_dir=local_dir,
                default_branch=default_branch,
                branch_name=branch,
                log_entry=entry,
                commit_subject=f"chore(achievements): milestone #{seq:04d}",
                pr_title=f"chore(achievements): milestone #{seq:04d}",
                pr_body="Automated milestone PR for Pull Shark and YOLO profile achievements.",
                coauthor_trailer=None,
                reviewer=config.reviewer if (seq == 1 and config.reviewer) else None,
            )
            created_pull += 1
            remaining_budget -= 1
            seq += 1
            state["last_pr_number"] = pr_num
            state["pull_shark_prs_created"] = state.get("pull_shark_prs_created", 0) + 1
            save_state(config.state_file, state)
            LOG.info("Merged Pull Shark PR #%s (%d/%d).", pr_num, created_pull, to_run)
            if idx < to_run:
                time.sleep(config.delay_seconds)

    return existing_total, created_pair + created_pull


def fetch_accepted_discussion_answers(owner: str, repo: str, answer_author: str) -> int:
    query = """
    query($owner: String!, $repo: String!, $cursor: String) {
      repository(owner: $owner, name: $repo) {
        hasDiscussionsEnabled
        discussions(first: 50, after: $cursor, answered: true) {
          pageInfo { hasNextPage endCursor }
          nodes {
            number
            answer {
              author { login }
            }
          }
        }
      }
    }
    """
    count = 0
    cursor: str | None = None
    while True:
        data = gh_graphql(query, {"owner": owner, "repo": repo, "cursor": cursor})
        repo_node = data.get("repository") or {}
        if not repo_node.get("hasDiscussionsEnabled"):
            return 0
        disc_conn = repo_node.get("discussions") or {}
        for node in disc_conn.get("nodes") or []:
            ans_login = ((node.get("answer") or {}).get("author") or {}).get("login")
            if ans_login and ans_login.lower() == answer_author.lower():
                count += 1
        page_info = disc_conn.get("pageInfo") or {}
        if not page_info.get("hasNextPage"):
            break
        cursor = page_info.get("endCursor")
    return count


def run_galaxy_brain(config: AutomationConfig) -> int:
    if config.galaxy_count <= 0:
        return 0
    assert config.owner is not None
    actor = config.actor or config.owner
    if config.dry_run:
        LOG.info(
            "[DRY RUN] Would enable Discussions on `%s` and run %d Galaxy Brain Q&A cycle(s) via `%s`.",
            config.full_repo,
            config.galaxy_count,
            config.helper_token_env,
        )
        return 0

    helper_token = os.environ[config.helper_token_env].strip()
    primary_token = get_primary_gh_token()

    # Enable Discussions if disabled
    repo_meta = fetch_repo_metadata(config.full_repo)
    if repo_meta and not repo_meta.get("hasDiscussionsEnabled"):
        LOG.info("Enabling GitHub Discussions on `%s`...", config.full_repo)
        gh_api_json(f"repos/{config.full_repo}", method="PATCH", fields={"has_discussions": True})
        time.sleep(1.5)

    existing_accepted = fetch_accepted_discussion_answers(config.owner, config.short_repo, actor)
    needed = max(0, config.galaxy_count - existing_accepted)
    if needed == 0:
        LOG.info("Galaxy Brain already has %d accepted answers (>= target %d).", existing_accepted, config.galaxy_count)
        return 0

    cat_query = """
    query($owner: String!, $repo: String!) {
      repository(owner: $owner, name: $repo) {
        id
        discussionCategories(first: 25) {
          nodes { id name isAnswerable }
        }
      }
    }
    """
    cat_data = gh_graphql(cat_query, {"owner": config.owner, "repo": config.short_repo})
    repo_id = cat_data["repository"]["id"]
    categories = cat_data["repository"]["discussionCategories"]["nodes"]
    answerable = [c for c in categories if c.get("isAnswerable")]
    if not answerable:
        raise AutomationError("No answerable (Q&A) discussion category found in the repository.")
    category_id = answerable[0]["id"]

    create_disc_mut = """
    mutation($repositoryId: ID!, $categoryId: ID!, $title: String!, $body: String!) {
      createDiscussion(input: {repositoryId: $repositoryId, categoryId: $categoryId, title: $title, body: $body}) {
        discussion { id number url }
      }
    }
    """
    add_comment_mut = """
    mutation($discussionId: ID!, $body: String!) {
      addDiscussionComment(input: {discussionId: $discussionId, body: $body}) {
        comment { id url }
      }
    }
    """
    mark_answer_mut = """
    mutation($id: ID!) {
      markDiscussionCommentAsAnswer(input: {id: $id}) {
        discussion { id }
      }
    }
    """

    created = 0
    for i in range(1, needed + 1):
        idx = existing_accepted + i
        disc_res = http_graphql_with_token(
            create_disc_mut,
            {
                "repositoryId": repo_id,
                "categoryId": category_id,
                "title": f"[Achievement] Galaxy Brain Q&A #{idx:03d}",
                "body": "Automated Q&A discussion question for Galaxy Brain verification.",
            },
            token=helper_token,
        )
        discussion = disc_res["createDiscussion"]["discussion"]
        comment_res = http_graphql_with_token(
            add_comment_mut,
            {
                "discussionId": discussion["id"],
                "body": f"Verified automated answer #{idx:03d} for Galaxy Brain achievement.",
            },
            token=primary_token,
        )
        comment_id = comment_res["addDiscussionComment"]["comment"]["id"]
        http_graphql_with_token(mark_answer_mut, {"id": comment_id}, token=helper_token)
        created += 1
        LOG.info("Accepted Galaxy Brain answer %d/%d on Discussion #%s.", created, needed, discussion["number"])
        if i < needed:
            time.sleep(config.delay_seconds)
    return created


BADGE_CARD_RE = re.compile(
    r'class="achievement-badge-card"[\s\S]{0,400}?<h3[^>]*>([^<]+)</h3>(?:\s*<span[^>]*achievement-tier-label[^>]*>\s*([^<\s]+)\s*</span>)?',
    re.IGNORECASE,
)


def parse_achievement_badges(html: str) -> list[str]:
    badges: list[str] = []
    for name, tier in BADGE_CARD_RE.findall(html):
        clean_name = name.strip()
        clean_tier = tier.strip()
        label = f"{clean_name} ({clean_tier})" if clean_tier else clean_name
        if label not in badges:
            badges.append(label)
    if not badges:
        for item in re.findall(r'alt="Achievement:\s*([^"]+)"', html):
            clean_item = item.strip()
            if clean_item and clean_item not in badges:
                badges.append(clean_item)
    return badges


def fetch_global_merged_prs_count(actor: str, max_retries: int = 5) -> int:
    data = gh_api_json(
        f"search/issues?q=is:pr+author:{actor}+is:merged&per_page=1",
        max_retries=max_retries,
    )
    return int(data.get("total_count", 0))


def scrape_profile_achievements(username: str) -> list[str]:
    badges: list[str] = []
    for url in (
        f"https://github.com/{username}?tab=achievements",
        f"https://github.com/{username}",
    ):
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                html = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                continue
            LOG.warning("HTTP %d checking profile URL %s", exc.code, url)
            continue
        parsed = parse_achievement_badges(html)
        for item in parsed:
            if item not in badges:
                badges.append(item)
        if badges:
            break
    return badges


def verify_achievements(config: AutomationConfig) -> VerificationSummary:
    assert config.owner is not None
    actor = config.actor or config.owner
    meta = fetch_repo_metadata(config.full_repo)
    merged_count = 0
    coauthored_count = 0
    quickdraw_count = 0
    accepted_answers = 0

    if meta is not None:
        merged_prs = fetch_merged_prs_stats(config.owner, config.short_repo, actor)
        merged_count = len(merged_prs)
        coauthored_count = count_coauthored_prs(merged_prs, config.coauthor_email)
        quickdraw_count = len(fetch_quickdraw_issues(config.full_repo))
        accepted_answers = fetch_accepted_discussion_answers(config.owner, config.short_repo, actor)

    global_merged_count = fetch_global_merged_prs_count(actor, max_retries=config.max_retries)
    badges = scrape_profile_achievements(actor)
    return VerificationSummary(
        owner=actor,
        repo=config.full_repo,
        merged_prs_count=merged_count,
        global_merged_prs_count=global_merged_count,
        coauthored_prs_count=coauthored_count,
        quickdraw_issue_count=quickdraw_count,
        accepted_discussion_answers=accepted_answers,
        visible_profile_badges=badges,
        profile_url=f"https://github.com/{actor}?tab=achievements",
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Automate earnable GitHub Profile Achievements safely in a sandbox repository."
    )
    parser.add_argument("--repo", default="github-achievements-sandbox", help="Sandbox repo name or owner/repo.")
    parser.add_argument("--visibility", choices=("public", "private"), default="public", help="Repository visibility.")
    parser.add_argument(
        "--pull-shark-target",
        choices=tuple(PULL_SHARK_TIERS.keys()),
        default="bronze",
        help="Target Pull Shark tier (default=2, bronze=16, silver=128, gold=1024, none=0).",
    )
    parser.add_argument("--pr-count", type=int, default=None, help="Explicit merged PR target (overrides --pull-shark-target).")
    parser.add_argument("--no-quickdraw", action="store_true", help="Skip Quickdraw issue automation.")
    parser.add_argument("--no-yolo", action="store_true", help="Skip YOLO check when PR target is 0.")
    parser.add_argument("--reviewer", default=None, help="Optional collaborator username to request as unreviewed PR reviewer.")
    parser.add_argument("--pair-count", type=int, default=0, help="Target Pair Extraordinaire co-authored merged PRs (0 to skip).")
    parser.add_argument("--coauthor-username", default=None, help="GitHub username of co-author (resolves noreply email via API).")
    parser.add_argument("--coauthor-name", default=None, help="Co-author display name.")
    parser.add_argument("--coauthor-email", default=None, help="Co-author verified or GitHub noreply email.")
    parser.add_argument("--allow-custom-email", action="store_true", help="Allow custom co-author email validation override.")
    parser.add_argument("--galaxy-count", type=int, default=0, help="Target Galaxy Brain accepted discussion answers (0 to skip).")
    parser.add_argument("--helper-token-env", default="GH_HELPER_TOKEN", help="Env var holding second GitHub account token.")
    parser.add_argument("--delay-seconds", type=float, default=2.5, help="Pause between PR/discussion cycles.")
    parser.add_argument("--batch-limit", type=int, default=None, help="Max PRs to create in this single run.")
    parser.add_argument("--max-retries", type=int, default=5, help="Max retries on rate limits or transient API errors.")
    parser.add_argument("--workdir", type=Path, default=Path(".sandbox"), help="Local directory for cloning sandbox repo.")
    parser.add_argument("--state-file", type=Path, default=Path(".achievements-state.json"), help="Checkpoint state file.")
    parser.add_argument("--dry-run", action="store_true", help="Print plan without modifying GitHub or local git repos.")
    parser.add_argument("--verify-only", action="store_true", help="Verify existing repo activity and public profile badges only.")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging.")
    return parser.parse_args(argv)


def config_from_args(ns: argparse.Namespace) -> AutomationConfig:
    if ns.delay_seconds < 0:
        raise AutomationError("--delay-seconds cannot be negative.")
    if ns.pair_count < 0 or ns.galaxy_count < 0:
        raise AutomationError("Counts cannot be negative.")
    if ns.batch_limit is not None and ns.batch_limit <= 0:
        raise AutomationError("--batch-limit must be positive.")

    pull_count = ns.pr_count if ns.pr_count is not None else PULL_SHARK_TIERS[ns.pull_shark_target]
    if pull_count < 0:
        raise AutomationError("--pr-count cannot be negative.")

    return AutomationConfig(
        repo_name=ns.repo,
        visibility=ns.visibility,
        pull_shark_count=pull_count,
        run_quickdraw=not ns.no_quickdraw,
        run_yolo=not ns.no_yolo,
        reviewer=ns.reviewer,
        pair_count=ns.pair_count,
        coauthor_username=ns.coauthor_username,
        coauthor_name=ns.coauthor_name,
        coauthor_email=ns.coauthor_email,
        allow_custom_email=ns.allow_custom_email,
        galaxy_count=ns.galaxy_count,
        helper_token_env=ns.helper_token_env,
        delay_seconds=ns.delay_seconds,
        batch_limit=ns.batch_limit,
        max_retries=ns.max_retries,
        workdir=ns.workdir,
        state_file=ns.state_file,
        dry_run=ns.dry_run,
        verify_only=ns.verify_only,
    )


def print_verification_report(summary: VerificationSummary) -> None:
    print("\n=== GitHub Achievement Automation Verification ===")
    print(f"Profile:              https://github.com/{summary.owner}")
    print(f"Achievements Tab:     {summary.profile_url}")
    print(f"Sandbox Repo:         {summary.repo}")
    print(f"Merged PRs (Repo):    {summary.merged_prs_count}")
    print(f"Merged PRs (Global):  {summary.global_merged_prs_count}")
    print(f"Co-authored PRs:      {summary.coauthored_prs_count}")
    print(f"Quickdraw Issues:     {summary.quickdraw_issue_count}")
    print(f"Accepted Answers:     {summary.accepted_discussion_answers}")
    if summary.visible_profile_badges:
        print(f"Visible Badges Now:   {', '.join(summary.visible_profile_badges)}")
    else:
        print("Visible Badges Now:   None scraped yet (GitHub may take a few minutes to 24h+ to index, or check profile visibility settings)")
    print("==================================================\n")


def main(argv: list[str] | None = None) -> int:
    ns = parse_args(argv)
    setup_logging(ns.verbose)

    try:
        config = config_from_args(ns)
        config, user = validate_tools_and_preflight(config)

        if config.verify_only:
            summary = verify_achievements(config)
            print_verification_report(summary)
            return 0

        if config.visibility == "private":
            LOG.warning(
                "Private repository mode selected: GitHub achievements like Pull Shark, YOLO, and Quickdraw "
                "often fail to trigger in private repositories even with 'Show private contributions' enabled."
            )

        state: dict[str, Any] = {}
        if config.state_file.exists():
            try:
                state = json.loads(config.state_file.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                state = {}

        state.update(
            {
                "owner": config.owner,
                "repo": config.full_repo,
                "last_started_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            }
        )

        local_dir, default_branch = ensure_sandbox_repo(config, user)
        quickdraw_url = run_quickdraw(config)
        if quickdraw_url and not config.dry_run:
            state["quickdraw_issue_url"] = quickdraw_url
            save_state(config.state_file, state)

        _, newly_merged = run_pr_achievements(config, local_dir, default_branch, state)
        accepted_added = run_galaxy_brain(config)

        if not config.dry_run:
            state["last_completed_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
            save_state(config.state_file, state)
            LOG.info("Run completed: +%d merged PR(s), +%d accepted discussion answer(s).", newly_merged, accepted_added)
            summary = verify_achievements(config)
            print_verification_report(summary)
        else:
            LOG.info("[DRY RUN] Simulation finished cleanly with zero remote changes.")

        return 0
    except AutomationError as exc:
        LOG.error("%s", exc)
        return 1
    except KeyboardInterrupt:
        LOG.warning("Interrupted by user. Progress checkpoints have been preserved.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
