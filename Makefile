.PHONY: setup dev smoke-goose test clean phase-status commit-plan ai-usage-check

GOOSE_PORT ?= 3284
GOOSE_HOST ?= 127.0.0.1
BACKEND_PORT ?= 8001
FRONTEND_PORT ?= 5173

# ── One-time setup ────────────────────────────────────────────────────────────
setup:
	@echo "==> Installing backend dependencies"
	cd backend && python3 -m pip install -e ".[dev]" --quiet
	@echo "==> Installing frontend dependencies"
	cd frontend && npm install --silent
	@echo "==> Creating data directory"
	mkdir -p data/smoke
	@echo "==> Copying .env.example → .env (if not present)"
	@test -f .env || cp .env.example .env && echo "  Created .env — fill in ANTHROPIC_API_KEY before running smoke-goose or dev"
	@echo "==> Initialising database and seeding agents"
	cd backend && python3 -m scripts.seed_db
	@echo "==> Setup complete. Run 'make dev' to start all services."

# ── Development servers (all three) ──────────────────────────────────────────
dev: _preflight
	@echo "==> Starting Goose ACP server on :$(GOOSE_PORT)"
	@set -a && . ./.env && set +a && \
	goose serve --host $(GOOSE_HOST) --port $(GOOSE_PORT) --with-builtin developer &
	@sleep 2
	@echo "==> Starting FastAPI backend on :$(BACKEND_PORT)"
	@set -a && . ./.env && set +a && \
	cd backend && GOOSE_PORT=$(GOOSE_PORT) python3 -m uvicorn app.main:app --host 0.0.0.0 --port $${BACKEND_PORT:-8001} --reload &
	@sleep 1
	@echo "==> Starting Vite frontend on :$(FRONTEND_PORT)"
	cd frontend && npm run dev &
	@echo ""
	@echo "  Goose  → http://$(GOOSE_HOST):$(GOOSE_PORT)/health"
	@echo "  API    → http://localhost:$(BACKEND_PORT)/health"
	@echo "  UI     → http://localhost:$(FRONTEND_PORT)"
	@echo ""
	@echo "Press Ctrl+C to stop (or: kill $$(lsof -ti:$(GOOSE_PORT),$(BACKEND_PORT),$(FRONTEND_PORT)) 2>/dev/null)"

# ── Preflight: Goose must be reachable before dev starts ─────────────────────
_preflight:
	@echo "==> Preflight: checking Goose binary"
	@command -v goose >/dev/null 2>&1 || (echo "ERROR: goose not found. Install with: brew install block-goose-cli" && exit 1)
	@echo "==> Preflight: checking .env"
	@test -f .env || (echo "ERROR: .env missing. Run: cp .env.example .env and fill in ANTHROPIC_API_KEY" && exit 1)
	@grep -q '^ANTHROPIC_API_KEY=sk-ant-' .env 2>/dev/null || echo "WARN: ANTHROPIC_API_KEY may not be set — smoke gate will fail"
	@echo "==> Preflight: checking port $(BACKEND_PORT) is free for Yuno API"
	@if curl -sf "http://localhost:$(BACKEND_PORT)/health" 2>/dev/null | grep -q '"status":"ok"'; then \
		echo "  Yuno API already running on :$(BACKEND_PORT)"; \
	elif curl -sf "http://localhost:$(BACKEND_PORT)/health" 2>/dev/null | grep -q .; then \
		echo "ERROR: port $(BACKEND_PORT) is in use by another app (not Yuno). Set BACKEND_PORT=8001 in .env or stop the other process."; exit 1; \
	fi

# ── Smoke gate (AC-4) ─────────────────────────────────────────────────────────
smoke-goose:
	@echo "==> Running Goose ACP smoke gate"
	@test -f .env || (echo "ERROR: .env missing" && exit 1)
	@command -v goose >/dev/null 2>&1 || (echo "ERROR: goose not found" && exit 1)
	@set -a && . ./.env && set +a && python3 backend/scripts/smoke_gate.py
	@echo "==> Smoke gate complete — check data/smoke/ for captured frames"

# ── Tests ─────────────────────────────────────────────────────────────────────
test:
	cd backend && python3 -m pytest tests/ -v

test-live:
	cd backend && python3 -m pytest tests/ -v -m live

# ── Phase workflow helpers (read-only) ────────────────────────────────────────
phase-status:
	@python3 scripts/phase_status.py

commit-plan:
	@python3 scripts/commit_plan.py

ai-usage-check:
	@python3 scripts/ai_usage_check.py --phase "$(PHASE)"

# ── Clean ─────────────────────────────────────────────────────────────────────
clean:
	rm -rf data/yuno.db data/smoke/*.json
	find backend -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find backend -name "*.pyc" -delete 2>/dev/null || true
