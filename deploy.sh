#!/usr/bin/env bash
set -e

echo "=== SmartSmeta deploy ==="

echo "1. Pulling latest code..."
git pull origin main

echo "2. Rebuilding docker image..."
docker compose build

echo "3. Restarting container..."
docker compose up -d

echo "4. Checking health..."
sleep 3
if curl -sf http://localhost:8000/health > /dev/null; then
  echo "OK: bot is running"
else
  echo "WARN: health check failed, checking logs..."
  docker compose logs --tail=20
fi

echo "=== Done ==="
