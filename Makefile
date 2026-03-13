.PHONY: up down build migrate seed test logs shell deploy ssl ssl-renew

# ── Development ──────────────────────────────────────────────────────────────
up:
	docker compose up -d

down:
	docker compose down

build:
	docker compose build

migrate:
	docker compose exec api alembic upgrade head

seed:
	docker compose exec api python -m scripts.seed

test:
	docker compose exec api pytest -v

logs:
	docker compose logs -f api

shell:
	docker compose exec api bash

# ── Production (aso.zouqly.com) ──────────────────────────────────────────────
# First-time deploy:  make ssl && make deploy
# Update deploy:      make deploy

# Build React frontend
frontend-build:
	cd frontend && npm ci --legacy-peer-deps && npm run build

# Get Let's Encrypt SSL certificate (run once on first deploy)
ssl:
	chmod +x scripts/init_ssl.sh && ./scripts/init_ssl.sh

# Renew SSL certificate (add to monthly cron)
ssl-renew:
	chmod +x scripts/renew_ssl.sh && ./scripts/renew_ssl.sh

# Full production deploy: build frontend → build docker images → start all services → migrate
deploy: frontend-build
	docker compose build
	docker compose up -d
	sleep 5
	docker compose exec api alembic upgrade head
	@echo ""
	@echo "✅ Deployed! https://aso.zouqly.com"
