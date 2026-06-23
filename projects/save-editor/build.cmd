@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0"

set "DIST_DIR=%~dp0dist"
if not exist "%DIST_DIR%" mkdir "%DIST_DIR%"

:: Build frontend
echo [*] Building frontend...
cd frontend
call npm install
if errorlevel 1 exit /b
call npx vite build
if errorlevel 1 exit /b
cd "%~dp0"

:: Bundle with PyInstaller
echo [*] Building standalone executable with PyInstaller...
call uv run pip install pyinstaller 2>nul

set "PYINST_OPTS=--name ecwolf-save-editor --add-data frontend/dist;frontend/dist --onefile --clean --noconfirm --windowed"

call uv run pyinstaller %PYINST_OPTS% main.py
if errorlevel 1 exit /b

:: Package
echo [*] Packaging...
copy /y "dist\ecwolf-save-editor.exe" "%DIST_DIR%\"
if errorlevel 1 (
    echo Build failed: output not found.
    exit /b 1
)

echo.
echo ✔ Build complete! Output in: %DIST_DIR%
echo   ^> %DIST_DIR%\ecwolf-save-editor.exe
