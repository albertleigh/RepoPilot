# Build Script - PowerShell
# Quick build script for Windows users

Write-Host "═══════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  Building RepoPilot" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

# Activate virtual environment if it exists
if (Test-Path ".venv\Scripts\Activate.ps1") {
    Write-Host "📦 Activating virtual environment..." -ForegroundColor Yellow
    & .\.venv\Scripts\Activate.ps1
}

# Run the build script
Write-Host "Starting build process..." -ForegroundColor Green
python scripts/build.py

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "✅ Build completed successfully!" -ForegroundColor Green
    Write-Host "📂 Check the 'release' folder for executables" -ForegroundColor Cyan
} else {
    Write-Host ""
    Write-Host "❌ Build failed!" -ForegroundColor Red
    exit 1
}
