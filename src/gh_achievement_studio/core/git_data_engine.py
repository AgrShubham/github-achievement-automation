"""Gitless GitHub repository, collaborator, and PR workflow engine via Git Data API."""

from __future__ import annotations

import base64
import datetime as dt
import time
from typing import Any

from .github_client import GitHubApiError, GitHubClient
from .models import AccountSession


def build_commit_message(subject: str, body: str = "", coauthor_trailer: str | None = None) -> str:
    lines = [subject.strip()]
    if body.strip():
        lines.extend(["", body.strip()])
    if coauthor_trailer and coauthor_trailer.strip():
        lines.extend(["", coauthor_trailer.strip()])
    return "\n".join(lines)


def format_coauthor_trailer(name: str, email: str) -> str:
    clean_name = name.strip()
    clean_email = email.strip()
    if not clean_name:
        raise ValueError("Co-author name cannot be empty.")
    if "@" not in clean_email or "." not in clean_email.split("@")[-1]:
        raise ValueError(f"Invalid co-author email address: {clean_email}")
    return f"Co-authored-by: {clean_name} <{clean_email}>"


def fetch_repo_info(client: GitHubClient, owner: str, repo: str) -> dict[str, Any] | None:
    try:
        data = client.rest("GET", f"/repos/{owner}/{repo}")
        return data if isinstance(data, dict) else None
    except GitHubApiError as exc:
        if exc.status_code == 404:
            return None
        raise


def ensure_sandbox_repository(
    owner_client: GitHubClient,
    owner_login: str,
    repo_name: str,
    visibility: str = "public",
) -> tuple[dict[str, Any], str, bool]:
    """Ensure the sandbox repo exists and has an initial commit on its default branch."""
    existing = fetch_repo_info(owner_client, owner_login, repo_name)
    created_now = False
    if existing is None:
        existing = owner_client.rest(
            "POST",
            "/user/repos",
            payload={
                "name": repo_name,
                "description": "Automated GitHub profile achievements sandbox repository",
                "private": visibility == "private",
                "auto_init": True,
                "has_issues": True,
                "has_discussions": True,
            },
        )
        created_now = True
        # Wait briefly until GitHub initializes the default branch reference
        for _ in range(8):
            default_branch = str(existing.get("default_branch") or "main")
            try:
                owner_client.rest("GET", f"/repos/{owner_login}/{repo_name}/git/ref/heads/{default_branch}")
                break
            except GitHubApiError as exc:
                if exc.status_code in (404, 409):
                    time.sleep(1.0)
                    continue
                raise

    default_branch = str(existing.get("default_branch") or "main")

    # Handle pre-existing empty repository (no commits yet)
    try:
        owner_client.rest("GET", f"/repos/{owner_login}/{repo_name}/git/ref/heads/{default_branch}")
    except GitHubApiError as exc:
        if exc.status_code in (404, 409):
            readme_b64 = base64.b64encode(
                f"# {repo_name}\n\nSandbox repository for automated GitHub profile achievements.\n".encode("utf-8")
            ).decode("ascii")
            owner_client.rest(
                "PUT",
                f"/repos/{owner_login}/{repo_name}/contents/README.md",
                payload={
                    "message": "chore: initialize achievement sandbox repository",
                    "content": readme_b64,
                    "branch": default_branch,
                },
            )
            existing = fetch_repo_info(owner_client, owner_login, repo_name) or existing
        else:
            raise

    return existing, default_branch, created_now


def ensure_collaborator_link(
    owner_client: GitHubClient,
    collaborator_client: GitHubClient,
    owner_login: str,
    repo_name: str,
    collaborator_login: str,
) -> None:
    """Invite collaborator with push access and auto-accept the pending invitation."""
    try:
        owner_client.rest(
            "GET",
            f"/repos/{owner_login}/{repo_name}/collaborators/{collaborator_login}",
        )
        return
    except GitHubApiError as exc:
        if exc.status_code != 404:
            raise

    owner_client.rest(
        "PUT",
        f"/repos/{owner_login}/{repo_name}/collaborators/{collaborator_login}",
        payload={"permission": "push"},
    )

    for _ in range(5):
        invites = collaborator_client.rest("GET", "/user/repository_invitations")
        if isinstance(invites, list):
            for inv in invites:
                repo_full = ((inv.get("repository") or {}).get("full_name") or "").lower()
                if repo_full == f"{owner_login}/{repo_name}".lower():
                    collaborator_client.rest("PATCH", f"/user/repository_invitations/{inv['id']}")
                    return
        time.sleep(1.0)


def _read_remote_file_content(
    client: GitHubClient,
    owner: str,
    repo: str,
    path: str,
    branch: str,
) -> str:
    try:
        data = client.rest("GET", f"/repos/{owner}/{repo}/contents/{path}", params={"ref": branch})
        if isinstance(data, dict) and data.get("content"):
            raw_b64 = str(data["content"]).replace("\n", "")
            return base64.b64decode(raw_b64).decode("utf-8", errors="replace")
    except GitHubApiError as exc:
        if exc.status_code != 404:
            raise
    return "# Achievement Automation Log\n\n"


def run_gitless_pr_cycle(
    author_client: GitHubClient,
    merger_client: GitHubClient,
    author_session: AccountSession,
    repo_owner: str,
    repo_name: str,
    default_branch: str,
    branch_name: str,
    log_entry: str,
    commit_subject: str,
    pr_title: str,
    pr_body: str,
    coauthor_trailer: str | None = None,
    requested_reviewer: str | None = None,
) -> int:
    """Execute one complete branch -> commit -> PR -> merge -> cleanup cycle over REST."""
    base_ref = author_client.rest("GET", f"/repos/{repo_owner}/{repo_name}/git/ref/heads/{default_branch}")
    base_sha = str(base_ref["object"]["sha"])
    base_commit = author_client.rest("GET", f"/repos/{repo_owner}/{repo_name}/git/commits/{base_sha}")
    base_tree_sha = str(base_commit["tree"]["sha"])

    current_log = _read_remote_file_content(
        author_client, repo_owner, repo_name, "ACHIEVEMENTS_LOG.md", default_branch
    )
    updated_log = current_log.rstrip("\n") + "\n" + log_entry + "\n"

    blob = author_client.rest(
        "POST",
        f"/repos/{repo_owner}/{repo_name}/git/blobs",
        payload={"content": updated_log, "encoding": "utf-8"},
    )
    tree = author_client.rest(
        "POST",
        f"/repos/{repo_owner}/{repo_name}/git/trees",
        payload={
            "base_tree": base_tree_sha,
            "tree": [
                {
                    "path": "ACHIEVEMENTS_LOG.md",
                    "mode": "100644",
                    "type": "blob",
                    "sha": blob["sha"],
                }
            ],
        },
    )

    now_iso = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    commit_msg = build_commit_message(commit_subject, coauthor_trailer=coauthor_trailer)
    commit_author = {
        "name": author_session.name,
        "email": author_session.commit_email,
        "date": now_iso,
    }
    commit = author_client.rest(
        "POST",
        f"/repos/{repo_owner}/{repo_name}/git/commits",
        payload={
            "message": commit_msg,
            "tree": tree["sha"],
            "parents": [base_sha],
            "author": commit_author,
            "committer": commit_author,
        },
    )

    author_client.rest(
        "POST",
        f"/repos/{repo_owner}/{repo_name}/git/refs",
        payload={"ref": f"refs/heads/{branch_name}", "sha": commit["sha"]},
    )

    pr = author_client.rest(
        "POST",
        f"/repos/{repo_owner}/{repo_name}/pulls",
        payload={
            "title": pr_title,
            "head": branch_name,
            "base": default_branch,
            "body": pr_body,
        },
    )
    pr_number = int(pr["number"])

    if requested_reviewer:
        try:
            author_client.rest(
                "POST",
                f"/repos/{repo_owner}/{repo_name}/pulls/{pr_number}/requested_reviewers",
                payload={"reviewers": [requested_reviewer]},
            )
        except GitHubApiError:
            # Non-fatal if reviewer request is blocked or identical to author
            pass

    time.sleep(0.8)

    merger_client.rest(
        "PUT",
        f"/repos/{repo_owner}/{repo_name}/pulls/{pr_number}/merge",
        payload={"merge_method": "merge"},
    )

    try:
        merger_client.rest("DELETE", f"/repos/{repo_owner}/{repo_name}/git/refs/heads/{branch_name}")
    except GitHubApiError:
        pass

    return pr_number
