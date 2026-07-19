#!/bin/bash
# Start Central Parking MVP Backend with PostgreSQL

set -e

REPO_DIR="/opt/services/centralparking-mvp"
cd "$REPO_DIR"

# Load environment
export DATABASE_URL="postgresql://parking:centralparking@localhost:5432/centralparking"
export JWT_SECRET="${JWT_SECRET:-your-secret-key-change-this}"
export API_KEY="${API_KEY:-your-api-key-change-this}"
export BACKEND_URL="https://2.24.69.49.nip.io"

# Check PostgreSQL is running
if ! systemctl is-active --quiet postgresql; then
    echo "❌ PostgreSQL is not running. Starting..."
    sudo systemctl start postgresql
    sleep 2
fi

# Kill any existing uvicorn process
if pgrep -f "uvicorn api.detect:app" > /dev/null 2>&1; then
    echo "Stopping existing backend process..."
    pkill -f "uvicorn api.detect:app" || true
    sleep 2
fi

# Start backend
echo "Starting Central Parking MVP Backend..."
.venv/bin/uvicorn api.detect:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!

sleep 3

# Verify it's running
if curl -s http://localhost:8000/api/history > /dev/null 2>&1; then
    echo "✅ Backend is running (PID: $BACKEND_PID)"
    echo "API available at: http://localhost:8000"
else
    echo "❌ Backend failed to start"
    exit 1
fi
