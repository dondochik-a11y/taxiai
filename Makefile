.PHONY: up down logs migrate seed train patterns web-dev

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

web-dev:
	cd apps/web && pnpm dev
