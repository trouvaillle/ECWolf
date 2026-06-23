#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── 1. Check dependencies ──────────────────────────────────────────────
command -v uv  >/dev/null 2>&1 || { echo "Missing: uv (pip install uv)";  exit 1; }
command -v npm >/dev/null 2>&1 || { echo "Missing: npm (install node.js)"; exit 1; }

# ── 2. Install Python deps ─────────────────────────────────────────────
echo "[*] Installing Python dependencies..."
uv sync

# ── 3. Install frontend deps & build ───────────────────────────────────
if [ ! -d frontend/node_modules ]; then
    echo "[*] Installing frontend dependencies..."
    cd frontend && npm install && cd "$SCRIPT_DIR"
fi

if [ ! -d frontend/dist ]; then
    echo "[*] Building frontend..."
    cd frontend && npx vite build && cd "$SCRIPT_DIR"
fi

# ── 4. Run the backend (serves frontend from dist/) ────────────────────
echo "[*] Starting ECWolf Save Editor..."
echo "    → Open http://127.0.0.1:8765 in your browser"
echo "    → Press Ctrl+C to stop"
echo ""
uv run python main.py
