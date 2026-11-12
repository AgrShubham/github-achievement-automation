"""Idempotent achievement planner and thread-safe execution engine."""

from __future__ import annotations

import datetime as dt
import re
import threading
import time
from typing import Callable

from .git_data_engine import (
    ensure_collaborator_link,
    ensure_sandbox_repository,
    fetch_repo_info,
    format_coauthor_trailer,
    run_gitless_pr_cycle,
)
from .github_client import GitHubClient
from .models import AccountSession, PlanPreview, ProgressEvent, RunConfig
from .state import StateStore
from .verifier import (
    count_coauthored_prs,
    fetch_accepted_discussion_answers,
    fetch_merged_prs_for_author,
    fetch_quickdraw_issues,
    parse_iso_datetime,
)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PLACEHOLDER_DOMAINS = {
    "example.com",
    "example.org",
    "example.net",
    "test.com",
    "fake.com",
    "invalid",
    "localhost",
}


class EngineValidationError(ValueError):
    """Raised when run configuration violates GitHub achievement constraints."""


def resolve_repo_target(
    primary: AccountSession,
    secondary: AccountSession | None,
    config: RunConfig,
) -> tuple[str, str]:
    raw = config.repo_name.strip()
    if not raw:
        raise EngineValidationError("Sandbox repository name cannot be empty.")
    if "/" in raw:
        owner, short = raw.split("/", 1)
        return owner.strip(), short.strip()
    if config.cross_owner_mode:
        if secondary is None:
            raise EngineValidationError("Cross-Owner Mode requires connecting a second GitHub account.")
        if secondary.login.lower() == primary.login.lower():
            raise EngineValidationError("Cross-Owner Mode requires the second account to differ from the primary account.")
        return secondary.login, raw
    return primary.login, raw


def resolve_coauthor_details(
    primary_client: GitHubClient,
    secondary: AccountSession | None,
    config: RunConfig,
) -> tuple[str, str]:
    if config.pair_target <= 0:
        return "", ""

    name = config.coauthor_name.strip()
    email = config.coauthor_email.strip()
    username = config.coauthor_username.strip()

    if not email and not username and secondary is not None:
        return secondary.name, secondary.noreply_email

    if username and not email:
        info = primary_client.rest("GET", f"/users/{username}")
        uid = int(info["id"])
        login = str(info["login"])
        email = f"{uid}+{login}@users.noreply.github.com"
        if not name:
            name = str(info.get("name") or login)

    if not name and username:
        name = username
    if not name or not email:
        raise EngineValidationError(
            "Pair Extraordinaire requires a connected 2nd account, a GitHub co-author username, or co-author name + email."
        )
    if not EMAIL_RE.match(email):
        raise EngineValidationError(f"Invalid co-author email address: {email}")
    domain = email.lower().split("@")[-1]
    if domain in PLACEHOLDER_DOMAINS:
        raise EngineValidationError(
            f"Email `{email}` is a placeholder address and will not trigger Pair Extraordinaire."
        )
    return name, email


def validate_run_config(
    primary: AccountSession,
    primary_client: GitHubClient,
    secondary: AccountSession | None,
    config: RunConfig,
) -> tuple[str, str, str, str, list[str]]:
    if config.delay_seconds < 0:
        raise EngineValidationError("Delay seconds cannot be negative.")
    if config.batch_limit is not None and config.batch_limit <= 0:
        raise EngineValidationError("Batch limit must be positive.")

    repo_owner, repo_name = resolve_repo_target(primary, secondary, config)
    co_name, co_email = resolve_coauthor_details(primary_client, secondary, config)

    if config.galaxy_target > 0:
        if secondary is None:
            raise EngineValidationError("Galaxy Brain requires connecting a second GitHub account.")
        if secondary.login.lower() == primary.login.lower():
            raise EngineValidationError(
                "Secondary account cannot match primary account: GitHub blocks self-accepted Discussion answers."
            )

    if config.request_secondary_reviewer and secondary is None:
        raise EngineValidationError("Requesting a collaborator reviewer for strict YOLO requires a connected 2nd account.")

    warnings: list[str] = []
    if config.visibility == "private":
        warnings.append("Private repos often fail to trigger achievements even with private contributions enabled.")
    if not config.cross_owner_mode and config.pull_shark_target >= 16:
        warnings.append(
            "Solo self-merged PRs may lag in Pull Shark's queue; connect a 2nd account and enable Cross-Owner Mode for fastest reliability."
        )
    if config.delay_seconds < 2.0 and (config.pull_shark_target + config.pair_target) > 10:
        warnings.append("Low delay (<2.0s) may trigger GitHub secondary rate limits on larger PR batches.")

    return repo_owner, repo_name, co_name, co_email, warnings


def build_execution_plan(
    primary: AccountSession,
    primary_client: GitHubClient,
    secondary: AccountSession | None,
    config: RunConfig,
) -> PlanPreview:
    repo_owner, repo_name, co_name, co_email, warnings = validate_run_config(
        primary, primary_client, secondary, config
    )
    repo_info = fetch_repo_info(primary_client, repo_owner, repo_name)
    repo_exists = repo_info is not None

    existing_merged = 0
    existing_pair = 0
    existing_quickdraw = 0
    existing_accepted = 0

    if repo_exists:
        merged_prs = fetch_merged_prs_for_author(primary_client, repo_owner, repo_name, primary.login)
        existing_merged = len(merged_prs)
        existing_pair = count_coauthored_prs(merged_prs, co_email or None)
        existing_quickdraw = len(fetch_quickdraw_issues(primary_client, repo_owner, repo_name))
        existing_accepted = fetch_accepted_discussion_answers(primary_client, repo_owner, repo_name, primary.login)

    quickdraw_needed = 1 if (config.run_quickdraw and existing_quickdraw == 0) else 0
    pair_needed = max(0, config.pair_target - existing_pair)
    expected_after_pair = existing_merged + pair_needed

    eff_pull_target = config.pull_shark_target
    if config.run_yolo and eff_pull_target == 0 and expected_after_pair == 0:
        eff_pull_target = 1

    pull_needed = max(0, eff_pull_target - expected_after_pair)
    if config.batch_limit is not None:
        budget = config.batch_limit
        pair_planned = min(pair_needed, budget)
        budget -= pair_planned
        pull_planned = min(pull_needed, budget)
    else:
        pair_planned = pair_needed
        pull_planned = pull_needed

    galaxy_needed = max(0, config.galaxy_target - existing_accepted)

    total_prs = pair_planned + pull_planned
    est = (quickdraw_needed * 3.0) + (total_prs * (3.5 + config.delay_seconds)) + (galaxy_needed * (3.0 + config.delay_seconds))

    return PlanPreview(
        repo_owner=repo_owner,
        repo_name=repo_name,
        visibility=config.visibility,
        repo_exists=repo_exists,
        cross_owner_mode=config.cross_owner_mode,
        existing_merged_prs=existing_merged,
        existing_coauthored_prs=existing_pair,
        existing_quickdraw_issues=existing_quickdraw,
        existing_accepted_answers=existing_accepted,
        quickdraw_to_create=quickdraw_needed,
        pair_prs_to_create=pair_planned,
        pull_shark_prs_to_create=pull_planned,
        galaxy_answers_to_create=galaxy_needed,
        estimated_seconds=round(est, 1),
        coauthor_display=f"{co_name} <{co_email}>" if co_email else "",
        warnings=tuple(warnings),
    )


class AchievementEngine:
    """Executes an achievement automation run safely on a background worker thread."""

    def __init__(
        self,
        primary: AccountSession,
        secondary: AccountSession | None,
        config: RunConfig,
        state_store: StateStore | None = None,
        on_event: Callable[[ProgressEvent], None] | None = None,
        cancel_event: threading.Event | None = None,
        pause_event: threading.Event | None = None,
    ) -> None:
        self.primary = primary
        self.secondary = secondary
        self.config = config
        self.state_store = state_store or StateStore()
        self.on_event = on_event or (lambda _evt: None)
        self.cancel_event = cancel_event or threading.Event()
        self.pause_event = pause_event or threading.Event()
        self.primary_client = GitHubClient(primary.token)
        self.secondary_client = GitHubClient(secondary.token) if secondary else None

    def _emit(
        self,
        kind: str,
        message: str,
        level: str = "INFO",
        current: int = 0,
        total: int = 0,
        stage: str = "",
    ) -> None:
        self.on_event(
            ProgressEvent(
                kind=kind,
                message=message,
                level=level,
                current=current,
                total=total,
                stage=stage,
            )
        )

    def _wait_if_paused_or_cancelled(self) -> bool:
        while self.pause_event.is_set():
            if self.cancel_event.is_set():
                return True
            time.sleep(0.25)
        return self.cancel_event.is_set()

    def _sleep_interruptible(self, seconds: float) -> bool:
        deadline = time.monotonic() + max(0.0, seconds)
        while time.monotonic() < deadline:
            if self._wait_if_paused_or_cancelled():
                return True
            time.sleep(min(0.25, max(0.0, deadline - time.monotonic())))
        return self.cancel_event.is_set()

    def execute(self) -> PlanPreview:
        plan = build_execution_plan(self.primary, self.primary_client, self.secondary, self.config)
        total_steps = (
            1  # repo setup
            + plan.quickdraw_to_create
            + plan.pair_prs_to_create
            + plan.pull_shark_prs_to_create
            + plan.galaxy_answers_to_create
        )
        completed_steps = 0

        if self.config.dry_run:
            self._emit(
                "log",
                f"[DRY RUN] Target `{plan.full_repo}` ({plan.visibility}) — Quickdraw: {plan.quickdraw_to_create}, "
                f"Pair PRs: {plan.pair_prs_to_create}, Pull Shark/YOLO PRs: {plan.pull_shark_prs_to_create}, "
                f"Galaxy Brain answers: {plan.galaxy_answers_to_create}.",
            )
            self._emit("completed", "Dry-run simulation finished with zero changes.", current=1, total=1)
            return plan

        if self._wait_if_paused_or_cancelled():
            self._emit("cancelled", "Run cancelled before starting.")
            return plan

        # Stage 1: Repository provisioning & collaborator access
        owner_client = self.secondary_client if (self.config.cross_owner_mode and self.secondary_client) else self.primary_client
        assert owner_client is not None

        self._emit("stage", f"Preparing `{plan.full_repo}`...", current=completed_steps, total=total_steps, stage="Repository")
        _, default_branch, created_now = ensure_sandbox_repository(
            owner_client,
            plan.repo_owner,
            plan.repo_name,
            visibility=self.config.visibility,
        )
        self._emit(
            "log",
            f"{'Created' if created_now else 'Using existing'} repository `{plan.full_repo}` (default branch: `{default_branch}`).",
        )

        if self.secondary and self.secondary_client and (
            self.config.cross_owner_mode or self.config.request_secondary_reviewer
        ):
            collab_login = self.primary.login if self.config.cross_owner_mode else self.secondary.login
            collab_client = self.primary_client if self.config.cross_owner_mode else self.secondary_client
            ensure_collaborator_link(owner_client, collab_client, plan.repo_owner, plan.repo_name, collab_login)
            self._emit("log", f"Verified collaborator permissions for `@{collab_login}` on `{plan.full_repo}`.")

        completed_steps += 1
        self._emit("progress", "Repository ready.", current=completed_steps, total=total_steps, stage="Repository")

        # Stage 2: Quickdraw
        if plan.quickdraw_to_create > 0:
            if self._wait_if_paused_or_cancelled():
                self._emit("cancelled", "Run cancelled during Quickdraw stage.")
                return plan
            self._emit("stage", "Running Quickdraw issue cycle...", current=completed_steps, total=total_steps, stage="Quickdraw")
            issue = self.primary_client.rest(
                "POST",
                f"/repos/{plan.repo_owner}/{plan.repo_name}/issues",
                payload={
                    "title": "[Achievement] Quickdraw verification",
                    "body": "Automated issue created and closed within 5 minutes for the GitHub Quickdraw achievement.",
                },
            )
            issue_num = int(issue["number"])
            closed = self.primary_client.rest(
                "PATCH",
                f"/repos/{plan.repo_owner}/{plan.repo_name}/issues/{issue_num}",
                payload={"state": "closed", "state_reason": "completed"},
            )
            elapsed = (
                parse_iso_datetime(closed["closed_at"]) - parse_iso_datetime(closed["created_at"])
            ).total_seconds()
            self._emit("log", f"Quickdraw verified: issue #{issue_num} closed in {elapsed:.1f}s.")
            completed_steps += 1
            self._emit("progress", f"Quickdraw issue #{issue_num} completed.", current=completed_steps, total=total_steps, stage="Quickdraw")

        # Stage 3: PR cycles (Pair Extraordinaire + Pull Shark / YOLO)
        merger_client = self.secondary_client if (self.config.cross_owner_mode and self.secondary_client) else self.primary_client
        assert merger_client is not None
        reviewer = self.secondary.login if (self.config.request_secondary_reviewer and self.secondary) else None
        seq = plan.existing_merged_prs + 1

        if plan.pair_prs_to_create > 0:
            _, _, co_name, co_email, _ = validate_run_config(
                self.primary, self.primary_client, self.secondary, self.config
            )
            trailer = format_coauthor_trailer(co_name, co_email)
            for idx in range(1, plan.pair_prs_to_create + 1):
                if self._wait_if_paused_or_cancelled():
                    self._emit("cancelled", "Run cancelled during Pair Extraordinaire batch.")
                    return plan
                ts = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                branch = f"achievement/pair-{seq:04d}-{ts.lower()}"
                pr_num = run_gitless_pr_cycle(
                    author_client=self.primary_client,
                    merger_client=merger_client,
                    author_session=self.primary,
                    repo_owner=plan.repo_owner,
                    repo_name=plan.repo_name,
                    default_branch=default_branch,
                    branch_name=branch,
                    log_entry=f"- [{ts}] Milestone #{seq:04d} — Pair Extraordinaire + Pull Shark (`{branch}`)",
                    commit_subject=f"chore(achievements): pair milestone #{seq:04d}",
                    pr_title=f"chore(achievements): pair milestone #{seq:04d}",
                    pr_body="Automated co-authored milestone PR for Pair Extraordinaire and Pull Shark.",
                    coauthor_trailer=trailer,
                    requested_reviewer=reviewer if seq == 1 else None,
                )
                seq += 1
                completed_steps += 1
                self.state_store.update({"last_repo": plan.full_repo, "last_pr_number": pr_num})
                self._emit("log", f"Merged Pair Extraordinaire PR #{pr_num} ({idx}/{plan.pair_prs_to_create}).")
                self._emit(
                    "progress",
                    f"Pair PR #{pr_num} merged ({idx}/{plan.pair_prs_to_create})",
                    current=completed_steps,
                    total=total_steps,
                    stage="Pair Extraordinaire",
                )
                if idx < plan.pair_prs_to_create or plan.pull_shark_prs_to_create > 0:
                    if self._sleep_interruptible(self.config.delay_seconds):
                        self._emit("cancelled", "Run cancelled between PR cycles.")
                        return plan

        for idx in range(1, plan.pull_shark_prs_to_create + 1):
            if self._wait_if_paused_or_cancelled():
                self._emit("cancelled", "Run cancelled during Pull Shark batch.")
                return plan
            ts = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            branch = f"achievement/pr-{seq:04d}-{ts.lower()}"
            pr_num = run_gitless_pr_cycle(
                author_client=self.primary_client,
                merger_client=merger_client,
                author_session=self.primary,
                repo_owner=plan.repo_owner,
                repo_name=plan.repo_name,
                default_branch=default_branch,
                branch_name=branch,
                log_entry=f"- [{ts}] Milestone #{seq:04d} — Pull Shark / YOLO (`{branch}`)",
                commit_subject=f"chore(achievements): milestone #{seq:04d}",
                pr_title=f"chore(achievements): milestone #{seq:04d}",
                pr_body="Automated milestone PR for Pull Shark and YOLO profile achievements.",
                coauthor_trailer=None,
                requested_reviewer=reviewer if seq == 1 else None,
            )
            seq += 1
            completed_steps += 1
            self.state_store.update({"last_repo": plan.full_repo, "last_pr_number": pr_num})
            self._emit("log", f"Merged Pull Shark / YOLO PR #{pr_num} ({idx}/{plan.pull_shark_prs_to_create}).")
            self._emit(
                "progress",
                f"Pull Shark PR #{pr_num} merged ({idx}/{plan.pull_shark_prs_to_create})",
                current=completed_steps,
                total=total_steps,
                stage="Pull Shark",
            )
            if idx < plan.pull_shark_prs_to_create or plan.galaxy_answers_to_create > 0:
                if self._sleep_interruptible(self.config.delay_seconds):
                    self._emit("cancelled", "Run cancelled between PR cycles.")
                    return plan

        # Stage 4: Galaxy Brain Discussions
        if plan.galaxy_answers_to_create > 0:
            assert self.secondary_client is not None
            repo_meta = fetch_repo_info(owner_client, plan.repo_owner, plan.repo_name)
            if repo_meta and not repo_meta.get("has_discussions"):
                owner_client.rest("PATCH", f"/repos/{plan.repo_owner}/{plan.repo_name}", payload={"has_discussions": True})
                time.sleep(1.5)

            cat_data = self.primary_client.graphql(
                """
                query($owner: String!, $repo: String!) {
                  repository(owner: $owner, name: $repo) {
                    id
                    discussionCategories(first: 25) {
                      nodes { id name isAnswerable }
                    }
                  }
                }
                """,
                {"owner": plan.repo_owner, "repo": plan.repo_name},
            )
            repo_id = cat_data["repository"]["id"]
            categories = cat_data["repository"]["discussionCategories"]["nodes"]
            answerable = [c for c in categories if c.get("isAnswerable")]
            if not answerable:
                raise EngineValidationError("No answerable Q&A Discussion category found on the sandbox repository.")
            cat_id = answerable[0]["id"]

            for idx in range(1, plan.galaxy_answers_to_create + 1):
                if self._wait_if_paused_or_cancelled():
                    self._emit("cancelled", "Run cancelled during Galaxy Brain stage.")
                    return plan
                num_label = plan.existing_accepted_answers + idx
                disc = self.secondary_client.graphql(
                    """
                    mutation($repositoryId: ID!, $categoryId: ID!, $title: String!, $body: String!) {
                      createDiscussion(input: {repositoryId: $repositoryId, categoryId: $categoryId, title: $title, body: $body}) {
                        discussion { id number url }
                      }
                    }
                    """,
                    {
                        "repositoryId": repo_id,
                        "categoryId": cat_id,
                        "title": f"[Achievement] Galaxy Brain Q&A #{num_label:03d}",
                        "body": "Automated Q&A discussion question for Galaxy Brain achievement verification.",
                    },
                )["createDiscussion"]["discussion"]

                comment = self.primary_client.graphql(
                    """
                    mutation($discussionId: ID!, $body: String!) {
                      addDiscussionComment(input: {discussionId: $discussionId, body: $body}) {
                        comment { id }
                      }
                    }
                    """,
                    {
                        "discussionId": disc["id"],
                        "body": f"Automated verified solution #{num_label:03d} for Galaxy Brain.",
                    },
                )["addDiscussionComment"]["comment"]

                self.secondary_client.graphql(
                    """
                    mutation($id: ID!) {
                      markDiscussionCommentAsAnswer(input: {id: $id}) {
                        discussion { id }
                      }
                    }
                    """,
                    {"id": comment["id"]},
                )
                completed_steps += 1
                self._emit("log", f"Accepted Galaxy Brain answer {idx}/{plan.galaxy_answers_to_create} (Discussion #{disc['number']}).")
                self._emit(
                    "progress",
                    f"Galaxy Brain Q&A #{disc['number']} accepted ({idx}/{plan.galaxy_answers_to_create})",
                    current=completed_steps,
                    total=total_steps,
                    stage="Galaxy Brain",
                )
                if idx < plan.galaxy_answers_to_create:
                    if self._sleep_interruptible(self.config.delay_seconds):
                        self._emit("cancelled", "Run cancelled during Galaxy Brain wait.")
                        return plan

        self._emit("completed", "Achievement automation run finished successfully.", current=total_steps, total=total_steps)
        return plan
