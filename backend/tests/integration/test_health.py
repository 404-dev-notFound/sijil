from httpx import AsyncClient


async def test_health_ready_returns_ok_against_real_db(client: AsyncClient) -> None:
    response = await client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
