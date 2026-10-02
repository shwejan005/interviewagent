#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
# dev.sh — One-command development launcher for Evalia
# Usage:  ./dev.sh
# ─────────────────────────────────────────────────────────────────────
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"

# Colors
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

log()  { echo -e "${GREEN}[evalia]${NC} $*"; }
warn() { echo -e "${YELLOW}[evalia]${NC} $*"; }
err()  { echo -e "${RED}[evalia]${NC} $*" >&2; }

# ── Cleanup on exit ─────────────────────────────────────────────────
cleanup() {
    log "Shutting down..."
    # Kill all background jobs in this process group
    kill 0 2>/dev/null || true
    wait 2>/dev/null || true
    log "Done."
}
trap cleanup EXIT INT TERM

# ── Pre-flight checks ───────────────────────────────────────────────
command -v python3 >/dev/null 2>&1 || { err "python3 is required but not found."; exit 1; }
command -v node    >/dev/null 2>&1 || { err "node is required but not found.";    exit 1; }
command -v npm     >/dev/null 2>&1 || { err "npm is required but not found.";     exit 1; }

# ── Check for .env ──────────────────────────────────────────────────
if [ ! -f "$BACKEND_DIR/.env" ] && [ ! -f "$ROOT_DIR/.env" ]; then
    warn "No .env file found. Create backend/.env with your GEMINI_API_KEY."
    warn "Example:  echo 'GEMINI_API_KEY=your-key-here' > backend/.env"
fi

# ── Backend setup ───────────────────────────────────────────────────
log "Setting up Python backend..."

if [ ! -d "$BACKEND_DIR/venv" ]; then
    log "Creating virtual environment..."
    python3 -m venv "$BACKEND_DIR/venv"
fi

# Activate venv
source "$BACKEND_DIR/venv/bin/activate"

log "Installing Python dependencies..."
pip install -q -r "$BACKEND_DIR/requirements.txt"

# ── Frontend setup ──────────────────────────────────────────────────
log "Setting up Next.js frontend..."

if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
    log "Installing Node dependencies..."
    (cd "$FRONTEND_DIR" && npm install)
else
    log "Node dependencies already installed."
fi

# ── Launch both servers ─────────────────────────────────────────────
echo ""
echo -e "${CYAN}══════════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}  Evalia — Multi-Agent Interview Evaluation System${NC}"
echo -e "${CYAN}══════════════════════════════════════════════════════════════${NC}"
echo -e "  ${GREEN}Backend${NC}  → http://localhost:8000"
echo -e "  ${GREEN}Worker${NC}   → durable screening/interview jobs"
echo -e "  ${GREEN}Frontend${NC} → http://localhost:3000"
echo -e "  ${GREEN}API Docs${NC} → http://localhost:8000/docs"
echo -e "${CYAN}══════════════════════════════════════════════════════════════${NC}"
echo -e "  Press ${YELLOW}Ctrl+C${NC} to stop both servers"
echo ""

# Start backend in background
(cd "$BACKEND_DIR" && uvicorn main:app --reload --port 8000) &
BACKEND_PID=$!

# The worker is a separate process: application screening and interview turns
# are durable jobs, never paid model calls inside the candidate HTTP request.
(cd "$BACKEND_DIR" && python -m app.worker.job_worker) &
WORKER_PID=$!

# Start frontend in background
(cd "$FRONTEND_DIR" && npm run dev) &
FRONTEND_PID=$!

# Wait for both — if either exits, the trap cleans up the other
wait $BACKEND_PID $WORKER_PID $FRONTEND_PID
