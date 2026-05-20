.PHONY: help up down backend frontend install migrate dev

BACKEND_DIR := backend
FRONTEND_DIR := frontend
DATABASE_URL := postgresql+psycopg://medcenters:medcenters@127.0.0.1:5434/medcenters

help:
	@echo "Usage:"
	@echo "  make up         - Start the PostgreSQL database (Docker)"
	@echo "  make down       - Stop the database"
	@echo "  make install    - Install backend and frontend dependencies"
	@echo "  make migrate    - Run Alembic migrations"
	@echo "  make backend    - Run backend (uvicorn, hot-reload)"
	@echo "  make frontend   - Run frontend dev server (Vite)"
	@echo "  make dev        - Start DB + backend + frontend in parallel"

up:
	docker compose up -d

down:
	docker compose down

$(BACKEND_DIR)/.venv/bin/python:
	cd $(BACKEND_DIR) && python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt

$(FRONTEND_DIR)/node_modules/.bin/vite:
	cd $(FRONTEND_DIR) && npm install

install: $(BACKEND_DIR)/.venv/bin/python $(FRONTEND_DIR)/node_modules/.bin/vite

migrate: $(BACKEND_DIR)/.venv/bin/python
	cd $(BACKEND_DIR) && DATABASE_URL=$(DATABASE_URL) .venv/bin/python -m alembic upgrade head

backend: $(BACKEND_DIR)/.venv/bin/python
	cd $(BACKEND_DIR) && DATABASE_URL=$(DATABASE_URL) .venv/bin/python -m uvicorn app.main:app --reload --port 8000

frontend: $(FRONTEND_DIR)/node_modules/.bin/vite
	cd $(FRONTEND_DIR) && npm run dev

dev: up $(BACKEND_DIR)/.venv/bin/python $(FRONTEND_DIR)/node_modules/.bin/vite
	-lsof -ti:8000 | xargs kill -9 2>/dev/null; true
	cd $(BACKEND_DIR) && DATABASE_URL=$(DATABASE_URL) .venv/bin/python -m alembic upgrade head
	@trap 'kill 0; pkill -f "uvicorn app.main" 2>/dev/null; docker compose stop; exit 0' INT TERM; \
	cd $(BACKEND_DIR) && DATABASE_URL=$(DATABASE_URL) .venv/bin/python -m uvicorn app.main:app --reload --port 8000 & \
	cd $(FRONTEND_DIR) && node_modules/.bin/vite & \
	wait
