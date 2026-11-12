# GitHub Achievement Studio & Automation Toolkit

Standalone Windows desktop application (**GitHub Achievement Studio**) and gitless/CLI toolkit for unlocking, tracking, scaling, and verifying earnable GitHub Profile Achievements in a dedicated sandbox repository.

See [WINDOWS_APP_PLAN.md](WINDOWS_APP_PLAN.md) for the desktop application architecture, [PLAN.md](PLAN.md) for the legacy CLI execution plan, [GITHUB_ACHIEVEMENTS_GUIDE.md](GITHUB_ACHIEVEMENTS_GUIDE.md) for the complete badge encyclopedia, and [ACHIEVEMENT_HACKS_AND_SOFTWARE_BLUEPRINT.md](ACHIEVEMENT_HACKS_AND_SOFTWARE_BLUEPRINT.md) for technical automation patterns.

---

## Option A: GitHub Achievement Studio (Windows Desktop App — Zero Prerequisites)

The standalone `dist/GitHubAchievementStudio.exe` binary runs on Windows 10/11 **without** requiring local `git`, `gh` CLI, or Python to be installed.

### Key Capabilities
- **Gitless HTTPS Engine:** Creates branches, commits, pull requests, merges, and Q&A Discussions directly via GitHub REST (Git Data API) and GraphQL.
- **Zero-CLI Authentication:** Supports GitHub **OAuth Device Flow** (browser code), scoped **Personal Access Tokens (PAT)**, and optional `gh` CLI import.
- **Windows DPAPI Security:** Encrypts saved account tokens per Windows user profile inside `%LOCALAPPDATA%\GitHubAchievementStudio\credentials.json` and redacts tokens from logs and exported diagnostics.
- **Multi-Account Support:** Connect an optional second/partner account for **Pair Extraordinaire**, **Galaxy Brain**, strict **YOLO** reviewer requests, and **Cross-Owner Pull Shark** mode.
- **Dry-Run Plan Preview & Controls:** Previews exact deltas before mutating GitHub, enforces pacing & rate-limit backoff, supports Pause/Resume/Cancel, and includes a **1-click Archive Sandbox Repo** button.

### Running from Source (`uv`)
```powershell
uv sync --extra dev
.\.venv\Scripts\github-achievement-studio.exe
```
Or launch the headless gitless CLI mode directly:
```powershell
.\.venv\Scripts\python.exe -m gh_achievement_studio.app --cli --verify-only
.\.venv\Scripts\python.exe -m gh_achievement_studio.app --cli --dry-run --pull-shark-target bronze
```

### Building the Portable Windows Executable
```powershell
.\.venv\Scripts\pyinstaller.exe --clean --noconfirm packaging\app.spec
```
Output binary: `dist/GitHubAchievementStudio.exe`

Generate/verify SHA-256 checksums:
```powershell
Get-FileHash .\dist\GitHubAchievementStudio.exe -Algorithm SHA256
```
(Checksums are written to `dist/SHA256SUMS.txt` alongside release artifacts.)

### Windows SmartScreen & Code Signing Notice
Because `GitHubAchievementStudio.exe` is currently an **unsigned** portable binary, Windows 11 Microsoft Defender SmartScreen may show *"Windows protected your PC"* on downloaded copies until the binary builds reputation or is Authenticode-signed:
- Always verify the SHA-256 digest against `SHA256SUMS.txt` before running.
- For public distribution without SmartScreen warnings, sign `dist/GitHubAchievementStudio.exe` using an EV/OV Authenticode certificate (e.g., Azure Trusted Signing or Certum) via `signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 dist\GitHubAchievementStudio.exe`.

---

## Option B: Legacy Standalone Script (`execute_achievements.py`)

### Prerequisites
- Python 3.11+ (zero external pip dependencies)
- Git (`git`)
- GitHub CLI (`gh`) authenticated via `gh auth login`

### 1. Preview without making changes (`--dry-run`)
```powershell
python execute_achievements.py --dry-run --pull-shark-target bronze
```

### 2. Run single-account badges (Quickdraw + YOLO + Pull Shark Bronze = 16 PRs)
```powershell
.\execute.ps1 -Tier bronze
```
Or directly with Python:
```powershell
python execute_achievements.py --pull-shark-target bronze
```

### 3. Verify repo stats & profile badges
```powershell
python execute_achievements.py --verify-only
```

### Optional Multi-Account & Scaling Commands

#### Pair Extraordinaire (Co-authored PRs)
```powershell
python execute_achievements.py --pull-shark-target bronze --no-quickdraw --no-yolo --pair-count 10 --coauthor-username <second-github-username>
```

#### Galaxy Brain (Q&A Discussions)
Requires a Personal Access Token for a second GitHub account in `GH_HELPER_TOKEN`:
```powershell
$env:GH_HELPER_TOKEN = "<second-account-pat>"
python execute_achievements.py --pull-shark-target bronze --no-quickdraw --no-yolo --galaxy-count 2 --helper-token-env GH_HELPER_TOKEN
```

#### Scale Pull Shark to Silver (128) or Gold (1,024) Safely in Batches
```powershell
python execute_achievements.py --pull-shark-target gold --batch-limit 50 --delay-seconds 4.0
```
Re-running the command resumes cleanly from your current merged PR count.

---

## Tests
```powershell
.\.venv\Scripts\python.exe -m pytest -v
.\.venv\Scripts\python.exe -m unittest test_execute_achievements.py -v
```
