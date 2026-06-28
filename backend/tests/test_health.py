"""Smoke-тест: приложение собирается и эндпоинт /health отвечает 200.

Использует httpx.ASGITransport, чтобы гонять запросы прямо по ASGI-приложению
без поднятого сетевого сервера (быстро и детерминированно в CI).
"""

import httpx
import pytest

from app.main import app, create_app


def test_create_app_returns_fresh_instances() -> None:
    """Фабрика всегда отдаёт новый экземпляр приложения."""
    assert create_app() is not create_app()


@pytest.mark.asyncio
async def test_health_returns_ok() -> None:
    """GET /health -> HTTP 200 и тело status=ok."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
