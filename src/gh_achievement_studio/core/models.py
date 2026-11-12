"""Domain models, badge metadata catalog, and execution configuration types."""

from __future__ import annotations

import dataclasses
from enum import Enum
from typing import Any

PULL_SHARK_TIERS: dict[str, int] = {
    "none": 0,
    "default": 2,
    "bronze": 16,
    "silver": 128,
    "gold": 1024,
}

PAIR_TIERS: dict[str, int] = {
    "none": 0,
    "default": 1,
    "bronze": 10,
    "silver": 24,
    "gold": 48,
}

GALAXY_TIERS: dict[str, int] = {
    "none": 0,
    "default": 2,
    "bronze": 8,
    "silver": 16,
    "gold": 32,
}


class BadgeCategory(str, Enum):
    AUTO_SINGLE = "auto_single"
    AUTO_DUAL = "auto_dual"
    MANUAL = "manual"
    UNAVAILABLE = "unavailable"


@dataclasses.dataclass(frozen=True)
class BadgeCatalogItem:
    key: str
    name: str
    category: BadgeCategory
    summary: str
    tiers: str
    notes: str


BADGE_CATALOG: tuple[BadgeCatalogItem, ...] = (
    BadgeCatalogItem(
        key="quickdraw",
        name="Quickdraw",
        category=BadgeCategory.AUTO_SINGLE,
        summary="Close an issue or PR within 5 minutes of opening.",
        tiers="Default (1)",
        notes="Works instantly via single account.",
    ),
    BadgeCatalogItem(
        key="yolo",
        name="YOLO",
        category=BadgeCategory.AUTO_SINGLE,
        summary="Merge a pull request without code review.",
        tiers="Default (1)",
        notes="Single account works in most repos; optional 2nd reviewer supported for strict check.",
    ),
    BadgeCatalogItem(
        key="pull-shark",
        name="Pull Shark",
        category=BadgeCategory.AUTO_SINGLE,
        summary="Merge pull requests into the repository default branch.",
        tiers="Default (2), Bronze (16), Silver (128), Gold (1,024)",
        notes="Enable Cross-Owner Mode (2nd account) if GitHub delays/filters solo-repo PRs.",
    ),
    BadgeCatalogItem(
        key="pair-extraordinaire",
        name="Pair Extraordinaire",
        category=BadgeCategory.AUTO_DUAL,
        summary="Co-author commits inside merged pull requests.",
        tiers="Default (1), Bronze (10), Silver (24), Gold (48)",
        notes="Requires a real second GitHub user's verified or noreply email and merge commit.",
    ),
    BadgeCatalogItem(
        key="galaxy-brain",
        name="Galaxy Brain",
        category=BadgeCategory.AUTO_DUAL,
        summary="Have Q&A Discussion replies marked as Accepted Answer.",
        tiers="Default (2), Bronze (8), Silver (16), Gold (32)",
        notes="Requires a second GitHub account (GitHub blocks self-accepted answers).",
    ),
    BadgeCatalogItem(
        key="starstruck",
        name="Starstruck",
        category=BadgeCategory.MANUAL,
        summary="Own a public repository earning stars from unique users.",
        tiers="Default (16), Bronze (128), Silver (512), Gold (4,096)",
        notes="Cannot be safely automated (fake star rings violate GitHub ToS).",
    ),
    BadgeCatalogItem(
        key="public-sponsor",
        name="Public Sponsor",
        category=BadgeCategory.MANUAL,
        summary="Sponsor an open-source contributor via GitHub Sponsors.",
        tiers="Default (1)",
        notes="Requires active financial sponsorship on github.com/sponsors.",
    ),
    BadgeCatalogItem(
        key="developer-program",
        name="Developer Program Member",
        category=BadgeCategory.MANUAL,
        summary="Profile Highlight for registered GitHub API tool developers.",
        tiers="Highlight Badge",
        notes="Free to enroll at github.com/settings/developers with a valid support email.",
    ),
    BadgeCatalogItem(
        key="github-pro",
        name="GitHub Pro",
        category=BadgeCategory.MANUAL,
        summary="Profile Highlight for GitHub Pro subscribers or Student Pack members.",
        tiers="Highlight Badge",
        notes="Free for verified students via GitHub Education.",
    ),
    BadgeCatalogItem(
        key="finishing-touch",
        name="Finishing Touch",
        category=BadgeCategory.UNAVAILABLE,
        summary="Merge PRs improving GitHub's own UI quality (Primer/GitHub UI).",
        tiers="1 / 4 / 16 / 32",
        notes="Practically restricted to GitHub UI contributors and staff.",
    ),
    BadgeCatalogItem(
        key="arctic-code-vault",
        name="Arctic Code Vault Contributor",
        category=BadgeCategory.UNAVAILABLE,
        summary="2020 GitHub Archive Program historical badge.",
        tiers="Retired",
        notes="No longer earnable.",
    ),
    BadgeCatalogItem(
        key="mars-2020",
        name="Mars 2020 Contributor",
        category=BadgeCategory.UNAVAILABLE,
        summary="Contributed to Mars 2020 Ingenuity helicopter mission repositories.",
        tiers="Retired",
        notes="No longer earnable.",
    ),
    BadgeCatalogItem(
        key="heart-on-your-sleeve",
        name="Heart On Your Sleeve",
        category=BadgeCategory.UNAVAILABLE,
        summary="Experimental heart-reaction achievement.",
        tiers="Disabled",
        notes="Disabled by GitHub.",
    ),
    BadgeCatalogItem(
        key="open-sourcerer",
        name="Open Sourcerer",
        category=BadgeCategory.UNAVAILABLE,
        summary="Experimental multi-repo open-source PR achievement.",
        tiers="Disabled",
        notes="Disabled by GitHub.",
    ),
)


@dataclasses.dataclass(frozen=True)
class AccountSession:
    login: str
    user_id: int
    name: str
    commit_email: str
    token: str
    avatar_url: str = ""
    scopes: tuple[str, ...] = ()
    auth_method: str = "pat"

    @property
    def noreply_email(self) -> str:
        return f"{self.user_id}+{self.login}@users.noreply.github.com"

    def to_dict(self) -> dict[str, Any]:
        return {
            "login": self.login,
            "user_id": self.user_id,
            "name": self.name,
            "commit_email": self.commit_email,
            "token": self.token,
            "avatar_url": self.avatar_url,
            "scopes": list(self.scopes),
            "auth_method": self.auth_method,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AccountSession:
        return cls(
            login=str(data["login"]),
            user_id=int(data["user_id"]),
            name=str(data.get("name") or data["login"]),
            commit_email=str(data["commit_email"]),
            token=str(data["token"]),
            avatar_url=str(data.get("avatar_url") or ""),
            scopes=tuple(str(s) for s in data.get("scopes") or ()),
            auth_method=str(data.get("auth_method") or "pat"),
        )


@dataclasses.dataclass(frozen=True)
class RunConfig:
    repo_name: str = "github-achievements-sandbox"
    visibility: str = "public"
    cross_owner_mode: bool = False
    run_quickdraw: bool = True
    run_yolo: bool = True
    request_secondary_reviewer: bool = False
    pull_shark_target: int = 16
    pair_target: int = 0
    coauthor_username: str = ""
    coauthor_name: str = ""
    coauthor_email: str = ""
    galaxy_target: int = 0
    delay_seconds: float = 2.5
    batch_limit: int | None = 50
    dry_run: bool = False


@dataclasses.dataclass(frozen=True)
class PlanPreview:
    repo_owner: str
    repo_name: str
    visibility: str
    repo_exists: bool
    cross_owner_mode: bool
    existing_merged_prs: int
    existing_coauthored_prs: int
    existing_quickdraw_issues: int
    existing_accepted_answers: int
    quickdraw_to_create: int
    pair_prs_to_create: int
    pull_shark_prs_to_create: int
    galaxy_answers_to_create: int
    estimated_seconds: float
    coauthor_display: str = ""
    warnings: tuple[str, ...] = ()

    @property
    def full_repo(self) -> str:
        return f"{self.repo_owner}/{self.repo_name}"

    @property
    def total_prs_to_create(self) -> int:
        return self.pair_prs_to_create + self.pull_shark_prs_to_create


@dataclasses.dataclass(frozen=True)
class ProgressEvent:
    kind: str  # "log" | "progress" | "stage" | "completed" | "error" | "cancelled"
    message: str
    level: str = "INFO"
    current: int = 0
    total: int = 0
    stage: str = ""


@dataclasses.dataclass(frozen=True)
class VerificationReport:
    actor: str
    repo_full_name: str
    repo_exists: bool
    repo_archived: bool
    repo_url: str
    profile_url: str
    achievements_url: str
    repo_merged_prs: int
    global_merged_prs: int
    coauthored_prs: int
    quickdraw_issues: int
    accepted_answers: int
    visible_badges: tuple[str, ...]
    rate_limit_remaining: int
    rate_limit_limit: int
