"""Live repository metrics, profile badge HTML parser, and sandbox archive utilities."""

from __future__ import annotations

import datetime as dt
import re
import urllib.error
import urllib.request
from typing import Any

from .git_data_engine import fetch_repo_info
from .github_client import GitHubApiError, GitHubClient
from .models import AccountSession, VerificationReport

COAUTHOR_EMAIL_RE = re.compile(r"^Co-authored-by:\s+.+?<([^>\s]+)>\s*$", re.IGNORECASE | re.MULTILINE)
BADGE_CARD_RE = re.compile(
    r'class="achievement-badge-card"[\s\S]{0,400}?<h3[^>]*>([^<]+)</h3>(?:\s*<span[^>]*achievement-tier-label[^>]*>\s*([^<\s]+)\s*</span>)?',
    re.IGNORECASE,
)


def parse_iso_datetime(value: str) -> dt.datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    return dt.datetime.fromisoformat(normalized)


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
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError):
            continue
        parsed = parse_achievement_badges(html)
        for item in parsed:
            if item not in badges:
                badges.append(item)
        if badges:
            break
    return badges


def fetch_merged_prs_for_author(
    client: GitHubClient,
    repo_owner: str,
    repo_name: str,
    author_login: str,
) -> list[dict[str, Any]]:
    query = """
    query($owner: String!, $repo: String!, $cursor: String) {
      repository(owner: $owner, name: $repo) {
        pullRequests(states: MERGED, first: 100, after: $cursor, orderBy: {field: CREATED_AT, direction: ASC}) {
          pageInfo { hasNextPage endCursor }
          nodes {
            number
            title
            headRefName
            mergedAt
            author { login }
            commits(first: 10) {
              nodes { commit { message } }
            }
          }
        }
      }
    }
    """
    results: list[dict[str, Any]] = []
    cursor: str | None = None
    while True:
        data = client.graphql(query, {"owner": repo_owner, "repo": repo_name, "cursor": cursor})
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
        for c in commits:
            msg = ((c or {}).get("commit") or {}).get("message") or ""
            emails = [m.lower() for m in COAUTHOR_EMAIL_RE.findall(msg)]
            if not emails:
                continue
            if not coauthor_email or coauthor_email.lower() in emails:
                count += 1
                break
    return count


def fetch_quickdraw_issues(client: GitHubClient, repo_owner: str, repo_name: str) -> list[dict[str, Any]]:
    data = client.rest(
        "GET",
        f"/repos/{repo_owner}/{repo_name}/issues",
        params={"state": "closed", "per_page": 50},
    )
    if not isinstance(data, list):
        return []
    qualifying: list[dict[str, Any]] = []
    for issue in data:
        if "pull_request" in issue:
            continue
        if not issue.get("created_at") or not issue.get("closed_at"):
            continue
        delta = (parse_iso_datetime(issue["closed_at"]) - parse_iso_datetime(issue["created_at"])).total_seconds()
        if 0 <= delta < 300:
            item = dict(issue)
            item["elapsed_seconds"] = round(delta, 2)
            qualifying.append(item)
    return qualifying


def fetch_accepted_discussion_answers(
    client: GitHubClient,
    repo_owner: str,
    repo_name: str,
    answer_author: str,
) -> int:
    query = """
    query($owner: String!, $repo: String!, $cursor: String) {
      repository(owner: $owner, name: $repo) {
        hasDiscussionsEnabled
        discussions(first: 50, after: $cursor, answered: true) {
          pageInfo { hasNextPage endCursor }
          nodes {
            number
            answer { author { login } }
          }
        }
      }
    }
    """
    count = 0
    cursor: str | None = None
    while True:
        data = client.graphql(query, {"owner": repo_owner, "repo": repo_name, "cursor": cursor})
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


def fetch_global_merged_prs_count(client: GitHubClient, actor: str) -> int:
    try:
        data = client.rest(
            "GET",
            "/search/issues",
            params={"q": f"is:pr author:{actor} is:merged", "per_page": 1},
        )
        return int((data or {}).get("total_count", 0))
    except GitHubApiError:
        return 0


def verify_account_achievements(
    primary_client: GitHubClient,
    primary_session: AccountSession,
    repo_owner: str,
    repo_name: str,
    coauthor_email: str | None = None,
) -> VerificationReport:
    repo_info = fetch_repo_info(primary_client, repo_owner, repo_name)
    repo_exists = repo_info is not None
    repo_archived = bool((repo_info or {}).get("archived", False))

    repo_merged = 0
    coauthored = 0
    quickdraw = 0
    accepted = 0
    if repo_exists:
        merged_prs = fetch_merged_prs_for_author(primary_client, repo_owner, repo_name, primary_session.login)
        repo_merged = len(merged_prs)
        coauthored = count_coauthored_prs(merged_prs, coauthor_email)
        quickdraw = len(fetch_quickdraw_issues(primary_client, repo_owner, repo_name))
        accepted = fetch_accepted_discussion_answers(primary_client, repo_owner, repo_name, primary_session.login)

    global_merged = fetch_global_merged_prs_count(primary_client, primary_session.login)
    badges = tuple(scrape_profile_achievements(primary_session.login))
    rem, lim = primary_client.get_rate_limit()

    return VerificationReport(
        actor=primary_session.login,
        repo_full_name=f"{repo_owner}/{repo_name}",
        repo_exists=repo_exists,
        repo_archived=repo_archived,
        repo_url=f"https://github.com/{repo_owner}/{repo_name}",
        profile_url=f"https://github.com/{primary_session.login}",
        achievements_url=f"https://github.com/{primary_session.login}?tab=achievements",
        repo_merged_prs=repo_merged,
        global_merged_prs=global_merged,
        coauthored_prs=coauthored,
        quickdraw_issues=quickdraw,
        accepted_answers=accepted,
        visible_badges=badges,
        rate_limit_remaining=rem,
        rate_limit_limit=lim,
    )


def set_repository_archived(client: GitHubClient, owner: str, repo: str, archived: bool) -> dict[str, Any]:
    data = client.rest("PATCH", f"/repos/{owner}/{repo}", payload={"archived": archived})
    return data if isinstance(data, dict) else {}
