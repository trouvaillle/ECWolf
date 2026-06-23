@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0"

:: 1. Check dependencies
where uv >nul 2>&1
if errorlevel 1 (
    echo Missing: uv (pip install uv)
    exit /b 1
)
where npm >nul 2>&1
if errorlevel 1 (
    echo Missing: npm (install node.js)
    exit /b 1
)

:: 2. Install Python deps
echo [*] Installing Python dependencies...
call uv sync
if errorlevel 1 exit /b

:: 3. Install frontend deps & build
if not exist "frontend\node_modules" (
    echo [*] Installing frontend dependencies...
    cd frontend
    call npm install
    cd "%~dp0"
)

if not exist "frontend\dist" (
    echo [*] Building frontend...
    cd frontend
    call npx vite build
    cd "%~dp0"
)

:: 4. Run the backend
echo [*] Starting ECWolf Save Editor...
echo     ^> Open http://127.0.0.1:8765 in your browser
echo     ^> Press Ctrl+C to stop
echo.
call uv run python main.py
