# TaxiAI

Taxi-driver copilot: demand map, forecasts, «куда ехать?» recommendations, finance tracking, Telegram bot (@taxiai1bot).

Stack: FastAPI + PostgreSQL/PostGIS + Redis (`apps/api`), Next.js PWA (`apps/web`), aiogram bot (`apps/bot`), adb+EasyOCR radar scraper on the Mac (`apps/scraper`, launchd every 30 min).

## Key make targets

- Dev: `make up` / `make migrate` / `make seed` / `make train` / `make test`
- Prod (VPS, docker compose + Caddy): `make prod-up` / `make prod-migrate` / `make prod-logs` — see `infra/DEPLOY.md`

## Architecture notes

- External providers live behind `apps/api/app/providers/` (mock/live, chosen by `*_PROVIDER_MODE` env vars, auto-fallback to mock).
- The surge source cascade (radar > live > synthetic) lives in `apps/api/app/services/surge_service.py`; real kef readings land in `kef_observations` via `POST /v1/kef/ingest`.
- Periodic jobs run in the `worker` container: `apps/api/app/jobs/scheduler.py`.

## AI Office

Registered as `taxi` in the AI Office (`/Users/tim/Documents/work/AI Office`); project state doc: `docs/state/projects/taxi.md` there. Sessions follow the office work cycle (plan → actions → verification → short update to Tim in Russian).
