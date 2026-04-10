import pytest

from app.services import data_cache_service


@pytest.mark.asyncio
async def test_data_cache_returns_cached_value_until_ttl_expires(monkeypatch):
    data_cache_service.clear()

    clock = {"value": 100.0}
    monkeypatch.setattr(data_cache_service.time, "monotonic", lambda: clock["value"])

    calls = {"count": 0}

    async def loader():
        calls["count"] += 1
        return {"value": calls["count"]}

    first = await data_cache_service.get_or_set("demo", loader, ttl_seconds=10)
    second = await data_cache_service.get_or_set("demo", loader, ttl_seconds=10)

    clock["value"] = 111.0
    third = await data_cache_service.get_or_set("demo", loader, ttl_seconds=10)

    assert first == {"value": 1}
    assert second == {"value": 1}
    assert third == {"value": 2}
    assert calls["count"] == 2
