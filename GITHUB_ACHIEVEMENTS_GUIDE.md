# Complete Guide to GitHub Profile Achievements & Highlights

*Researched from official GitHub Docs, [`Schweinepriester/github-profile-achievements`](https://github.com/Schweinepriester/github-profile-achievements), and [`drknzz/GitHub-Achievements`](https://github.com/drknzz/GitHub-Achievements).*

---

## 1. How GitHub Profile Achievements Work

GitHub displays two distinct badge groups on a user's public profile sidebar:

1. **Achievements:** Milestone badges automatically awarded based on GitHub activity (pull requests, issues, discussions, stars, sponsorships). Many support **four progressive tiers**: Default (`x1`), Bronze (`x2`), Silver (`x3`), and Gold (`x4`).
2. **Highlights:** Program, subscription, and security-recognition badges (e.g., `Pro`, `Developer Program Member`, `Security Bug Bounty Hunter`).

### Key Profile & Visibility Rules

| Setting / Behavior | Details |
| --- | --- |
| **Enable/Disable Achievements** | **Settings -> Public profile -> Profile settings -> Show Achievements on my profile** (`https://github.com/settings/profile`). If unchecked, earned badges and `?tab=achievements` stay hidden. |
| **Zero-Badge 404 Behavior** | Visiting `https://github.com/<username>?tab=achievements` returns **HTTP 404** until at least one achievement has been earned and indexed. |
| **Public vs. Private Repos** | Public repositories trigger achievements reliably. Activity in **private repositories** is hidden by default; enabling **Contribution settings -> Private contributions** on your profile allows private activity to appear anonymized (linked repos show as *inaccessible*), though private-repo triggers are inconsistent for several badges. |
| **Commit Email Attribution** | Git commit author emails **must** match a verified email on your GitHub account (or your GitHub noreply email `<id>+<username>@users.noreply.github.com`). Unverified emails break attribution. |
| **Processing Latency** | `Quickdraw` and `YOLO` often evaluate within seconds via webhook; `Pull Shark`, `Pair Extraordinaire`, and `Galaxy Brain` run in asynchronous backend queues that commonly lag **hours to several days (24–48h+)**. |
| **Emoji Skin-Tone Preference** | Set at **Settings -> Appearance -> Emoji skin tone preference** (`https://github.com/settings/appearance`). Changes the hand/person artwork on **Starstruck** and **Quickdraw** (`👋`, `👋🏻`, `👋🏼`, `👋🏽`, `👋🏾`, `👋🏿`). |

### Achievement Tier Visual Tokens

| Tier | Profile Label | Badge Accent Hex |
| --- | --- | --- |
| Default | *(no multiplier)* | Standard badge |
| Bronze 🥉 | `x2` | `#F9BFA7` |
| Silver 🥈 | `x3` | `#E1E4E4` |
| Gold 🥇 | `x4` | `#FAE57E` |

---

## 2. Active & Earnable GitHub Achievements

| Achievement | Criteria | Default (`x1`) | Bronze (`x2`) | Silver (`x3`) | Gold (`x4`) | Automation Feasibility |
| --- | --- | --- | --- | --- | --- | --- |
| **Quickdraw** | Close an issue or pull request within **5 minutes** of opening it. | `1` | — | — | — | **Single-account automated** |
| **YOLO** | Merge a pull request without a code review. | `1` | — | — | — | **Single-account automated** *(optional collaborator reviewer)* |
| **Pull Shark** | Open pull requests that get **merged** into the default branch. | `2` | `16` | `128` | `1,024` | **Automated** *(see own-repo caveat below)* |
| **Pair Extraordinaire** | Author or co-author commits with a valid `Co-authored-by:` trailer in a merged PR. | `1` | `10` | `24` | `48` | **Automated (requires valid 2nd GitHub user email)** |
| **Galaxy Brain** | Have replies in GitHub Discussions (Q&A) marked as **Accepted Answer**. | `2` | `8` | `16` | `32` | **Automated (requires 2nd GitHub account)** |
| **Starstruck** | Own a public repository that reaches star milestones from unique users. | `16` | `128` | `512` | `4,096` | **Not legitimately automatable** |
| **Public Sponsor** | Sponsor an open-source contributor or project via GitHub Sponsors. | `1` | — | — | — | **Manual / Financial** |
| **Finishing Touch** | Author merged pull requests improving GitHub's own UI quality (e.g., Primer / GitHub UI). | `1` | `4` | `16` | `32` | **Practically GitHub UI / staff only** |

---

### Detailed Breakdown of Each Earnable Badge

#### 1. Quickdraw
- **How to earn:** Open an issue (or pull request) and close it within **5 minutes (`< 300 seconds`)** of creation.
- **Tiers:** Single tier (`1` action).
- **Caveats:** Must be closed cleanly (`completed` works consistently). Appears almost immediately on public profiles and supports skin-tone variants.

#### 2. YOLO
- **How to earn:** Merge a pull request without any submitted code reviews.
- **Tiers:** Single tier (`1` PR).
- **Caveats:** In most repositories, opening a PR and merging it directly without a review triggers `YOLO` immediately. In stricter cases reported by users, assigning an accepted repository collaborator as a requested reviewer and merging **before** they review guarantees satisfaction of the check. Branch protection rules requiring approvals must not block the merge.

#### 3. Pull Shark
- **How to earn:** Open pull requests that are **merged** (purple *Merged* state, not red *Closed*) into a repository's **default branch** (`main` or `master`).
- **Tiers:** `2` (Default), `16` (Bronze `x2`), `128` (Silver `x3`), `1,024` (Gold `x4`).
- **Critical Rules & Caveats:**
  - Direct pushes to `main`/`master` do **not** count — commits must go through a PR merge.
  - Forks of your own repository back to your own repository generally do **not** count.
  - **Anti-farming / Own-repo caveat:** Historically, solo PR merges in your own public sandbox counted; however, GitHub periodically filters solo self-merges or stalls them in delayed queues. PRs merged into repositories owned by **another user or external open-source project** count most reliably.
  - Indexing lag commonly ranges from hours to 24–48+ hours.

#### 4. Pair Extraordinaire
- **How to earn:** Include a properly formatted `Co-authored-by:` commit trailer on a commit inside a **merged** pull request.
- **Tiers:** `1` (Default), `10` (Bronze `x2`), `24` (Silver `x3`), `48` (Gold `x4`).
- **Critical Rules & Caveats:**
  - Exact commit message structure (blank line required before trailer):
    ```text
    feat: collaborative update

    Co-authored-by: Partner Name <1234567+partner@users.noreply.github.com>
    ```
  - The co-author email **must** resolve to a real GitHub user account (either a verified email on their account or `<id>+<login>@users.noreply.github.com`). Arbitrary/fake emails fail silently, and GitHub system bots (`github-actions[bot]`) do not qualify.
  - Merge strategy matters: using **Create a merge commit** (`--merge`) preserves individual commit trailers on the default branch, whereas squash merges only count if the squash commit message itself includes the `Co-authored-by:` trailer.

#### 5. Galaxy Brain
- **How to earn:** Post replies in repository **GitHub Discussions** (an answerable category such as **Q&A**) that are marked as the **Accepted Answer**.
- **Tiers:** `2` (Default), `8` (Bronze `x2`), `16` (Silver `x3`), `32` (Gold `x4`).
- **Critical Rules & Caveats:**
  - **No self-accepting:** GitHub prevents marking your own reply as the accepted answer on your own discussion thread from counting toward Galaxy Brain. A separate user (question author or repo maintainer) must accept your reply.
  - **Community Discussions excluded:** Since **February 6, 2024**, replies in `github.com/orgs/community/discussions` no longer award achievements to curb spam. Discussions must live inside standard public repositories with Discussions enabled.

#### 6. Starstruck
- **How to earn:** Create and own a public repository that collects stars from unique GitHub users (`16` / `128` / `512` / `4,096`).
- **Caveats:** Stars from your own account don't scale beyond 1; requires genuine external developer stars. Unstarring below a threshold can affect progress.

#### 7. Public Sponsor
- **How to earn:** Financially sponsor at least one eligible open-source developer or organization through **GitHub Sponsors** (`https://github.com/sponsors`).
- **Caveats:** Requires an active billing method and valid sponsorship payment (minimum tier depends on the maintainer, often \$1+/month or one-time where supported).

#### 8. Finishing Touch
- **How to earn:** Author merged pull requests that improved GitHub's own UI quality (`1` / `4` / `16` / `32`).
- **Caveats:** Tied to GitHub's internal UI/Primer platform repositories and predominantly awarded to GitHub staff and core design-system contributors.

---

## 3. Disabled, Retired & Internal Achievements (Cannot Be Earned)

| Achievement | Status | Original / Known Criteria |
| --- | --- | --- |
| **Arctic Code Vault Contributor** | ❌ **Retired** | Contributed code to an eligible repository captured in the **2020 GitHub Archive Program**. |
| **Mars 2020 Contributor** | ❌ **Retired** | Contributed code to specific open-source library versions used in NASA's **Mars 2020 Ingenuity Helicopter** mission. |
| **Heart On Your Sleeve** | ❌ **Disabled (Testing)** | Reacted to an item on GitHub with a `❤️` emoji during brief internal rollouts. Removed from production profiles. |
| **Open Sourcerer** | ❌ **Disabled (Testing)** | Merged PRs across multiple distinct public open-source repositories (`1` / `8` / `16` / `64`). Currently disabled. |
| **Proxima Pioneer** | ❌ **Internal (GitHub Staff)** | M0 Participant ("contributed to Proxima POC"). |
| **Proxima Staffshipper** | ❌ **Internal (GitHub Staff)** | M8 Participant ("shipped Proxima Staff instance"). |
| **Proxima Staffuser** | ❌ **Internal (GitHub Staff)** | Team onboarded to Proxima internally at GitHub. |

---

## 4. GitHub Profile Highlights

Highlights appear in a separate **Highlights** block below your Achievements sidebar:

| Highlight Badge | How to Obtain | Notes |
| --- | --- | --- |
| **GitHub Pro (`PRO`)** | Subscribe to GitHub Pro or verify student status via the **GitHub Student Developer Pack**. | Active subscription required to retain display. |
| **Developer Program Member** | Register for free in the **GitHub Developer Program** (`https://github.com/settings/developers` / Developer Program signup) with a valid support email while building a GitHub API integration/app. | Active and free; showcases that you build tools on the GitHub API. |
| **Security Bug Bounty Hunter** | Report a valid, accepted vulnerability to the **GitHub Security Bug Bounty** program (`https://bounty.github.com/`). | Requires verified security vulnerability disclosure. |
| **GitHub Campus Expert** | Apply, complete training, and graduate in the **GitHub Campus Experts** student leadership program (`https://education.github.com/experts`). | Student-only program. |
| **Security Advisory Credit** | Receive reporter/contributor credit on a published advisory in the **GitHub Advisory Database** (`https://github.com/advisories`). | Credited automatically when a repo maintainer publishes the advisory listing your handle. |

---

## 5. Authoritative References

- GitHub Docs — [Personalizing your profile: Displaying badges on your profile](https://docs.github.com/en/account-and-profile/setting-up-and-managing-your-github-profile/customizing-your-profile/personalizing-your-profile#displaying-badges-on-your-profile)
- GitHub Docs — [Showing your private contributions and achievements on your profile](https://docs.github.com/en/account-and-profile/setting-up-and-managing-your-github-profile/managing-contribution-settings-on-your-profile/showing-your-private-contributions-and-achievements-on-your-profile)
- GitHub Docs — [Creating a commit with multiple authors](https://docs.github.com/en/pull-requests/committing-changes-to-your-project/creating-and-editing-commits/creating-a-commit-with-multiple-authors)
- Community Reference — [`Schweinepriester/github-profile-achievements`](https://github.com/Schweinepriester/github-profile-achievements)
- Community Reference — [`drknzz/GitHub-Achievements`](https://github.com/drknzz/GitHub-Achievements)

