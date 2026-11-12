"""Headless CLI runner built on the gitless GitHub Achievement Studio engine."""

from __future__ import annotations

import argparse
import os
import sys

from ..core.auth import AuthError, CredentialStore, authenticate_with_token, import_gh_cli_token
from ..core.github_client import GitHubClient
from ..core.models import PULL_SHARK_TIERS, AccountSession, ProgressEvent, RunConfig
from ..core.runners import AchievementEngine, EngineValidationError, resolve_repo_target
from ..core.state import StateStore
from ..core.verifier import verify_account_achievements


def parse_pull_shark_target(raw: str) -> int:
    key = raw.strip().lower()
    if key in PULL_SHARK_TIERS:
        return PULL_SHARK_TIERS[key]
    val = int(key)
    if val < 0:
        raise ValueError("Pull Shark target cannot be negative.")
    return val


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="github-achievement-studio --cli",
        description="Gitless CLI runner for GitHub Achievement Studio.",
    )
    parser.add_argument("--repo", default="github-achievements-sandbox", help="Sandbox repo name or owner/repo.")
    parser.add_argument("--visibility", choices=("public", "private"), default="public")
    parser.add_argument("--cross-owner", action="store_true", help="Let secondary account own and merge PRs.")
    parser.add_argument("--quickdraw", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--yolo", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--strict-yolo", action="store_true", help="Request secondary user as unreviewed PR reviewer.")
    parser.add_argument(
        "--pull-shark-target",
        default="bronze",
        help="none|default|bronze|silver|gold or exact integer count (default: bronze=16).",
    )
    parser.add_argument("--pair-count", type=int, default=0, help="Target co-authored merged PRs.")
    parser.add_argument("--coauthor-username", default="", help="GitHub username for co-author trailer.")
    parser.add_argument("--coauthor-email", default="", help="Explicit verified/noreply email for co-author.")
    parser.add_argument("--galaxy-count", type=int, default=0, help="Target accepted Q&A answers.")
    parser.add_argument("--delay-seconds", type=float, default=2.5)
    parser.add_argument("--batch-limit", type=int, default=50)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--token-env", default="GH_TOKEN", help="Env var holding primary GitHub token.")
    parser.add_argument("--helper-token-env", default="GH_HELPER_TOKEN", help="Env var holding secondary token.")
    return parser


def _resolve_sessions(args: argparse.Namespace) -> tuple[AccountSession, AccountSession | None]:
    cred_store = CredentialStore()

    primary_token = os.environ.get(args.token_env, "").strip()
    if primary_token:
        primary = authenticate_with_token(primary_token, auth_method="env")
    else:
        saved = cred_store.load_session("primary")
        if saved is not None:
            primary = saved
        else:
            primary = authenticate_with_token(import_gh_cli_token(), auth_method="gh_cli")

    secondary: AccountSession | None = None
    helper_token = os.environ.get(args.helper_token_env, "").strip()
    if helper_token:
        secondary = authenticate_with_token(helper_token, auth_method="env")
    else:
        secondary = cred_store.load_session("secondary")

    return primary, secondary


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        pull_target = parse_pull_shark_target(args.pull_shark_target)
        primary, secondary = _resolve_sessions(args)
    except (ValueError, AuthError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    cfg = RunConfig(
        repo_name=args.repo,
        visibility=args.visibility,
        cross_owner_mode=args.cross_owner,
        run_quickdraw=args.quickdraw,
        run_yolo=args.yolo,
        request_secondary_reviewer=args.strict_yolo,
        pull_shark_target=pull_target,
        pair_target=args.pair_count,
        coauthor_username=args.coauthor_username,
        coauthor_email=args.coauthor_email,
        galaxy_target=args.galaxy_count,
        delay_seconds=args.delay_seconds,
        batch_limit=args.batch_limit,
        dry_run=args.dry_run,
    )

    if args.verify_only:
        try:
            owner, repo = resolve_repo_target(primary, secondary, cfg)
        except EngineValidationError as exc:
            print(f"Validation error: {exc}", file=sys.stderr)
            return 2
        report = verify_account_achievements(
            GitHubClient(primary.token),
            primary,
            owner,
            repo,
            coauthor_email=cfg.coauthor_email or (secondary.noreply_email if secondary else None),
        )
        print(f"Actor:             @{report.actor}")
        print(f"Sandbox Repo:      {report.repo_full_name} (exists={report.repo_exists}, archived={report.repo_archived})")
        print(f"Repo Merged PRs:   {report.repo_merged_prs}")
        print(f"Global Merged PRs: {report.global_merged_prs}")
        print(f"Quickdraw Issues:  {report.quickdraw_issues}")
        print(f"Co-authored PRs:   {report.coauthored_prs}")
        print(f"Accepted Answers:  {report.accepted_answers}")
        print(f"API Quota:         {report.rate_limit_remaining}/{report.rate_limit_limit}")
        print(f"Visible Badges:    {', '.join(report.visible_badges) if report.visible_badges else 'None scraped yet'}")
        return 0

    def log_cb(evt: ProgressEvent) -> None:
        if evt.message:
            print(f"[{evt.level}] {evt.message}")

    try:
        engine = AchievementEngine(
            primary=primary,
            secondary=secondary,
            config=cfg,
            state_store=StateStore(),
            on_event=log_cb,
        )
        engine.execute()
    except (EngineValidationError, Exception) as exc:
        print(f"Execution error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
