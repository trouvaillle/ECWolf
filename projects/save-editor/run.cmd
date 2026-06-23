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

where npm >nul 2>&1
if errorlevel 1 (
    echo ERROR: npm not found. Install Node.js from https://nodejs.org/
    pause
    exit /b 1
)
echo     npm: OK

echo.
echo [*] Installing Python dependencies...
call uv sync
if errorlevel 1 (
    echo ERROR: uv sync failed
    pause
    exit /b 1
)
echo     Python dependencies: OK

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
    echo     Frontend dependencies: OK
)

if not exist "frontend\dist" (
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
)

echo.
echo [*] Starting ECWolf Save Editor...
echo     ^> Open http://127.0.0.1:8765 in your browser
echo     ^> Press Ctrl+C to stop
echo.
call uv run python main.py
if errorlevel 1 (
    echo ERROR: Application exited with error
    pause
    exit /b 1
)
