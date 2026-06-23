#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

DIST_DIR="$SCRIPT_DIR/dist"
mkdir -p "$DIST_DIR"

# ── Detect platform ──────────────────────────────────────────────────
UNAME_S="$(uname -s)"
case "$UNAME_S" in
    Linux)   PLATFORM="linux" ;;
    Darwin)  PLATFORM="macos" ;;
    MINGW*|MSYS*|CYGWIN*)  PLATFORM="windows" ;;
    *)       echo "Unknown platform: $UNAME_S"; exit 1 ;;
esac
echo "[*] Platform: $PLATFORM"

# ── Build frontend ───────────────────────────────────────────────────
echo "[*] Building frontend..."
cd frontend
npm install
npx vite build
cd "$SCRIPT_DIR"

# ── Bundle with PyInstaller ──────────────────────────────────────────
echo "[*] Building standalone executable with PyInstaller..."
uv run pip install pyinstaller 2>/dev/null || true

PYINST_OPTS=(
    --name "ecwolf-save-editor"
    --add-data "frontend/dist:frontend/dist"
    --onefile
    --clean
    --noconfirm
)

case "$PLATFORM" in
    windows)
        PYINST_OPTS+=(--windowed --icon NUL)
        ;;
    macos)
        PYINST_OPTS+=(--windowed)
        ;;
    linux)
        PYINST_OPTS+=(--windowed)
        ;;
esac

uv run pyinstaller "${PYINST_OPTS[@]}" main.py

# ── Package ──────────────────────────────────────────────────────────
echo "[*] Packaging..."
case "$PLATFORM" in
    windows)
        cp "dist/ecwolf-save-editor.exe" "$DIST_DIR/"
        ;;
    macos)
        cp -r "dist/ecwolf-save-editor.app" "$DIST_DIR/"
        ;;
    linux)
        cp "dist/ecwolf-save-editor" "$DIST_DIR/"
        ;;
esac

echo ""
echo "✔ Build complete! Output in: $DIST_DIR"
echo "  → $DIST_DIR/ecwolf-save-editor*"
