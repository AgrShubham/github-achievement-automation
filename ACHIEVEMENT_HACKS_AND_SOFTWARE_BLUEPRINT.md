# GitHub Achievement Automation Hacks & Software Architecture Blueprint

This document covers:
1. **Exact programmatic techniques ("hacks")** for unlocking every earnable achievement on **`@AgrShubham`** (and any user profile), including real-world edge cases observed during live testing.
2. **A complete software architecture blueprint** for turning [execute_achievements.py](file:///d:/PROJECTS/Self/Github%20Achievement%20Automation/execute_achievements.py) into a public, easy-to-use tool (CLI, Web App, or Desktop App) that lets any user unlock eligible achievements safely without touching terminal commands.

> **Important Policy & Safety Notice**
> Automate **only** inside dedicated sandbox repositories you control (or with a consenting partner account). Never spam third-party open-source repositories, never use fake/unsolicited emails to attribute commits to strangers, and never attempt fake-star botnets — those violate GitHub's Acceptable Use Policies and can get accounts suspended or shadow-filtered from achievement queues.

---

## Part 1: Achievement-by-Achievement Technical Playbook (`@AgrShubham`)

### Current Baseline Observed on `@AgrShubham`
- **Already Unlocked & Visible:** `Quickdraw`, `YOLO` (via `AgrShubham/github-achievements-sandbox`).
- **Completed Locally / Pending Queue:** `17` merged PRs authored by `@AgrShubham` (`Merged PRs (Repo): 17`, `Merged PRs (Global): 17`) with verified email `ag.shubham747@gmail.com`.
- **Key Live Observation:** `Quickdraw` and `YOLO` registered almost immediately, whereas `Pull Shark` remained queued after 10+ hours — confirming GitHub's asynchronous Pull Shark worker lag and potential solo-repo anti-farming filtering.

---

### Hack 1: Quickdraw (100% Instant, Single Account)
- **Goal:** Open an issue and close it within `< 300s`.
- **Mechanism:**
  1. `POST /repos/{owner}/{repo}/issues` -> `{"title": "[Achievement] Quickdraw", "body": "..."}`
  2. Immediately `PATCH /repos/{owner}/{repo}/issues/{issue_number}` -> `{"state": "closed", "state_reason": "completed"}`
- **Verification Check:** Assert `(closed_at - created_at) < 300`.
- **Status on `@AgrShubham`:** Already unlocked (`issue #1`, closed in `2.0s`).

---

### Hack 2: YOLO (Instant, Single Account + Strict Collaborator Trick)
- **Goal:** Merge a PR without any submitted reviews.
- **Fast Method (already succeeded on `@AgrShubham`):**
  1. Create a branch from `main`, push 1 file change, open a PR, and merge via `PUT /repos/{owner}/{repo}/pulls/{n}/merge` (`merge_method: "merge"`).
- **Strict Fallback Trick (if another user's profile doesn't trigger from solo merges):**
  1. Invite a second consenting account as a repository collaborator and accept the invite.
  2. Open the PR with `"reviewers": ["<second-account>"]` (`POST /repos/{owner}/{repo}/pulls/{n}/requested_reviewers`).
  3. Merge the PR immediately **before** the requested reviewer submits any review.

---

### Hack 3: Pull Shark (Default=2, Bronze=16, Silver=128, Gold=1,024)

#### Standard Automated Flow
1. Create branch from `main` -> commit change -> push -> `POST /pulls` -> `PUT /pulls/{n}/merge` (`merge_method: "merge"`) -> delete branch (`DELETE /git/refs/heads/{branch}`).
2. **Idempotency Hack:** Always query `repository.pullRequests(states: MERGED)` via GraphQL first and create only `target - existing_count` PRs.
3. **Rate-Limit Shield:**
   - Pause `2.5s–4.0s` between PRs (~12–16 PRs/min, well under GitHub's secondary rate limit).
   - For Silver (`128`) or Gold (`1,024`), process in **batches** (`--batch-limit 50` per run or via GitHub Actions `workflow_dispatch` / daily cron).
   - **GitHub Actions Gotcha:** Never use the default `secrets.GITHUB_TOKEN` to open PRs — that sets PR author to `github-actions[bot]`. Always use the user's OAuth token / `ACHIEVEMENTS_PAT`.

#### Cross-Account Anti-Farming Workaround (If Solo Self-Merged PRs Stall)
If `Pull Shark` stays pending beyond 48 hours on `AgrShubham/github-achievements-sandbox`, GitHub's anti-farming heuristic may be ignoring PRs where **repo owner == PR author == PR merger**:
- **Fix:** Have a **second account (`Account B`)** own the public sandbox repository (`AccountB/collab-sandbox`) and either:
  1. Fork `AccountB/collab-sandbox` to `AgrShubham`, open PRs from `AgrShubham:branch` -> `AccountB:main`, and merge them using `Account B`'s token; **or**
  2. Add `@AgrShubham` as a collaborator on `AccountB/collab-sandbox`, have `@AgrShubham` push branches and open PRs, and have `Account B` merge them via `PUT /repos/AccountB/collab-sandbox/pulls/{n}/merge`.
- This mimics genuine cross-account collaboration (different repo owner, different merger, real PR flow).

#### "Gitless" Speed Hack (Git Data API — Best for Software)
Instead of running slow local `git clone` / `git checkout` / `git push` commands (which fail on serverless hosts without `git` or local disk), your software can create branches and commits **purely over HTTPS REST calls**:
1. `GET /repos/{owner}/{repo}/git/ref/heads/main` -> get base commit SHA.
2. `GET /repos/{owner}/{repo}/git/commits/{sha}` -> get base `tree.sha`.
3. `POST /repos/{owner}/{repo}/git/blobs` -> upload updated `ACHIEVEMENTS_LOG.md` content.
4. `POST /repos/{owner}/{repo}/git/trees` -> create new tree (`base_tree` + blob).
5. `POST /repos/{owner}/{repo}/git/commits` -> create commit (including `author` + `committer` with user's verified email, and optional `Co-authored-by:` trailer!).
6. `POST /repos/{owner}/{repo}/git/refs` -> create `refs/heads/achievement/pr-0001`.
7. `POST /repos/{owner}/{repo}/pulls` -> open PR.
8. `PUT /repos/{owner}/{repo}/pulls/{n}/merge` -> merge commit (`"merge_method": "merge"`).
9. `DELETE /repos/{owner}/{repo}/git/refs/heads/achievement/pr-0001` -> clean up branch.

---

### Hack 4: Pair Extraordinaire (Default=1, Bronze=10, Silver=24, Gold=48)
- **Exact Requirement:** A merged PR containing a commit with a valid `Co-authored-by:` footer belonging to another real GitHub user account.
- **Working Hack:**
  1. Look up the second GitHub user's numeric ID via `GET https://api.github.com/users/{partner_username}` (`id`, `login`, `name`).
  2. Construct their guaranteed-valid GitHub noreply email:
     ```text
     {id}+{login}@users.noreply.github.com
     ```
  3. Format the commit message with a **mandatory blank line** before the trailer:
     ```text
     chore(achievements): pair milestone #001

     Co-authored-by: Partner Name <1234567+partner@users.noreply.github.com>
     ```
  4. Merge using **`merge_method: "merge"`** (never squash unless the squash message repeats the `Co-authored-by:` line).
- **Important:** Never use random strangers' usernames (creates unwanted attribution/spam). Use a consenting friend or second account you own.
- **Ready in this repo:**
  ```powershell
  python execute_achievements.py --pull-shark-target bronze --no-quickdraw --no-yolo --pair-count 10 --coauthor-username <second-username>
  ```

---

### Hack 5: Galaxy Brain (Default=2, Bronze=8, Silver=16, Gold=32)
- **Exact Requirement:** Answer Q&A Discussions in a public repo and have a **different user** mark your reply as the Accepted Answer.
- **Automated Two-Account GraphQL Hack:**
  1. Enable Discussions on the sandbox repo: `PATCH /repos/{owner}/{repo}` with `{"has_discussions": true}`.
  2. Query GraphQL `repository.discussionCategories` for the category with `isAnswerable == true` (default: `Q&A`).
  3. **Account B** calls `createDiscussion` mutation in that Q&A category.
  4. **Account A** (`@AgrShubham`) calls `addDiscussionComment` mutation to reply.
  5. **Account B** calls `markDiscussionCommentAsAnswer` mutation on Account A's `comment.id`.
- **Ready in this repo:**
  ```powershell
  $env:GH_HELPER_TOKEN = "<second-account-pat>"
  python execute_achievements.py --pull-shark-target bronze --no-quickdraw --no-yolo --galaxy-count 2 --helper-token-env GH_HELPER_TOKEN
  ```

---

### Hack 6: Easy Highlights & Paid/Community Badges

| Badge | Legitimate Shortcut / "Hack" |
| --- | --- |
| **Developer Program Member** *(Highlight)* | Free and instant to enroll at `https://github.com/settings/developers` while building your achievement software (just provide a project URL & support email). |
| **GitHub Pro** *(Highlight)* | Free if eligible for the **GitHub Student Developer Pack** (`https://education.github.com/pack`), otherwise paid Pro plan. |
| **Public Sponsor** *(Achievement)* | Sponsor a maintainer on GitHub Sponsors with a small tier (some maintainers allow \$1 one-time or monthly tiers). |
| **Starstruck** *(16 / 128 / 512 / 4,096 stars)* | **Do NOT automate with fake accounts** (violates GitHub ToS and risks suspension). In your software, offer legitimate growth helpers: README badge generator, topic/tag SEO checklist, or opt-in community showcase directory where real users star genuinely useful tools. |
| **Finishing Touch / Retired / Disabled** | Mark clearly as **Not Automatable** (`Arctic Code Vault`, `Mars 2020`, `Heart On Your Sleeve`, `Open Sourcerer`, `Proxima *`, `Finishing Touch`). |

---

## Part 2: Software Architecture for a Universal Achievement Tool

To turn [execute_achievements.py](file:///d:/PROJECTS/Self/Github%20Achievement%20Automation/execute_achievements.py) into a product **anyone** can use effortlessly (Web App, Desktop App, or One-Command CLI):

### 1. Recommended System Architecture

```text
+-------------------------------------------------------------------+
| Frontend (Web UI / Electron / Tauri / Interactive CLI)            |
|  - GitHub OAuth / Device Flow Login                               |
|  - Achievement Checklist + Current Profile Scraper                |
|  - Tier Picker (Quickdraw, YOLO, Pull Shark, Pair, Galaxy Brain)  |
|  - Optional Buddy/Second-Account Pairing Flow                     |
+---------------------------------+---------------------------------+
                                  |
                                  v
+-------------------------------------------------------------------+
| Orchestration API & Job Queue (FastAPI / Node + Redis / BullMQ)   |
|  - Preflight Validator (verified emails, rate limits, repo check) |
|  - Idempotent Delta Planner (GraphQL merged PR + issue count)     |
|  - Paced Batch Scheduler (prevents HTTP 403/429 secondary limits) |
|  - Retry & Exponential Backoff Engine (respects Retry-After)      |
+---------------------------------+---------------------------------+
                                  |
                                  v
+-------------------------------------------------------------------+
| Gitless GitHub Engine (Pure HTTPS REST + GraphQL, No Local Git)   |
|  - Git Data API: Blobs -> Trees -> Commits -> Refs -> Pulls       |
|  - Issues API: Create + Close (< 5s)                              |
|  - Discussions GraphQL: Create -> Reply -> Mark Accepted Answer   |
|  - Profile Verifier: HTML Badge Card & Global Search Inspector    |
+-------------------------------------------------------------------+
```

### 2. Core Engineering Decisions for Multi-User Software

1. **Zero-Friction Authentication (OAuth Device Flow or GitHub App):**
   - **CLI / Desktop App:** Use GitHub **OAuth Device Flow** (`POST https://github.com/login/device/code`) — the user clicks one browser link and enters an 8-character code; no copying PATs or installing `gh` CLI required.
   - **Web App:** Standard GitHub OAuth Web Flow (`repo`, `read:user`, `user:email`, `write:discussion` scopes) + encrypted short-lived session storage (never store user tokens permanently in plaintext).
2. **Pure Git Data API Engine (No `git` Binary Needed):**
   - Port [`execute_single_pr_cycle`](file:///d:/PROJECTS/Self/Github%20Achievement%20Automation/execute_achievements.py#L677-L767) from local `git` subprocesses to GitHub's REST Git Data API (`blobs` -> `trees` -> `commits` -> `refs` -> `pulls` -> `merge`). This eliminates OS/path issues, credential helper popups, and local `.sandbox` disk cleanup.
3. **Automatic Verified Email Lookup:**
   - Query `GET /user/emails` (with `user:email` scope) and select the primary verified email (or `<id>+<login>@users.noreply.github.com`) automatically when constructing commits via Git Data API so commits never fail attribution due to misconfigured local git emails.
4. **Two-User / Buddy Pairing Mode (Unlocks Everything Safely):**
   - Include a **"Pair With a Friend / Second Account"** mode in the UI:
     - User A creates `repo-a` and invites User B (and vice versa).
     - The software coordinates mutual `Pair Extraordinaire` trailers, `Galaxy Brain` Q&A answers, strict `YOLO` reviewer requests, and cross-owner `Pull Shark` merges — making even strict anti-farming checks pass legitimately!
5. **Rate-Limit & Anti-Abuse Guardrails:**
   - Hard cap single-burst PR creation (e.g., max `25–50` PRs per batch with `3–4s` spacing), queuing larger targets (`Silver=128`, `Gold=1,024`) over scheduled background runs.
   - Require explicit user confirmation showing exactly how many public PRs/issues/commits will be added to their GitHub contribution graph.
   - Provide a **1-click Sandbox Archiver** (`PATCH /repos/{owner}/{repo}` `{"archived": true}`) once badges appear, warning users **not** to delete the sandbox repo if they want badge details preserved.
6. **Honest Achievement Capability Matrix in UI:**
   - Show clear status tags for every badge:
     - `Auto (Single Account)`: `Quickdraw`, `YOLO`, `Pull Shark`
     - `Auto (2nd Account / Buddy)`: `Pair Extraordinaire`, `Galaxy Brain`
     - `Legit / Manual Only`: `Starstruck`, `Public Sponsor`, `Developer Program Member`, `GitHub Pro`
     - `Unavailable (Retired / Disabled / Staff)`: `Arctic Code Vault`, `Mars 2020`, `Heart On Your Sleeve`, `Open Sourcerer`, `Finishing Touch`, `Proxima *`

### 3. Suggested Migration Path from This Workspace
1. **Current Prototype:** [execute_achievements.py](file:///d:/PROJECTS/Self/Github%20Achievement%20Automation/execute_achievements.py) already implements preflight validation, idempotent GraphQL delta counting, rate-limit backoff, co-author resolution, GraphQL Discussions automation, and profile HTML badge scraping ([`parse_achievement_badges`](file:///d:/PROJECTS/Self/Github%20Achievement%20Automation/execute_achievements.py#L1026-L1039)).
2. **Next Step (v2 Engine):** Replace local `run_git(...)` calls with the Git Data API (`create_blob` -> `create_tree` -> `create_commit` -> `create_ref`) and add OAuth Device Flow (`device/code` polling) + `merger_token` support for cross-owner `Pull Shark` runs.
3. **v3 UI Wrapper:** Expose the Python engine behind a lightweight FastAPI/React web dashboard or local Streamlit/Tauri UI with live progress streaming and a post-run badge verification dashboard.

