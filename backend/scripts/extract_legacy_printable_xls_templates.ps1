[CmdletBinding()]
param(
    [Parameter()]
    [string]$TemplatesDir
)

$ErrorActionPreference = "Stop"
$projectDir = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
if (-not $TemplatesDir) {
    $TemplatesDir = Join-Path $projectDir "assets\templates\Templates"
}
$TemplatesDir = (Resolve-Path $TemplatesDir).Path

$manifest = @(
    @{ FileName = "ВУ.xls"; Sheets = @("Водительская Лицевая", "Водительская Оборотная") },
    @{ FileName = "АМБ_карты_профосмотр_шаблон.xls"; Sheets = @("Амб") },
    @{ FileName = "Выписка из Амб карты (профа).xls"; Sheets = @("ПЗ2") },
    @{ FileName = "Справка_342н_псих_освид.xls"; Sheets = @("Проф2") }
)

$temporaryRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("vova-legacy-xls-" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $temporaryRoot | Out-Null
$temporaryRoot = (Resolve-Path $temporaryRoot).Path
$excel = $null
try {
    $excel = New-Object -ComObject Excel.Application
    $excel.Visible = $false
    $excel.DisplayAlerts = $false
    $excel.EnableEvents = $false

    foreach ($item in $manifest) {
        $sourcePath = Join-Path $TemplatesDir $item.FileName
        if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) {
            throw "Не найден исходный шаблон: $sourcePath"
        }
        $sourceCopy = Join-Path $temporaryRoot $item.FileName
        Copy-Item -LiteralPath $sourcePath -Destination $sourceCopy
        Unblock-File -LiteralPath $sourceCopy -ErrorAction SilentlyContinue

        $sourceWorkbook = $null
        $targetWorkbook = $null
        try {
            $sourceWorkbook = $excel.Workbooks.Open($sourceCopy, 0, $true)
            $targetWorkbook = $excel.Workbooks.Add()
            while ($targetWorkbook.Worksheets.Count -gt 1) {
                $targetWorkbook.Worksheets.Item($targetWorkbook.Worksheets.Count).Delete()
            }
            $placeholderSheet = $targetWorkbook.Worksheets.Item(1)

            foreach ($sheetName in $item.Sheets) {
                $sourceSheet = $sourceWorkbook.Worksheets.Item([string]$sheetName)
                [void]$sourceSheet.Copy([Type]::Missing, $targetWorkbook.Worksheets.Item($targetWorkbook.Worksheets.Count))
            }
            $placeholderSheet.Delete()

            $actualNames = @($targetWorkbook.Worksheets | ForEach-Object { [string]$_.Name })
            if ([string]::Join("|", $actualNames) -ne [string]::Join("|", $item.Sheets)) {
                throw "Неверный набор печатных листов в $($item.FileName): $([string]::Join(', ', $actualNames))"
            }

            $temporaryOutput = Join-Path $temporaryRoot ("output-" + $item.FileName)
            $targetWorkbook.SaveAs($temporaryOutput, 56)
            $targetWorkbook.Close($false)
            $targetWorkbook = $null
            $sourceWorkbook.Close($false)
            $sourceWorkbook = $null
            Move-Item -LiteralPath $temporaryOutput -Destination $sourcePath -Force
            Write-Host "Оставлены печатные листы: $sourcePath"
        }
        finally {
            if ($targetWorkbook) { $targetWorkbook.Close($false) }
            if ($sourceWorkbook) { $sourceWorkbook.Close($false) }
        }
    }
}
finally {
    if ($excel) {
        $excel.Quit()
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($excel)
    }
    if (Test-Path -LiteralPath $temporaryRoot) {
        $resolvedTemporaryRoot = (Resolve-Path $temporaryRoot).Path
        $resolvedSystemTemp = (Resolve-Path ([System.IO.Path]::GetTempPath())).Path
        if ($resolvedTemporaryRoot.StartsWith($resolvedSystemTemp, [StringComparison]::OrdinalIgnoreCase)) {
            Remove-Item -LiteralPath $resolvedTemporaryRoot -Recurse -Force
        }
    }
}
