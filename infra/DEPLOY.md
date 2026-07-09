# Развёртывание на VPS

Целевая конфигурация: Ubuntu 24.04, **4 ГБ RAM** (еженедельное переобучение
модели в пике ест ~2.5–3 ГБ), 2 vCPU, 30+ ГБ диска. Подходят Timeweb Cloud,
Beget, Selectel — ~500–800 ₽/мес.

## 1. Разовая подготовка сервера (от root)

```bash
apt update && apt install -y docker.io docker-compose-v2 git
```

DNS: у регистратора домена создать **A-запись** на IP сервера
(`taxi.example.ru → 1.2.3.4`). HTTPS-сертификат Caddy получит и будет
продлевать сам, ничего настраивать не нужно.

## 2. Код и конфигурация

```bash
git clone https://github.com/dondochik-a11y/taxiai.git /opt/taxiai
cd /opt/taxiai
cp .env.example .env
```

Docker Compose читает переменные для подстановки (`${POSTGRES_PASSWORD}`,
`${DOMAIN}`) из `.env` рядом с compose-файлом, т.е. из `infra/.env`. Заведите
симлинк на корневой `.env`, иначе `up` упадёт с «required variable … is missing»:

```bash
ln -sf ../.env infra/.env
```

Нет своего домена? Подойдёт бесплатный `<IP>.sslip.io` (резолвится в этот IP,
Let's Encrypt его принимает) — например `DOMAIN=93.189.228.203.sslip.io`.

В `.env` заполнить:

```bash
ENVIRONMENT=production
POSTGRES_PASSWORD=<сгенерировать: openssl rand -hex 24>
DOMAIN=taxi.example.ru   # или <IP>.sslip.io
TELEGRAM_BOT_TOKEN=<токен @taxiai1bot>
# + все ключи провайдеров, которые были в локальном .env
# (TOMTOM_API_KEY, OPENWEATHER_API_KEY, AVIATIONSTACK_API_KEY, OPENSKY_*,
#  *_PROVIDER_MODE=live, и YANDEX_TAXI_* когда придёт)
```

Важно: бот может long-poll'ить Telegram только из одного места — перед
запуском на сервере остановить локальный: `docker stop infra-bot-1` на Mac.

## 3. Перенос накопленной истории с Mac (опционально, но жалко терять)

На Mac:

```bash
make backup                             # backups/taxi-<дата>.sql.gz
scp backups/taxi-*.sql.gz root@<IP>:/opt/taxiai/
```

На сервере восстановление ДО старта api (его entrypoint гонит
`alembic upgrade head` и на пустой базе создал бы таблицы, конфликтуя с дампом).
Поэтому сначала поднимаем только db:

```bash
cd /opt/taxiai
docker compose -f infra/docker-compose.prod.yml up -d db     # только база
# дождаться healthy, затем:
gunzip -c taxi-*.sql.gz | docker compose -f infra/docker-compose.prod.yml exec -T db psql -U taxi taxi
# (ошибки «schema tiger/topology already exists» безвредны — это схемы PostGIS)
```

Модель (`apps/api/app/ml/artifacts/demand_model.joblib`) в git не хранится —
скопируйте её с Mac тем же `scp`, иначе после запуска выполните `make train`.

Если история не нужна — пропустить и после запуска выполнить обычные
`prod-migrate`, seed и train (см. корневой README).

## 4. Запуск

```bash
cd /opt/taxiai
make prod-up        # соберёт и поднимет db, redis, api, worker, bot, web, caddy
make prod-migrate   # применит миграции (no-op, если базу восстановили из дампа)
```

Через минуту приложение доступно на `https://<DOMAIN>` (первый заход может
занять ~10 сек — Caddy получает сертификат). Геолокация в браузере телефона
работает — контекст безопасный.

## 5. Бэкапы на сервере

```bash
crontab -e
# ежедневно в 04:15 UTC, хранить последние 14:
15 4 * * * cd /opt/taxiai && make backup && ls -t backups/*.sql.gz | tail -n +15 | xargs -r rm
```

## Обновление кода

```bash
cd /opt/taxiai && git pull && make prod-up && make prod-migrate
```

## Что где слушает

Наружу открыты только 80/443 (Caddy). Postgres/Redis/API живут во внутренней
docker-сети и с интернета недоступны. Маршрутизация: `https://DOMAIN/api/*` →
FastAPI (префикс `/api` срезается), всё остальное → Next.js.
