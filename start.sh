#!/bin/bash

set -e
cd "$(dirname "$0")"

echo "Starting OnHolland Accounting..."

# Start PostgreSQL/database if Docker Compose has a db service
if docker compose config --services 2>/dev/null | grep -qx db; then
    docker compose up -d db
fi

# Start backend
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

# Start frontend
cd ../frontend
npm run dev &
FRONTEND_PID=$!

cleanup() {
    echo "Stopping OnHolland Accounting..."
    kill "$FRONTEND_PID" "$BACKEND_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

wait
