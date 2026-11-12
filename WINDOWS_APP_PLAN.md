# Windows Desktop Application Plan — GitHub Achievement Studio

**Goal:** Build a standalone, user-friendly Windows 10/11 desktop application (**GitHub Achievement Studio**) that enables any user to unlock, track, scale, and verify earnable GitHub profile achievements with zero terminal commands and **zero prerequisite installations** (no local `git`, `gh` CLI, or Python runtime required by end users).

This plan builds directly on the existing engine and research in:
- [execute_achievements.py](file:///d:/PROJECTS/Self/Github%20Achievement%20Automation/execute_achievements.py)
- [GITHUB_ACHIEVEMENTS_GUIDE.md](file:///d:/PROJECTS/Self/Github%20Achievement%20Automation/GITHUB_ACHIEVEMENTS_GUIDE.md)
- [ACHIEVEMENT_HACKS_AND_SOFTWARE_BLUEPRINT.md](file:///d:/PROJECTS/Self/Github%20Achievement%20Automation/ACHIEVEMENT_HACKS_AND_SOFTWARE_BLUEPRINT.md)

---

## 1. Workstation Baseline & Recommended Technology Stack

### Verified Host Environment (`Windows 11 x64`, Build `22631`)
- **Python:** `3.11.9` (Tkinter `8.6` available)
- **Bundler:** `PyInstaller 6.22.2` + `pywin32-ctypes 0.2.3` + `uv 0.11.32` (all preinstalled)
- **.NET SDK:** `10.0.302`
- **Node.js:** `v25.9.0`
- **Not installed:** Rust/Cargo (`rustc`), Inno Setup (`iscc`), NSIS (`makensis`)

### UI Framework Selection

| Option | Pros | Cons | Verdict |
| --- | --- | --- | --- |
| **Python + `PySide6` (Qt 6) + `PyInstaller`** | Native-grade Windows 11 DPI scaling, built-in `QThread` async workers, rich progress/table/card widgets, zero localhost port exposure, reuses 100% of existing Python core logic | Slightly larger `.exe` (~50–65 MB) | **Recommended** |
| **Python + `CustomTkinter` + `PyInstaller`** | Compact `.exe` (~25–35 MB), simple Python code | Fewer rich table/card widgets, requires extra work for polished high-DPI layouts | Viable lightweight fallback |
| **.NET 10 WPF / WinUI 3 (C#)** | Native Windows 11 controls, fast startup | Requires rewriting the entire tested Python REST/GraphQL engine in C# | Higher effort, low reuse |
| **Tauri v2 (React + Rust)** | Smallest binary (~10 MB), modern web UI | Requires installing Rust toolchain + MSVC C++ Build Tools; separate IPC bridge to Python | Extra build complexity |

**Selected Architecture:** **Python 3.11 + `PySide6` + Gitless GitHub REST/GraphQL Engine**, isolated in a project `.venv` managed via `uv`, and packaged with **`PyInstaller`** into a portable `GitHubAchievementStudio.exe` (plus optional Inno Setup installer later).

---

## 2. Requirements & Acceptance Criteria

### Functional Requirements
1. **Zero-CLI GitHub Sign-In:**
   - **Primary:** GitHub **OAuth Device Flow** (one-click "Sign in with GitHub" opens browser `github.com/login/device`, displays 8-char code + copy button, polls automatically).
   - **Fallback:** Scoped Personal Access Token (PAT) entry with automatic scope & rate-limit inspection.
   - **Optional 2nd Account Slot:** Same OAuth Device Flow or PAT slot for a second/partner GitHub account (unlocks `Pair Extraordinaire`, `Galaxy Brain`, strict `YOLO`, and cross-owner `Pull Shark`).
2. **Live Profile & Capability Dashboard:**
   - Displays avatar, handle, verified email status, core API quota remaining, and live scraped badges + tier multipliers (`x2`, `x3`, `x4`).
   - Categorizes every badge honestly into:
     - **Ready (Single Account):** `Quickdraw`, `YOLO`, `Pull Shark`
     - **Ready (Requires 2nd Account / Partner):** `Pair Extraordinaire`, `Galaxy Brain`, Cross-owner `Pull Shark`
     - **Manual / Legitimate Actions Only:** `Starstruck`, `Public Sponsor`, `Developer Program Member`, `GitHub Pro`
     - **Unavailable (Retired / Disabled / Staff):** `Arctic Code Vault`, `Mars 2020`, `Heart On Your Sleeve`, `Open Sourcerer`, `Finishing Touch`, `Proxima *`
3. **Interactive Run Planner & Dry-Run Preview:**
   - User selects target badges and tier (`Default`, `Bronze`, `Silver`, `Gold`), sandbox repo name, visibility (`public` default with clear warning on `private`), and pacing delay (`2.5s–5.0s`).
   - Before any remote mutation, displays an exact **Plan Preview Modal** (e.g., *"Will create 1 public repo, 1 Quickdraw issue, and 16 merged PRs — estimated time ~95s"*).
4. **Pause / Resume / Cancel Execution Engine:**
   - Runs asynchronously off the UI thread with live step-by-step progress bar, per-PR timer, ETA, and real-time log drawer.
   - Persists checkpoints in `%LOCALAPPDATA%\GitHubAchievementStudio\state.json`; re-running resumes idempotently using live GraphQL merged PR counts.
5. **Post-Run Verification & Sandbox Archiver:**
   - Refreshes `Repo Merged PRs`, `Global Merged PRs` (`search/issues`), `Quickdraw Issues`, `Accepted Answers`, and `Visible Profile Badges`.
   - Includes a **1-click Archive Sandbox Repo** button (`PATCH /repos/{owner}/{repo}` `{"archived": true}`) with a warning not to delete the repo if preserving badge links.

### Non-Functional & Security Acceptance Criteria
- **Zero local dependencies:** Works on a clean Windows 10/11 PC with no `git`, `gh`, or Python installed.
- **No plaintext secrets on disk:** Tokens encrypted via Windows **DPAPI** (`CryptProtectData` / `CryptUnprotectData`) per Windows user profile and masked from all UI logs/diagnostics.
- **Rate-limit & anti-abuse protection:** Enforces minimum pacing (`>= 2.0s` default `2.5s`), caps per-burst batch size (default `50` PRs per batch with resume prompt for `Silver=128` / `Gold=1,024`), honors `Retry-After` / HTTP `403`/`429` exponential backoff, and restricts operations strictly to user-owned or consenting partner sandboxes.

---

## 3. Target Architecture & Directory Layout

```text
GitHubAchievementStudio/
├── pyproject.toml                   # Project metadata, PySide6 + dev dependencies (managed via uv)
├── src/
│   └── gh_achievement_studio/
│       ├── __init__.py
│       ├── app.py                   # GUI entrypoint, high-DPI setup, exception hook
│       ├── core/
│       │   ├── models.py            # Dataclasses: AccountSession, RunPlan, BadgeStatus, ProgressEvent
│       │   ├── security.py          # Windows DPAPI token encrypt/decrypt + secret redaction
│       │   ├── auth.py              # GitHub OAuth Device Flow + PAT validation + /user/emails lookup
│       │   ├── github_client.py     # Pure HTTPS REST + GraphQL client with Retry-After & backoff
│       │   ├── git_data_engine.py   # Gitless Blobs -> Trees -> Commits -> Refs -> PR -> Merge engine
│       │   ├── runners.py           # Quickdraw, YOLO, Pull Shark (solo + cross-owner), Pair, Galaxy Brain
│       │   ├── verifier.py          # Repo stats + global search + HTML badge card/tier parser
│       │   └── state.py             # %LOCALAPPDATA% checkpoint & settings persistence
│       ├── ui/
│       │   ├── main_window.py       # Sidebar navigation, status bar, theme manager (Light/Dark)
│       │   ├── workers.py           # QThread/QRunnable wrappers emitting progress/log signals
│       │   ├── widgets/
│       │   │   ├── badge_card.py    # Achievement card widget (status pill, tier badge, tooltip)
│       │   │   └── log_drawer.py    # Filterable, copyable live execution log viewer
│       │   └── views/
│       │       ├── login_view.py    # Primary & secondary account Device Flow / PAT panels
│       │       ├── dashboard_view.py# Profile overview + live achievement status grid
│       │       ├── runner_view.py   # Single & multi-account configuration, Dry-Run modal, live queue
│       │       └── sandbox_view.py  # Repo manager, batch history, 1-click Archive, diagnostics export
│       └── cli/
│           └── main.py              # Thin headless CLI wrapper preserving execute_achievements.py flags
├── tests/
│   ├── test_auth_and_dpapi.py
│   ├── test_git_data_engine.py
│   ├── test_runners_and_delta.py
│   ├── test_verifier.py
│   └── test_ui_controllers.py
├── packaging/
│   ├── app.spec                     # PyInstaller single-file / one-dir spec
│   ├── version_info.txt             # Windows PE file metadata
│   ├── icon.ico                     # Application icon
│   └── installer.iss                # Optional Inno Setup script
└── execute_achievements.py          # Kept as lightweight backward-compatible shim/CLI
```

---

## 4. Data Flow & Gitless GitHub API Pipeline

Replacing local `git` + `gh` CLI subprocesses with direct HTTPS calls eliminates OS/environment breakage:

### A. Authentication Flow (OAuth Device Flow)
1. App sends `POST https://github.com/login/device/code` (`client_id`, `scope="repo read:user user:email write:discussion"`).
2. UI shows `user_code` (e.g., `ABCD-1234`), copies it to clipboard on click, and opens `verification_uri` in the user's default browser.
3. Background worker polls `POST https://github.com/login/oauth/access_token` at `interval` seconds (`slow_down` handled automatically).
4. On success, token is encrypted via Windows DPAPI and saved under `%LOCALAPPDATA%\GitHubAchievementStudio\credentials.json`.
5. App resolves `GET /user` (`login`, `id`, `name`, `avatar_url`) and `GET /user/emails` (picking primary verified email or `{id}+{login}@users.noreply.github.com`).

### B. Gitless Pull Request Cycle (Git Data API)
For each Pull Shark / YOLO / Pair Extraordinaire PR:
1. `GET /repos/{repo_owner}/{repo}/git/ref/heads/{default_branch}` -> `base_commit_sha`
2. `GET /repos/{repo_owner}/{repo}/git/commits/{base_commit_sha}` -> `base_tree_sha`
3. `POST /repos/{repo_owner}/{repo}/git/blobs` -> upload updated `ACHIEVEMENTS_LOG.md` content -> `blob_sha`
4. `POST /repos/{repo_owner}/{repo}/git/trees` (`base_tree`: `base_tree_sha`, entry path `ACHIEVEMENTS_LOG.md`, mode `100644`) -> `new_tree_sha`
5. `POST /repos/{repo_owner}/{repo}/git/commits` (`message` including optional `Co-authored-by:` trailer, `tree`: `new_tree_sha`, `parents`: `[base_commit_sha]`, `author`/`committer` verified email) -> `new_commit_sha`
6. `POST /repos/{repo_owner}/{repo}/git/refs` (`ref`: `refs/heads/achievement/pr-XXXX`, `sha`: `new_commit_sha`)
7. `POST /repos/{repo_owner}/{repo}/pulls` (`head`, `base`, `title`, `body`) -> `pr_number` *(plus optional `POST .../requested_reviewers` for strict YOLO)*
8. `PUT /repos/{repo_owner}/{repo}/pulls/{pr_number}/merge` (`merge_method: "merge"`) *(uses `secondary_token` in Cross-Owner mode so merger != author!)*
9. `DELETE /repos/{repo_owner}/{repo}/git/refs/heads/achievement/pr-XXXX` -> clean branch cleanup

### C. Cross-Owner Pull Shark Mode (Anti-Farming Fix Built Into App)
When a secondary/partner account is connected:
1. **Account B** creates `AccountB/achievement-collab-sandbox` (`public`, `auto_init: true`).
2. **Account B** invites **Account A** as collaborator (`PUT /repos/{B}/{repo}/collaborators/{A}`).
3. **Account A** auto-accepts the repository invitation (`GET /user/repository_invitations` -> `PATCH /user/repository_invitations/{id}`).
4. **Account A** creates branches & opens PRs; **Account B** merges them (`PUT .../merge`).
5. Same dual-account link seamlessly powers **Pair Extraordinaire** (`Co-authored-by:`) and **Galaxy Brain** (`createDiscussion` -> `addDiscussionComment` -> `markDiscussionCommentAsAnswer`).

---

## 5. Phased Implementation Plan

### Milestone 1: Core Engine Refactor (Gitless + Async-Friendly)
- Create `pyproject.toml` and initialize isolated `.venv` using `uv` (without modifying global Python packages).
- Port existing logic from [execute_achievements.py](file:///d:/PROJECTS/Self/Github%20Achievement%20Automation/execute_achievements.py) into `src/gh_achievement_studio/core/` (`models.py`, `github_client.py`, `git_data_engine.py`, `runners.py`, `verifier.py`, `state.py`).
- Add callback/event hooks (`ProgressEvent`) + `threading.Event` cancellation checks between steps so the GUI can pause/cancel safely mid-batch.
- Maintain a thin CLI entrypoint so headless automation & existing flags continue working.

### Milestone 2: Authentication, DPAPI Security & Cross-Owner Support
- Implement `auth.py` (GitHub OAuth Device Flow polling + PAT validator + `/user/emails` resolver + collaborator invitation acceptor).
- Implement `security.py` using Windows `ctypes.windll.crypt32.CryptProtectData` / `CryptUnprotectData` for zero-dependency Windows DPAPI encryption.
- Add Cross-Owner `Pull Shark` runner mode in `runners.py`.

### Milestone 3: Windows Desktop UI (`PySide6`)
- Build `MainWindow` with clean 4-tab sidebar (`Dashboard`, `Automation Runner`, `Multi-Account / Collab`, `Sandbox & Settings`) + Light/Dark theme matching Windows 11.
- Implement `LoginView` (Device Flow modal + PAT fallback + 2nd Account slot).
- Implement `DashboardView` with live badge cards (`Quickdraw`, `YOLO`, `Pull Shark`, `Pair Extraordinaire`, `Galaxy Brain`, `Starstruck`, `Public Sponsor`, `Developer Program Member`, plus collapsible `Unavailable / Retired` section).
- Implement `RunnerView` with Tier selectors, Dry-Run Preview confirmation dialog, live progress bar, pause/cancel button, and collapsible log drawer.
- Implement `SandboxView` with repo link launcher, batch continuation status, 1-click Archive Sandbox, and redacted diagnostic log export.

### Milestone 4: Testing & Quality Assurance
- **Unit tests (`unittest` / `pytest`):** Mocked Git Data API pipeline, Device Flow state transitions, DPAPI roundtrip on Windows, exponential backoff & `Retry-After` parsing, idempotent delta calculation, co-author email validation, and HTML tier scraper.
- **UI/Controller tests:** Verify button state guards (e.g., `Galaxy Brain` disabled without distinct 2nd account, `Start` requires Plan Preview confirmation, cancellation stops worker cleanly without leaving corrupt state).
- **Live smoke test:** Run the GUI against a real test sandbox (`--dry-run` and live verification check on `@AgrShubham`).

### Milestone 5: Windows Packaging & Distribution
- Generate app icon (`icon.ico`) and `version_info.txt`.
- Configure `packaging/app.spec` and build `dist/GitHubAchievementStudio.exe` using `PyInstaller 6.22.2`.
- Verify the `.exe` launches cleanly on a clean PATH (without Python/`git`/`gh` accessible), confirm Windows DPAPI credential persistence across restarts, and generate `SHA256SUMS.txt`.
- Document Microsoft Defender SmartScreen behavior for unsigned binaries (and code-signing instructions if distributing publicly).

---

## 6. Key Risks, Prerequisites & Mitigations

| Risk / Dependency | Impact | Mitigation |
| --- | --- | --- |
| **OAuth App Client ID** | Required for 1-click OAuth Device Flow login | Register one free GitHub OAuth App (`github.com/settings/developers`) with **Enable Device Flow** checked; no Client Secret needed in desktop binary. PAT login also works standalone. |
| **Unsigned `.exe` SmartScreen Prompt** | Windows 11 warns on unsigned executables downloaded from the web | Publish SHA-256 checksums, clean PE metadata, and document Authenticode signing (or Microsoft Store / Certum/Azure Trusted Signing) before public release. |
| **GitHub Secondary Rate Limits** | Rapid bursts trigger HTTP `403`/`429` or temporary blocks | Default `2.5s` delay, max `50` PRs per burst (`batch_limit`), automatic `Retry-After` backoff, and progress checkpoints for multi-day Gold (`1,024`) runs. |
| **Anti-Farming Filter on Solo Repos** | Self-merged PRs may stall in Pull Shark queue | Highlight **Cross-Owner / Buddy Mode** inside the UI and clearly warn users before running large batches solely on a solo repo. |
| **Account/ToS Misuse** | Spamming external repos or fake-star rings causes bans | Hard-lock automation to user-owned or explicitly invited sandbox repos; refuse arbitrary external repos and omit fake-star automation entirely. |
