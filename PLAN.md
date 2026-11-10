# GitHub Profile Achievement Automation — Detailed Plan

## 1. Objective & Scope

Automate unlocking and verifying earnable GitHub Profile Achievements for **`@AgrShubham`** (`https://github.com/AgrShubham`, user ID `98349772`) safely, idempotently, and transparently using a dedicated public sandbox repository (`AgrShubham/github-achievements-sandbox`).

### Current Execution Scope (Approved)
- **Target Account:** `@AgrShubham` (authenticated via GitHub CLI `gh` v2.96.0)
- **Sandbox Repository:** New **public** repository `AgrShubham/github-achievements-sandbox` (cloned locally under `.sandbox/github-achievements-sandbox`, gitignored from this automation workspace)
- **Immediate Single-Account Targets:**
  - **Quickdraw (Default):** Create and close 1 issue within 5 minutes.
  - **YOLO (Default):** Merge a pull request without code review (supports optional `--reviewer <collaborator>` for strictest check).
  - **Pull Shark (Bronze Tier — 16x):** Create and merge **16** pull requests into the repository's default branch.
- **Ready-to-Use Multi-Account Extensions (Built & Tested, Opt-In via CLI Flags):**
  - **Pair Extraordinaire (Default=1, Bronze=10, Silver=24, Gold=48):** Merge PRs containing commits with a valid `Co-authored-by:` trailer linked to a second GitHub user account.
  - **Galaxy Brain (Default=2, Bronze=8, Silver=16, Gold=32):** Answer Q&A Discussions opened by a second GitHub user account and mark the reply as accepted via GraphQL.
- **Scale-Up Path (Silver / Gold Pull Shark):**
  - Idempotent batch resume via `--pull-shark-target silver` (128 PRs) or `--pull-shark-target gold` (1,024 PRs) + `--batch-limit`, plus a reusable GitHub Actions workflow template (`.github/workflows/achievements.yml`).

---

## 2. Environment & Account Audit

Verified against the local workstation and live GitHub API prior to implementation:

| Check | Result |
| --- | --- |
| Active GitHub Account | `AgrShubham` (`id: 98349772`) |
| GitHub CLI Auth Scopes | `gist`, `read:org`, `repo`, `workflow` (via `gh` keyring) |
| Verified Commit Author Emails | `ag.shubham747@gmail.com` and `shubhamagrawal.code@gmail.com` (both confirmed to link commits to `@AgrShubham`) |
| Local Git Config | `user.name=Shubham Agrawal`, `user.email=ag.shubham747@gmail.com`, `init.defaultbranch=master` |
| Git Credential Strategy | Per-invocation `-c credential.helper= -c "credential.helper=!gh auth git-credential"` (avoids interactive GUI credential prompts and never stores tokens in URLs or `.git/config`) |
| Current Public Achievements | None visible yet on `https://github.com/AgrShubham` |
| Sandbox Repo Collision Check | `AgrShubham/github-achievements-sandbox` does not currently exist |

---

## 3. GitHub Profile Achievements Eligibility Matrix

| Achievement | Automatable? | Account Requirement | Tiers | Key GitHub Rules & Caveats |
| --- | --- | --- | --- | --- |
| **Quickdraw** | Yes | Single account | Default: 1 | Close an issue or PR within **5 minutes** of opening (`closedAt - createdAt < 300s`). |
| **Pull Shark** | Yes | Single account | Default: 2, Bronze: 16, Silver: 128, Gold: 1,024 | PRs must be merged into the **default branch** of a **public** repository (private repos fail reliably). |
| **YOLO** | Yes | Single account (optional 2nd collaborator) | Default: 1 | Merge an unreviewed PR. Self-merging works in most cases; passing `--reviewer <collaborator>` requests a collaborator review before merging without review to satisfy strict checks. |
| **Pair Extraordinaire** | Yes (Opt-In) | Primary + valid 2nd GitHub user email | Default: 1, Bronze: 10, Silver: 24, Gold: 48 | Commit inside a merged PR must include a blank line followed by `Co-authored-by: Name <id+user@users.noreply.github.com>`. Must use `--merge` (not squash without preserving trailers). Fake emails and system bots do not qualify. |
| **Galaxy Brain** | Yes (Opt-In) | Primary + 2nd GitHub account token | Default: 2, Bronze: 8, Silver: 16, Gold: 32 | A reply in an answerable Discussion (Q&A) must be marked as the accepted answer by a **different** user (GitHub blocks self-accepted answers from counting). |
| **Starstruck** | No | Community users | 16 / 128 / 512 / 4,096 stars | Requires unique real users starring a repo. |
| **Public Sponsor** | No | Financial sponsorship | 1 active sponsorship | Requires sponsoring an open-source maintainer via GitHub Sponsors. |
| **Finishing Touch** | No | GitHub platform UI PRs | 1 / 4 / 16 / 32 | Requires merged UI quality PRs in GitHub's own/Primer repositories. |
| **Arctic Code Vault / Mars 2020** | Retired | Historical | N/A | Permanently retired; no longer earnable. |
| **Heart On Your Sleeve / Open Sourcerer** | Disabled | Experimental | N/A | Disabled / internal testing only. |

---

## 4. Architecture & Deliverables

All automation lives inside `d:\PROJECTS\Self\Github Achievement Automation`:

1. **`PLAN.md`** — This architectural blueprint, eligibility matrix, execution plan, and verification playbook.
2. **`execute_achievements.py`** — Self-contained Python 3.11+ execution engine (zero third-party pip dependencies; uses standard library + `git` + `gh`):
   - **Preflight Validator:** Checks `gh`, `git`, active GitHub user, rate limits, git author metadata, co-author resolution, and secondary token distinction.
   - **Repository Provisioner:** Creates `AgrShubham/github-achievements-sandbox` if absent, detects default branch dynamically (`main` vs `master`), clones cleanly into `.sandbox/`.
   - **Idempotent State & Delta Engine:** Queries live merged PRs and closed Quickdraw issues before creating anything new so re-runs only create remaining deltas and never duplicate targets.
   - **Rate-Limit & Retry Controller:** Paces PR cycles (`--delay-seconds`, default `2.5s`) and applies exponential backoff + `Retry-After` handling on HTTP `403`/`429` or GitHub secondary rate-limit messages.
   - **Achievement Runners:**
     - `QuickdrawRunner`: Opens and immediately closes a tracked issue as `completed`, then verifies `closedAt - createdAt < 300s`.
     - `PullSharkRunner`: Creates isolated feature branches (`achievement/pr-XXXX`), updates `ACHIEVEMENTS_LOG.md`, commits, pushes via `gh` credential helper, opens PRs, merges with `--merge --delete-branch`, pulls default branch, and saves local state checkpoints in `.achievements-state.json`.
     - `PairExtraordinaireRunner`: Builds commits with validated `Co-authored-by:` trailers (auto-resolving `id+username@users.noreply.github.com` when `--coauthor-username` is provided) and merges with `--merge` so trailers stay intact.
     - `GalaxyBrainRunner`: Enables Discussions (`has_discussions: true`), resolves the Q&A answerable category via GraphQL, creates discussions via helper token (`--helper-token-env`), posts answers via primary token, and marks accepted via helper token.
   - **Verifier:** Checks merged PR counts, closed Quickdraw issue timestamps, and fetches `https://github.com/AgrShubham` + `https://github.com/AgrShubham?tab=achievements` to report unlocked badges (accounting gracefully for GitHub's asynchronous badge indexing delay).
3. **`execute.ps1`** — Windows PowerShell launcher wrapping `execute_achievements.py` with clean parameters (`-Tier`, `-DryRun`, `-VerifyOnly`, etc.).
4. **`.github/workflows/achievements.yml`** — Optional GitHub Actions workflow (`workflow_dispatch` + configurable cron) for scaling to Silver (128) or Gold (1,024) in safe batches on GitHub runners without keeping a local terminal open.
5. **`test_execute_achievements.py`** — Deterministic `unittest` suite validating tier calculations, delta counting, co-author formatting, self-answer rejection, rate-limit retries, and dry-run planning without touching live GitHub APIs.
6. **`README.md` & `.gitignore`** — Usage instructions and workspace hygiene.

---

## 5. Step-by-Step Execution Plan

### Phase 1: Build & Test Locally (Zero External Side Effects)
1. Author `execute_achievements.py`, `execute.ps1`, `.github/workflows/achievements.yml`, `test_execute_achievements.py`, `README.md`, and `.gitignore`.
2. Run `python -m unittest discover -v` to validate all logic offline.
3. Run `python execute_achievements.py --dry-run --pull-shark-target bronze` to inspect the exact execution plan without creating remote repos or PRs.

### Phase 2: Sandbox Provisioning (`AgrShubham/github-achievements-sandbox`)
1. Check if `AgrShubham/github-achievements-sandbox` already exists; if not, create it as `--public` with `--add-readme`.
2. Clone it to `.sandbox/github-achievements-sandbox`, verify the default branch name, and verify local git `user.name` / `user.email`.

### Phase 3: Quickdraw Execution
1. Check for an existing `[Achievement] Quickdraw verification` issue closed in `< 300s`.
2. If none exists, create an issue via `gh issue create` and close it immediately via `gh issue close --reason completed`.
3. Query `createdAt` and `closedAt` to prove closure happened in `< 300s`.

### Phase 4: YOLO + Pull Shark Bronze Execution (16 Merged PRs)
1. Query all existing merged PRs authored by `@AgrShubham` in `AgrShubham/github-achievements-sandbox`.
2. Compute remaining delta `16 - existing_merged`.
3. For each remaining PR `1..delta`:
   - Branch from updated default branch (`achievement/pr-XXXX`).
   - Append a structured milestone entry to `ACHIEVEMENTS_LOG.md`.
   - Commit, push, create PR (`gh pr create`), merge immediately via merge commit without review (`gh pr merge --merge --delete-branch`), pull default branch, and pause `--delay-seconds` (`2.5s`).
   - Save progress checkpoint to `.achievements-state.json`.

### Phase 5: Verification & Profile Check
1. Run `python execute_achievements.py --verify-only` to confirm:
   - `>= 16` merged PRs authored by `@AgrShubham` in `AgrShubham/github-achievements-sandbox`
   - `>= 1` Quickdraw issue closed in `< 300s`
   - Live profile badge scrape on `https://github.com/AgrShubham` / `?tab=achievements`
2. Note: GitHub processes some achievements asynchronously (from seconds up to 24 hours). Also confirm **Settings -> Profile -> Profile settings -> Show Achievements on my profile** (`https://github.com/settings/profile`) is enabled.

### Phase 6: Optional Multi-Account & Scaling Commands (Run Later When Ready)
- **Pair Extraordinaire (e.g., Bronze = 10 PRs):**
  ```powershell
  python execute_achievements.py --pull-shark-target bronze --no-quickdraw --no-yolo --pair-count 10 --coauthor-username <second-github-username>
  ```
- **Galaxy Brain (e.g., Default = 2 accepted answers):**
  ```powershell
  $env:GH_HELPER_TOKEN = "<token-of-second-account>"
  python execute_achievements.py --pull-shark-target bronze --no-quickdraw --no-yolo --galaxy-count 2 --helper-token-env GH_HELPER_TOKEN
  ```
- **Scale Pull Shark to Silver (128) or Gold (1,024) in safe batches:**
  ```powershell
  python execute_achievements.py --pull-shark-target gold --batch-limit 50 --delay-seconds 4.0
  ```

---

## 6. Safety, Rate Limits & Cleanup Policy

- **No Secrets in Code or Git:** Uses `gh` CLI keyring authentication and environment variable indirection (`--helper-token-env`). Never logs tokens or embeds credentials in remote URLs.
- **Anti-Spam & Rate-Limit Protection:** All actions occur strictly inside your own dedicated sandbox repository—never on third-party repositories. Exponential backoff triggers automatically on HTTP `403` / `429`.
- **Clean Rollback / Archival:** Because all artifacts live in a dedicated sandbox repository (`AgrShubham/github-achievements-sandbox`), you can archive the repository (`gh repo archive AgrShubham/github-achievements-sandbox`) after badges appear without affecting your real project repositories. (Avoid deleting the repository if you want to preserve badge evidence/history.)

