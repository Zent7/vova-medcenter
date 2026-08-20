[CmdletBinding()]
param(
    [Parameter()]
    [string]$SourceDir = (Join-Path $HOME "Downloads"),

    [Parameter()]
    [string]$OutputDir,

    [Parameter()]
    [string]$OnlyFileName
)

$ErrorActionPreference = "Stop"
$projectDir = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
if (-not $OutputDir) {
    $OutputDir = Join-Path $projectDir "assets\templates\Templates"
}
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
$OutputDir = (Resolve-Path $OutputDir).Path
$SourceDir = (Resolve-Path $SourceDir).Path

$venvPython = Join-Path $projectDir "backend\.venv\Scripts\python.exe"
$python = if (Test-Path -LiteralPath $venvPython) { $venvPython } else { "python" }
$previousPythonIoEncoding = $env:PYTHONIOENCODING
$previousProjectDir = $env:VOVA_XLS_PROJECT_DIR
$env:PYTHONIOENCODING = "utf-8"
$env:VOVA_XLS_PROJECT_DIR = $projectDir
try {
    $pythonCode = "import json, os, sys; sys.path.insert(0, os.path.join(os.environ['VOVA_XLS_PROJECT_DIR'], 'backend')); from app.services.new_xls_templates import NEW_XLS_TEMPLATE_SPECS, new_xls_placeholder; print(json.dumps([{'file_name': spec.file_name, 'source_file_name': spec.source_file_name or spec.file_name, 'sheet_name': spec.sheet_name, 'print_pages_wide': spec.print_pages_wide, 'print_pages_tall': spec.print_pages_tall, 'print_area': spec.print_area, 'print_zoom': spec.print_zoom, 'vertical_page_break_column': spec.vertical_page_break_column, 'cells': [{'row': row + 1, 'column': column + 1, 'placeholder': new_xls_placeholder(spec, (row, column))} for row, column in spec.dynamic_cells]} for spec in NEW_XLS_TEMPLATE_SPECS], ensure_ascii=True))"
    $manifestJson = & $python -c $pythonCode
    if ($LASTEXITCODE -ne 0) {
        throw "Не удалось получить карту новых XLS-шаблонов."
    }
}
finally {
    $env:PYTHONIOENCODING = $previousPythonIoEncoding
    $env:VOVA_XLS_PROJECT_DIR = $previousProjectDir
}
$manifest = $manifestJson | ConvertFrom-Json
if ($OnlyFileName) {
    $manifest = @($manifest | Where-Object { [string]$_.file_name -eq $OnlyFileName })
    if ($manifest.Count -eq 0) {
        throw "Не найдено описание XLS-шаблона '$OnlyFileName'."
    }
}

$temporaryRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("vova-new-xls-" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $temporaryRoot | Out-Null
$temporaryRoot = (Resolve-Path $temporaryRoot).Path

$excel = $null
try {
    $excel = New-Object -ComObject Excel.Application
    $excel.Visible = $false
    $excel.DisplayAlerts = $false
    $excel.EnableEvents = $false

    $itemIndex = 0
    foreach ($item in $manifest) {
        $itemIndex += 1
        $sourcePath = Join-Path $SourceDir $item.source_file_name
        if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) {
            throw "Не найден исходный шаблон: $sourcePath"
        }

        # A local unblocked copy avoids Protected View without altering the file
        # supplied by the customer.
        $sourceCopy = Join-Path $temporaryRoot ("source-$itemIndex.xls")
        Copy-Item -LiteralPath $sourcePath -Destination $sourceCopy
        Unblock-File -LiteralPath $sourceCopy -ErrorAction SilentlyContinue

        $sourceWorkbook = $null
        $targetWorkbook = $null
        try {
            $sourceWorkbook = $excel.Workbooks.Open($sourceCopy, 0, $true)
            $sourceSheet = $sourceWorkbook.Worksheets.Item([string]$item.sheet_name)
            $targetWorkbook = $excel.Workbooks.Add()
            $firstTargetSheet = $targetWorkbook.Worksheets.Item(1)

            [void]$targetWorkbook.Activate()
            [void]$firstTargetSheet.Activate()
            [void]$sourceSheet.GetType().InvokeMember(
                "Copy",
                [Reflection.BindingFlags]::InvokeMethod,
                $null,
                $sourceSheet,
                @($firstTargetSheet, [Type]::Missing)
            )
            if ($targetWorkbook.Worksheets.Count -lt 2) {
                throw "Excel не скопировал лист '$($item.sheet_name)' из '$($item.file_name)'."
            }

            while ($targetWorkbook.Worksheets.Count -gt 1) {
                $targetWorkbook.Worksheets.Item($targetWorkbook.Worksheets.Count).Delete()
            }
            $targetSheet = $targetWorkbook.Worksheets.Item(1)
            if ([string]$targetSheet.Name -ne [string]$item.sheet_name) {
                throw "В новой книге остался неверный лист '$($targetSheet.Name)'."
            }

            foreach ($cell in $item.cells) {
                $range = $targetSheet.Cells.Item([int]$cell.row, [int]$cell.column)
                $range.Value2 = [string]$cell.placeholder
            }
            if ($null -ne $item.vertical_page_break_column) {
                [void]$targetSheet.ResetAllPageBreaks()
            }
            if ($null -ne $item.print_zoom) {
                $targetSheet.PageSetup.PrintArea = [string]$item.print_area
                $targetSheet.PageSetup.Zoom = [int]$item.print_zoom
            }
            else {
                $targetSheet.PageSetup.Zoom = $false
                $targetSheet.PageSetup.FitToPagesWide = [int]$item.print_pages_wide
                $targetSheet.PageSetup.FitToPagesTall = [int]$item.print_pages_tall
            }
            if ($null -ne $item.vertical_page_break_column) {
                [void]$targetSheet.VPageBreaks.Add(
                    $targetSheet.Columns.Item([int]$item.vertical_page_break_column)
                )
            }

            $temporaryOutput = Join-Path $temporaryRoot ("output-$itemIndex.xls")
            $targetWorkbook.SaveAs($temporaryOutput, 56)
            $targetWorkbook.Close($false)
            $targetWorkbook = $null
            $sourceWorkbook.Close($false)
            $sourceWorkbook = $null

            $outputPath = Join-Path $OutputDir $item.file_name
            Move-Item -LiteralPath $temporaryOutput -Destination $outputPath -Force
            Write-Host "Подготовлен $outputPath"
        }
        finally {
            if ($targetWorkbook) {
                $targetWorkbook.Close($false)
            }
            if ($sourceWorkbook) {
                $sourceWorkbook.Close($false)
            }
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
