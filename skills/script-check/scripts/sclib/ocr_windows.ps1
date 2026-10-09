<#
INPUT: -ListFile 一个 UTF-8 文本文件，每行一个图片绝对路径；-Language OCR 语言标签（默认 zh-Hans-CN）
OUTPUT: 标准输出写一行 UTF-8 JSON：[{ "path": 路径, "lines": [逐行文字], "error": 失败原因或 null }]
POS: script-check 的截图文字识别后端，调用 Windows 自带的 Windows.Media.Ocr（不联网、不计费、无需安装依赖）。
     路径经文件传入而非命令行参数，避免中文路径在控制台编码中损坏（AGENTS.md 第 16 节）。
     本文件须保存为带 BOM 的 UTF-8：Windows PowerShell 5.1 会把无 BOM 的脚本按系统代码页（GBK）读取，中文字符串会解析失败。
#>
param(
    [Parameter(Mandatory = $true)][string]$ListFile,
    [string]$Language = "zh-Hans-CN"
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)

Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Globalization.Language, Windows.Globalization, ContentType = WindowsRuntime]

# PowerShell 5.1 不能直接 await WinRT 异步操作：借 WindowsRuntimeSystemExtensions.AsTask 转成 .NET Task 再同步等待
$asTaskGeneric = [System.WindowsRuntimeSystemExtensions].GetMethods() |
    Where-Object { $_.Name -eq "AsTask" -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' } |
    Select-Object -First 1

function Wait-WinRt($operation, [Type]$resultType) {
    $task = $asTaskGeneric.MakeGenericMethod($resultType).Invoke($null, @($operation))
    $task.Wait() | Out-Null
    return $task.Result
}

$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new($Language))
if ($null -eq $engine) {
    Write-Error "Windows OCR 未安装语言 $Language；在「设置 › 时间和语言 › 语言」添加该语言的光学字符识别功能"
    exit 2
}

$results = @()
foreach ($path in [System.IO.File]::ReadAllLines($ListFile, [System.Text.Encoding]::UTF8)) {
    if ([string]::IsNullOrWhiteSpace($path)) { continue }
    try {
        $file = Wait-WinRt ([Windows.Storage.StorageFile]::GetFileFromPathAsync($path)) ([Windows.Storage.StorageFile])
        $stream = Wait-WinRt ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
        $decoder = Wait-WinRt ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
        $bitmap = Wait-WinRt ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
        $ocr = Wait-WinRt ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
        $stream.Dispose()
        $results += [pscustomobject]@{ path = $path; lines = @($ocr.Lines | ForEach-Object { $_.Text }); error = $null }
    } catch {
        $results += [pscustomobject]@{ path = $path; lines = @(); error = $_.Exception.Message }
    }
}
# 单元素数组也要保持 JSON 数组形态
Write-Output (ConvertTo-Json -InputObject @($results) -Depth 4 -Compress)
