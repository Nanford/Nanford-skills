[CmdletBinding()]
param(
    [ValidateSet("codex", "claude", "both")]
    [string]$Agent = "both",

    [switch]$Force,

    [switch]$DryRun,

    # Copy the skills only; skip npm ci, font download, wallpaper restore and sound library build.
    [switch]$SkipSetup
)

# Source of truth: VideoCut tools/install-video-skills.ps1, copied here by tools/export_skills.py.
# Messages stay in English: Windows PowerShell 5.1 reads BOM-less scripts in the ANSI code page.

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$skillNames = @(
    "video-workflow", "video-project", "script-check", "doubao-review", "jev-check", "minimax-tts",
    "voice-captions", "video-timeline", "visual-assets", "remotion-render", "sfx-kit", "av-export"
)
$repositoryRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$sourceRoot = Join-Path $repositoryRoot "skills"

$agentRoots = [ordered]@{}
if ($Agent -in @("codex", "both")) {
    $codexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE ".codex" }
    $agentRoots["Codex"] = Join-Path $codexHome "skills"
}
if ($Agent -in @("claude", "both")) {
    $agentRoots["Claude Code"] = Join-Path $env:USERPROFILE ".claude\skills"
}

foreach ($skillName in $skillNames) {
    if (-not (Test-Path -LiteralPath (Join-Path (Join-Path $sourceRoot $skillName) "SKILL.md") -PathType Leaf)) {
        throw "Skill source is incomplete: $(Join-Path $sourceRoot $skillName)"
    }
}

function Test-Tool([string]$name) {
    return [bool](Get-Command $name -ErrorAction SilentlyContinue)
}

function Invoke-Checked([string]$description, [scriptblock]$command) {
    & $command
    if ($LASTEXITCODE -ne 0) {
        throw "$description failed (exit code $LASTEXITCODE)"
    }
}

# Check every tool the setup needs before copying anything, so a missing tool cannot leave a half-installed set.
if (-not $SkipSetup) {
    $missing = @("python", "node", "npm", "ffmpeg", "ffprobe") | Where-Object { -not (Test-Tool $_) }
    if ($missing) {
        throw "Missing required tools: $($missing -join ', '). Install them, or re-run with -SkipSetup to copy the skills only."
    }
    Invoke-Checked "Python 3.10+ check" { python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" }
    # find_spec prints nothing, so no stderr redirection is needed (PowerShell 5.1 turns redirected stderr into errors)
    python -c "import importlib.util, sys; sys.exit(0 if all(importlib.util.find_spec(m) for m in ('requests', 'PIL')) else 1)"
    if ($LASTEXITCODE -ne 0) {
        throw "Python packages are missing. Run: python -m pip install requests pillow==12.1.0"
    }
    $nodeVersion = [version](node -p "process.versions.node")
    if ($nodeVersion -lt [version]"22.6.0") {
        throw "Node.js 22.6+ is required (found $nodeVersion)."
    }
}

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
        # Merge children one by one so a forced update keeps files the user added (such as a skill-level .env).
        Get-ChildItem -LiteralPath $sourcePath -Force | ForEach-Object {
            Copy-Item -LiteralPath $_.FullName -Destination $targetPath -Recurse -Force
        }
        Write-Host "  Installed $skillName"
    }

    if ($DryRun -or $SkipSetup) {
        continue
    }
    # Each installed copy needs its own node_modules, fonts, wallpapers and sound library.
    $renderRoot = Join-Path $targetRoot "remotion-render"
    Push-Location -LiteralPath $renderRoot
    try {
        Invoke-Checked "npm ci" { npm ci --no-audit --no-fund }
        Invoke-Checked "Font download" { npm run setup:fonts }
        Invoke-Checked "Wallpaper restore" { python scripts/wallpapers_build.py --restore }
    }
    finally {
        Pop-Location
    }
    Invoke-Checked "Sound library build" { python (Join-Path $targetRoot "sfx-kit\scripts\sfx_kit.py") build }
}

if (-not $DryRun) {
    $firstRoot = @($agentRoots.Values)[0]
    Write-Host ""
    Write-Host "Installation complete."
    Write-Host "Create a workspace (once per machine or account):"
    Write-Host "  python `"$(Join-Path $firstRoot 'video-workflow\scripts\init_workspace.py')`" <workspace-folder>"
    Write-Host "Then copy .env.example to .env in the workspace and fill in the API keys."
    if ($Agent -in @("codex", "both")) {
        Write-Host 'Codex: open the workspace folder and start with $video-workflow'
    }
    if ($Agent -in @("claude", "both")) {
        Write-Host "Claude Code: open the workspace folder and start with /video-workflow"
    }
    Write-Host "Start a new task or restart the agent if the skills do not appear immediately."
}
