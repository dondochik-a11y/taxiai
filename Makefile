.PHONY: up down logs migrate seed train patterns test web-dev backup prod-up prod-logs prod-migrate

up:
	docker compose -f infra/docker-compose.yml up -d --build

down:
	docker compose -f infra/docker-compose.yml down

logs:
	docker compose -f infra/docker-compose.yml logs -f

migrate:
	docker compose -f infra/docker-compose.yml exec api alembic upgrade head

seed:
	docker compose -f infra/docker-compose.yml exec api python scripts/seed_synthetic_history.py

train:
	docker compose -f infra/docker-compose.yml exec api python -m app.ml.train_demand_model

patterns:
	docker compose -f infra/docker-compose.yml exec api python -m app.ml.pattern_mining

test:
	docker compose -f infra/docker-compose.yml exec api pytest -q

web-dev:
	cd apps/web && pnpm dev

backup:
	mkdir -p backups && docker exec infra-db-1 pg_dump -U taxi taxi | gzip > backups/taxi-$$(date +%Y%m%d-%H%M%S).sql.gz && ls -lh backups/ | tail -1

# Production stack on a VPS (HTTPS via Caddy) — see infra/DEPLOY.md
prod-up:
	docker compose -f infra/docker-compose.prod.yml up -d --build

prod-logs:
	docker compose -f infra/docker-compose.prod.yml logs -f

prod-migrate:
	docker compose -f infra/docker-compose.prod.yml exec api alembic upgrade head
