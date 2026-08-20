[CmdletBinding()]
param(
    [Parameter()]
    [string]$TemplatesDir,

    [Parameter()]
    [string]$SourceDir
)

$ErrorActionPreference = "Stop"
$projectDir = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
if (-not $TemplatesDir) {
    $TemplatesDir = Join-Path $projectDir "assets\templates\Templates"
}
$TemplatesDir = (Resolve-Path $TemplatesDir).Path
if (-not $SourceDir) { $SourceDir = $TemplatesDir }
$SourceDir = (Resolve-Path $SourceDir).Path

$venvPython = Join-Path $projectDir "backend\.venv\Scripts\python.exe"
$python = if (Test-Path -LiteralPath $venvPython) { $venvPython } else { "python" }
$previousPythonIoEncoding = $env:PYTHONIOENCODING
$previousProjectDir = $env:VOVA_XLS_PROJECT_DIR
$env:PYTHONIOENCODING = "utf-8"
$env:VOVA_XLS_PROJECT_DIR = $projectDir
try {
    $pythonCode = "import json, os, sys; sys.path.insert(0, os.path.join(os.environ['VOVA_XLS_PROJECT_DIR'], 'backend')); from app.services.new_xls_templates import LEGACY_XLS_TEMPLATE_SPECS, legacy_xls_placeholder; print(json.dumps([{'file_name': s.file_name, 'fields': [{'sheet_name': f.sheet_name, 'row': f.source_cell[0] + 1, 'column': f.source_cell[1] + 1, 'placeholder': legacy_xls_placeholder(s, f)} for f in s.fields]} for s in LEGACY_XLS_TEMPLATE_SPECS], ensure_ascii=True))"
    $markerManifest = (& $python -c $pythonCode) | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0) { throw "Не удалось получить карту маркеров старых XLS-шаблонов." }
}
finally {
    $env:PYTHONIOENCODING = $previousPythonIoEncoding
    $env:VOVA_XLS_PROJECT_DIR = $previousProjectDir
}

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
        $sourcePath = Join-Path $SourceDir $item.FileName
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

            # Remove obsolete hidden markers inherited from older multi-sheet
            # books before injecting this template's authoritative registry.
            $markerStart = [string][char]0x2060
            foreach ($targetSheet in $targetWorkbook.Worksheets) {
                $usedRange = $targetSheet.UsedRange
                for ($row = 1; $row -le $usedRange.Rows.Count; $row += 1) {
                    for ($column = 1; $column -le $usedRange.Columns.Count; $column += 1) {
                        $cell = $usedRange.Cells.Item($row, $column)
                        $value = [string]$cell.Value2
                        if ($value.Contains($markerStart)) { $cell.Value2 = "" }
                    }
                }
            }
            if ([string]$item.FileName -eq "Выписка из Амб карты (профа).xls") {
                $targetWorkbook.Worksheets.Item("ПЗ2").Cells.Item(58, 55).MergeArea.ClearContents()
            }

            $markerItem = $markerManifest | Where-Object { [string]$_.file_name -eq [string]$item.FileName } | Select-Object -First 1
            if (-not $markerItem) { throw "Не найдена карта маркеров для $($item.FileName)" }
            foreach ($field in $markerItem.fields) {
                $targetSheet = $targetWorkbook.Worksheets.Item([string]$field.sheet_name)
                $targetSheet.Cells.Item([int]$field.row, [int]$field.column).Value2 = [string]$field.placeholder
            }

            $temporaryOutput = Join-Path $temporaryRoot ("output-" + $item.FileName)
            $targetWorkbook.SaveAs($temporaryOutput, 56)
            $targetWorkbook.Close($false)
            $targetWorkbook = $null
            $sourceWorkbook.Close($false)
            $sourceWorkbook = $null
            $outputPath = Join-Path $TemplatesDir $item.FileName
            Move-Item -LiteralPath $temporaryOutput -Destination $outputPath -Force
            Write-Host "Оставлены печатные листы: $outputPath"
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
