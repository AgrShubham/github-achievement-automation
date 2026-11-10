<#
.SYNOPSIS
    Runs the GitHub Profile Achievement Automation engine on Windows.

.EXAMPLE
    .\execute.ps1 -DryRun
    .\execute.ps1 -Tier bronze
    .\execute.ps1 -VerifyOnly
    .\execute.ps1 -Tier gold -BatchLimit 50 -DelaySeconds 4.0
#>
[CmdletBinding()]
param(
    [string]$Repo = "github-achievements-sandbox",
    [ValidateSet("public", "private")]
    [string]$Visibility = "public",
    [ValidateSet("none", "default", "bronze", "silver", "gold")]
    [string]$Tier = "bronze",
    [int]$PrCount = -1,
    [switch]$NoQuickdraw,
    [switch]$NoYolo,
    [string]$Reviewer = "",
    [int]$PairCount = 0,
    [string]$CoauthorUsername = "",
    [string]$CoauthorName = "",
    [string]$CoauthorEmail = "",
    [int]$GalaxyCount = 0,
    [string]$HelperTokenEnv = "GH_HELPER_TOKEN",
    [double]$DelaySeconds = 2.5,
    [int]$BatchLimit = 0,
    [switch]$DryRun,
    [switch]$VerifyOnly,
    [switch]$VerboseLogs
)

$ErrorActionPreference = "Stop"

$scriptPath = Join-Path $PSScriptRoot "execute_achievements.py"
if (-not (Test-Path $scriptPath)) {
    throw "Execution script not found at $scriptPath"
}

$argsList = @(
    $scriptPath,
    "--repo", $Repo,
    "--visibility", $Visibility,
    "--pull-shark-target", $Tier,
    "--delay-seconds", "$DelaySeconds",
    "--helper-token-env", $HelperTokenEnv
)

if ($PrCount -ge 0) { $argsList += @("--pr-count", "$PrCount") }
if ($NoQuickdraw) { $argsList += "--no-quickdraw" }
if ($NoYolo) { $argsList += "--no-yolo" }
if ($Reviewer) { $argsList += @("--reviewer", $Reviewer) }
if ($PairCount -gt 0) { $argsList += @("--pair-count", "$PairCount") }
if ($CoauthorUsername) { $argsList += @("--coauthor-username", $CoauthorUsername) }
if ($CoauthorName) { $argsList += @("--coauthor-name", $CoauthorName) }
if ($CoauthorEmail) { $argsList += @("--coauthor-email", $CoauthorEmail) }
if ($GalaxyCount -gt 0) { $argsList += @("--galaxy-count", "$GalaxyCount") }
if ($BatchLimit -gt 0) { $argsList += @("--batch-limit", "$BatchLimit") }
if ($DryRun) { $argsList += "--dry-run" }
if ($VerifyOnly) { $argsList += "--verify-only" }
if ($VerboseLogs) { $argsList += "--verbose" }

& python @argsList
exit $LASTEXITCODE

