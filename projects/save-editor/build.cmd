@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0" || (
    echo ERROR: Could not change to script directory
    pause
    exit /b 1
)

echo [*] Checking dependencies...
where uv >nul 2>&1
if errorlevel 1 (
    echo ERROR: uv not found. Install with: pip install uv
    pause
    exit /b 1
)
echo     uv: OK

if not exist "frontend\node_modules" (
    echo.
    echo [*] Installing frontend dependencies...
    pushd frontend
    call npm install
    if errorlevel 1 (
        echo ERROR: npm install failed
        popd
        pause
        exit /b 1
    )
    popd
)

echo.
echo [*] Building frontend...
pushd frontend
call npx vite build
if errorlevel 1 (
    echo ERROR: vite build failed
    popd
    pause
    exit /b 1
)
popd
echo     Frontend build: OK

echo.
echo [*] Installing PyInstaller...
call uv pip install pyinstaller
if errorlevel 1 (
    echo ERROR: PyInstaller install failed
    pause
    exit /b 1
)

echo.
echo [*] Building standalone executable...
set "DIST_DIR=%~dp0dist"
if not exist "%DIST_DIR%" mkdir "%DIST_DIR%"

call uv run pyinstaller ^
    --name ecwolf-save-editor ^
    --add-data "frontend/dist;frontend/dist" ^
    --onefile --clean --noconfirm --windowed ^
    main.py
if errorlevel 1 (
    echo ERROR: PyInstaller build failed
    pause
    exit /b 1
)

if not exist "dist\ecwolf-save-editor.exe" (
    echo ERROR: Output not found
    pause
    exit /b 1
)

copy /y "dist\ecwolf-save-editor.exe" "%DIST_DIR%\" >nul
echo     Package: OK

echo.
echo ^> Build complete! Output:
echo   %DIST_DIR%\ecwolf-save-editor.exe
pause
