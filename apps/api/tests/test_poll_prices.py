"""The price poll must stay dormant without Yandex credentials — a mock-mode
poll would write fake rows into price_observations and surge_service would
serve them as source="live"."""
from app.jobs.poll_prices import poll_prices


def test_noop_without_yandex_credentials(monkeypatch):
    monkeypatch.delenv("YANDEX_TAXI_CLID", raising=False)
    monkeypatch.delenv("YANDEX_TAXI_API_KEY", raising=False)
    monkeypatch.delenv("PRICING_PROVIDER_MODE", raising=False)
    from app.core.config import get_settings

    get_settings.cache_clear()
    try:
        # session=None proves the gate fires before any DB access
        assert poll_prices(None) == 0
    finally:
        get_settings.cache_clear()
