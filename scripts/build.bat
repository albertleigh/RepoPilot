@echo off
REM Build Script - Batch file for Windows

echo ===================================================
echo   Building Qt Python Application
echo ===================================================
echo.

REM Activate virtual environment if it exists
if exist .venv\Scripts\activate.bat (
    echo Activating virtual environment...
    call .venv\Scripts\activate.bat
)

REM Run the build script
echo Starting build process...
python build.py

if %ERRORLEVEL% EQU 0 (
    echo.
    echo Build completed successfully!
    echo Check the 'release' folder for executables
) else (
    echo.
    echo Build failed!
    exit /b 1
)
