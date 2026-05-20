#!/bin/bash
# ══════════════════════════════════════
# Pulse-Chennai — One-Command Demo Start
# ══════════════════════════════════════
set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
echo "🚌 Starting Pulse-Chennai Demo..."
echo "   Project: $PROJECT_DIR"
echo ""

# Activate virtual environment
if [ -d "$PROJECT_DIR/venv" ]; then
  source "$PROJECT_DIR/venv/bin/activate"
else
  echo "📦 Creating virtual environment..."
  python3 -m venv venv
  source "$PROJECT_DIR/venv/bin/activate"
fi

# Install Python deps
echo "📦 Installing Python dependencies..."
python3 -m pip install -r "$PROJECT_DIR/requirements.txt" -q
if python3 -c "import playwright" &>/dev/null; then
  echo "🎭 Installing Playwright Chromium browser..."
  python3 -m playwright install chromium || echo "⚠️ Playwright browser install skipped"
fi

# Start backend
echo "🖥  Starting backend server..."
cd "$PROJECT_DIR"
python3 -m uvicorn api.dashboard_server:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!
sleep 2

# Seed stops
echo "🌱 Seeding stop data..."
python3 "$PROJECT_DIR/seed_stops.py"

# Start simulator
echo "🚌 Starting bus simulator..."
python3 -m simulator.demo_simulation &
SIM_PID=$!

# Start frontend
echo "🎨 Starting frontend..."
cd "$PROJECT_DIR/frontend"
npm install -q
npm run dev &
FRONTEND_PID=$!

echo ""
echo "════════════════════════════════════"
echo "✅ Pulse-Chennai is running!"
echo "════════════════════════════════════"
echo ""
echo "  🖥  Backend:   http://localhost:8000"
echo "  🎨 Frontend:  http://localhost:5173"
echo "  🚌 Simulator: Running (3 buses)"
echo ""
echo "Press Ctrl+C to stop all services"
echo ""

# Trap Ctrl+C to kill all background processes
trap "echo ''; echo '🛑 Stopping all services...'; kill $BACKEND_PID $SIM_PID $FRONTEND_PID 2>/dev/null; exit 0" INT TERM

wait
