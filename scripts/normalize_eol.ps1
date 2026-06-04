$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath 'Q:\Repos2\RepoPilot'

$excludeDirs = @('.git','__pycache__','.venv','venv','node_modules','build','dist','.idea','.mypy_cache','.pytest_cache')
$binaryExt   = @('.png','.ico','.jpg','.jpeg','.gif','.webp','.pdf','.zip','.exe','.dll','.pyc','.pyd','.so','.bin','.7z','.gz','.tar','.whl')
$crlfKeepExt = @('.bat','.cmd','.ps1','.psm1')

$converted   = @()
$keptCRLF    = @()
$skippedBin  = 0

Get-ChildItem -Path . -Recurse -File -Force | ForEach-Object {
    $full = $_.FullName
    $rel  = $full.Substring((Get-Location).Path.Length + 1)
    $parts = $rel -split '[\\/]'
    foreach ($d in $excludeDirs) {
        if ($parts -contains $d) { return }
    }
    $ext = $_.Extension.ToLower()
    if ($binaryExt -contains $ext) { return }
    if ($_.Length -eq 0) { return }
    if ($_.Length -gt 5MB) { return }  # skip huge files

    $bytes = [System.IO.File]::ReadAllBytes($full)

    # Binary heuristic: NUL byte in first 8KB
    $scan = [Math]::Min($bytes.Length, 8192)
    $isBinary = $false
    for ($i = 0; $i -lt $scan; $i++) {
        if ($bytes[$i] -eq 0) { $isBinary = $true; break }
    }
    if ($isBinary) { $script:skippedBin++; return }

    $hasCRLF = $false
    for ($i = 0; $i -lt $bytes.Length - 1; $i++) {
        if ($bytes[$i] -eq 13 -and $bytes[$i+1] -eq 10) { $hasCRLF = $true; break }
    }
    if (-not $hasCRLF) { return }

    if ($crlfKeepExt -contains $ext) {
        $script:keptCRLF += $rel
        return
    }

    $ms = New-Object System.IO.MemoryStream
    for ($i = 0; $i -lt $bytes.Length; $i++) {
        if ($bytes[$i] -eq 13 -and ($i + 1) -lt $bytes.Length -and $bytes[$i+1] -eq 10) { continue }
        $ms.WriteByte($bytes[$i])
    }
    [System.IO.File]::WriteAllBytes($full, $ms.ToArray())
    $ms.Dispose()
    $script:converted += $rel
}

Write-Host "=== Converted CRLF -> LF ($($converted.Count)) ==="
$converted | ForEach-Object { Write-Host "  $_" }
Write-Host ""
Write-Host "=== Kept CRLF (Windows scripts) ($($keptCRLF.Count)) ==="
$keptCRLF | ForEach-Object { Write-Host "  $_" }
Write-Host ""
Write-Host "Skipped binary (NUL detected): $skippedBin"

