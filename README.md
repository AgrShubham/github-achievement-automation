# GitHub Achievement Automation

Automated, idempotent toolkit for unlocking and verifying earnable GitHub Profile Achievements in a dedicated public sandbox repository.

See [PLAN.md](PLAN.md) for the complete architecture, eligibility matrix, and safety design.

## Prerequisites

- Python 3.11+ (zero external pip dependencies)
- Git (`git`)
- GitHub CLI (`gh`) authenticated via `gh auth login`

## Quick Start

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

## Optional Multi-Account & Scaling Commands

### Pair Extraordinaire (Co-authored PRs)
```powershell
python execute_achievements.py --pull-shark-target bronze --no-quickdraw --no-yolo --pair-count 10 --coauthor-username <second-github-username>
```

### Galaxy Brain (Q&A Discussions)
Requires a Personal Access Token for a second GitHub account in `GH_HELPER_TOKEN`:
```powershell
$env:GH_HELPER_TOKEN = "<second-account-pat>"
python execute_achievements.py --pull-shark-target bronze --no-quickdraw --no-yolo --galaxy-count 2 --helper-token-env GH_HELPER_TOKEN
```

### Scale Pull Shark to Silver (128) or Gold (1,024) Safely in Batches
```powershell
python execute_achievements.py --pull-shark-target gold --batch-limit 50 --delay-seconds 4.0
```
Re-running the command resumes cleanly from your current merged PR count.

## Tests
```powershell
python -m unittest discover -v
```

