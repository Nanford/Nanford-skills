# 湖北/武汉企业补贴 · 桌面每日播报（对应 SKILL.md §4）
# 读取 $env:SUBSIDY_DATA_DIR\digest_latest.md，弹 Windows toast；
# 失败无害：任何异常都静默退出，不影响每日自动化。
$ErrorActionPreference = 'SilentlyContinue'

try {
    $dir = $env:SUBSIDY_DATA_DIR
    $digestPath = if ($dir) { Join-Path $dir 'digest_latest.md' } else { $null }
    if ($digestPath -and (Test-Path $digestPath)) {
        $lines = (Get-Content -Path $digestPath -Encoding UTF8 | Where-Object { $_.Trim() -ne '' }) | Select-Object -First 14
        $body = ($lines -join "`n").Trim()
    } else {
        $body = "湖北/武汉企业补贴：今日运行完成（未找到摘要）"
    }
    if (-not $body) { $body = "湖北/武汉企业补贴：今日运行完成" }
    $title = "湖北/武汉企业补贴 · 每日播报"

    # 优先用 Windows.UI.Notifications 原生 toast（Win10+）
    [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
    [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom, ContentType = WindowsRuntime] | Out-Null

    $template = '<toast><visual><binding template="ToastText02"><text id="1">{0}</text><text id="2">{1}</text></binding></visual></toast>'
    $xml = New-Object Windows.Data.Xml.Dom.XmlDocument
    $escaped = [System.Security.SecurityElement]::Escape($body)
    $xml.LoadXml(($template -f $title, $escaped))
    $notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("HubeiSubsidyTracker")
    $notifier.Show($xml)
}
catch {
    # 回退：弹一个 MessageBox（依赖 .NET WinForms，几乎总可用）
    try {
        Add-Type -AssemblyName System.Windows.Forms | Out-Null
        [System.Windows.Forms.MessageBox]::Show($body, $title) | Out-Null
    } catch {
        # 彻底失败也安静退出
    }
}
