#!/bin/bash
# Starts Orion: Postgres, Redis and the frontend in Docker, the backend API on this machine (extraction runs
# extractor/, which needs the GPU and its own venv; see docker-compose.yml). Ctrl+C stops the API; the containers keep running
# (stop them with: docker compose down).
set -e
cd "$(dirname "$0")"

GREEN='\033[0;32m'; BLUE='\033[0;34m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
fail() { echo -e "${RED}$1${NC}"; exit 1; }

echo -e "${BLUE}Starting Orion World State Engine${NC}"

# ---- prerequisites (setup: backend/README.md, extractor/requirements.txt)
[ -x backend/.venv/bin/uvicorn ] || fail "backend/.venv is missing: create it and pip install -r backend/requirements.txt"
[ -f backend/.env ] || fail "backend/.env is missing: cp backend/.env.example backend/.env"
[ -x extractor/.venv/bin/python ] || fail "extractor/.venv is missing: extraction needs it (see extractor/requirements.txt)"
curl -sf http://localhost:11434/api/tags >/dev/null || fail "Ollama is not running on localhost:11434"
curl -sf http://localhost:11434/api/tags | grep -q '"nuextract2-4b' \
  || fail "Ollama has no nuextract2-4b model: register it (see extractor/requirements.txt)"
if ss -ltn 2>/dev/null | grep -q ':8000 '; then
  fail "Port 8000 is in use (an API already running?)"
fi

# ---- containers
echo -e "${YELLOW}Starting Postgres, Redis and the frontend...${NC}"
docker compose up -d --build db redis frontend
echo -e "${YELLOW}Waiting for Postgres...${NC}"
until [ "$(docker inspect -f '{{.State.Health.Status}}' orion_db)" = "healthy" ]; do sleep 1; done

echo -e "${GREEN}Frontend: ${BLUE}http://localhost:5173${NC}   API: ${BLUE}http://localhost:8000${NC}"
echo -e "Don't use the AI Assistant while a manuscript is processing: its model and the extractor don't fit on the GPU together."
echo -e "${YELLOW}Starting the API (Ctrl+C to stop)...${NC}"
cd backend
exec .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
