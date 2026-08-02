[CmdletBinding()]
param(
    [ValidateSet("codex", "claude", "both")]
    [string]$Agent = "both",

    [switch]$Force,

    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$skillNames = @("ecom-listing", "ecom-image", "ecom-publish")
$repositoryRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$sourceRoot = Join-Path $repositoryRoot "skills"

# Install to the current user's standard skill folders so every project can use
# the same three commands. No administrator permission is required.
$agentRoots = @{}
if ($Agent -in @("codex", "both")) {
    $codexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE ".codex" }
    $agentRoots["Codex"] = Join-Path $codexHome "skills"
}
if ($Agent -in @("claude", "both")) {
    $agentRoots["Claude Code"] = Join-Path $env:USERPROFILE ".claude\skills"
}

foreach ($skillName in $skillNames) {
    $sourcePath = Join-Path $sourceRoot $skillName
    if (-not (Test-Path -LiteralPath (Join-Path $sourcePath "SKILL.md") -PathType Leaf)) {
        throw "Skill source is incomplete: $sourcePath"
    }
}

# Preflight all destinations before copying so a conflict cannot leave a partial
# multi-agent installation.
$conflicts = foreach ($entry in $agentRoots.GetEnumerator()) {
    foreach ($skillName in $skillNames) {
        $targetPath = Join-Path $entry.Value $skillName
        if (Test-Path -LiteralPath $targetPath) {
            [PSCustomObject]@{ Agent = $entry.Key; Path = $targetPath }
        }
    }
}
if ($conflicts -and -not $Force) {
    $details = ($conflicts | ForEach-Object { "[$($_.Agent)] $($_.Path)" }) -join [Environment]::NewLine
    throw "The following skills already exist. Re-run with -Force to update them:`n$details"
}

foreach ($entry in $agentRoots.GetEnumerator()) {
    $targetRoot = $entry.Value
    Write-Host "[$($entry.Key)] $targetRoot"

    foreach ($skillName in $skillNames) {
        $sourcePath = Join-Path $sourceRoot $skillName
        $targetPath = Join-Path $targetRoot $skillName
        if ($DryRun) {
            Write-Host "  Would install $skillName -> $targetPath"
            continue
        }

        [System.IO.Directory]::CreateDirectory($targetPath) | Out-Null
        # Copy children one by one to merge a forced update without deleting
        # user-added files that may already exist in the target skill folder.
        Get-ChildItem -LiteralPath $sourcePath -Force | ForEach-Object {
            Copy-Item -LiteralPath $_.FullName -Destination $targetPath -Recurse -Force
        }
        Write-Host "  Installed $skillName"
    }
}

if (-not $DryRun) {
    Write-Host ""
    Write-Host "Installation complete."
    if ($Agent -in @("codex", "both")) {
        Write-Host 'Codex commands: $ecom-listing -> $ecom-image -> $ecom-publish'
    }
    if ($Agent -in @("claude", "both")) {
        Write-Host "Claude Code commands: /ecom-listing -> /ecom-image -> /ecom-publish"
    }
    Write-Host "Start a new task or restart the current agent if the commands do not appear immediately."
}
