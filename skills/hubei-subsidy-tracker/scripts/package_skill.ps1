param(
    [string]$OutputPath = ""
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptDir
$skillName = "hubei-subsidy-tracker"

if (-not $OutputPath) {
    $stamp = Get-Date -Format "yyyyMMdd"
    $OutputPath = Join-Path $projectRoot "$skillName-$stamp.zip"
}

$outputFull = [System.IO.Path]::GetFullPath($OutputPath)
$tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("hubei-subsidy-package-" + [guid]::NewGuid().ToString("N"))
$tempBaseFull = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath()).TrimEnd('\') + '\'
$tempRootFull = [System.IO.Path]::GetFullPath($tempRoot)
if (-not $tempRootFull.StartsWith($tempBaseFull, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "临时打包目录不在系统临时目录内，已停止: $tempRootFull"
}
$stageSkill = Join-Path $tempRoot $skillName

$rootFiles = @(
    "SKILL.md",
    "requirements.txt",
    "config.example.env"
)

$scriptFiles = @(
    "dingtalk_aitable_sync.py",
    "dingtalk_notify.py",
    "feishu_sync.py",
    "feishu_wiki.py",
    "fetch_subsidies.py",
    "fill_draft.py",
    "init_setup.py",
    "install.py",
    "setup_state.py",
    "onboarding.py",
    "run_daily.py",
    "notification_ledger.py",
    "match_engine.py",
    "notify_toast.ps1",
    "package_skill.ps1"
)

try {
    New-Item -ItemType Directory -Path $stageSkill | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $stageSkill "scripts") | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $stageSkill "references") | Out-Null

    foreach ($name in $rootFiles) {
        Copy-Item -LiteralPath (Join-Path $projectRoot $name) -Destination (Join-Path $stageSkill $name)
    }

    foreach ($name in $scriptFiles) {
        Copy-Item -LiteralPath (Join-Path $scriptDir $name) -Destination (Join-Path (Join-Path $stageSkill "scripts") $name)
    }

    Get-ChildItem -LiteralPath (Join-Path $projectRoot "references") -File | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $stageSkill "references")
    }

    $forbidden = Get-ChildItem -LiteralPath $stageSkill -Recurse -Force | Where-Object {
        $_.Name -in @("config.env", "data", "__pycache__", ".pytest_cache") -or
        $_.Extension -in @(".xlsx", ".xls", ".log", ".zip", ".pyc") -or
        $_.Name -eq "run_daily.bat"
    }
    if ($forbidden) {
        $names = ($forbidden | ForEach-Object FullName) -join "; "
        throw "打包目录出现禁止文件: $names"
    }

    $outputDir = Split-Path -Parent $outputFull
    if (-not (Test-Path -LiteralPath $outputDir)) {
        New-Item -ItemType Directory -Path $outputDir | Out-Null
    }
    Compress-Archive -LiteralPath $stageSkill -DestinationPath $outputFull -Force
    Write-Output $outputFull
}
finally {
    if (Test-Path -LiteralPath $tempRootFull) {
        Remove-Item -LiteralPath $tempRootFull -Recurse -Force
    }
}
