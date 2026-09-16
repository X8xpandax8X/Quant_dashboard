from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api import create_app
from app.config import Settings
from data_engine.service import DataService, HistoryResult

ORIGIN = "http://testserver"
PAYLOAD = {"name": "Research basket", "positions": [{"symbol":"MSFT","weight_bps":6000},{"symbol":"AAPL","weight_bps":4000}]}


@pytest.fixture
def client(tmp_path):
    app = create_app(Settings(mode="demo", storage_dir=tmp_path, public_origin=ORIGIN, _env_file=None))
    with TestClient(app) as client:
        yield client
    app.state.store.engine.dispose()


def signin(client):
    r = client.post("/api/v1/auth/demo", headers={"Origin":ORIGIN})
    assert r.status_code == 200
    return {"Origin":ORIGIN,"X-CSRF-Token":r.json()["csrf_token"]}


def test_auth_and_csrf(client):
    assert client.get("/api/v1/portfolios").status_code == 401
    assert client.post("/api/v1/auth/demo", headers={"Origin":"https://evil.example"}).status_code == 403
    headers = signin(client)
    assert client.get("/api/v1/auth/me").headers["cache-control"] == "no-store"
    assert client.post("/api/v1/portfolios", json=PAYLOAD).status_code == 403
    assert client.post("/api/v1/portfolios", json=PAYLOAD, headers={**headers,"Origin":"https://evil.example"}).status_code == 403
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401


def test_portfolio_crud_revision_and_idempotency(client):
    headers = {**signin(client), "Idempotency-Key":"create-once"}
    first = client.post("/api/v1/portfolios", json=PAYLOAD, headers=headers)
    assert first.status_code == 201
    saved = first.json()
    assert "owner_id" not in saved
    again = client.post("/api/v1/portfolios", json=PAYLOAD, headers=headers)
    assert again.json()["id"] == saved["id"]
    assert len(client.get("/api/v1/portfolios").json()["items"]) == 1
    url = "/api/v1/portfolios/" + saved["id"]
    edited = {**PAYLOAD,"name":"Renamed basket","revision":1}
    assert client.patch(url,json=edited,headers=headers).json()["revision"] == 2
    assert client.patch(url,json=edited,headers=headers).status_code == 409
    assert client.delete(url+"?revision=1",headers=headers).status_code == 409
    assert client.delete(url+"?revision=2",headers=headers).status_code == 204
    assert client.get(url).status_code == 404


def test_validation_and_simulation(client):
    h = signin(client)
    for positions in [[],[{"symbol":"BTC-USD","weight_bps":10000}], [{"symbol":"MSFT","weight_bps":-1}], [{"symbol":"MSFT","weight_bps":5000},{"symbol":"MSFT","weight_bps":5000}], [{"symbol":"MSFT","weight_bps":1.5}]]:
        assert client.post("/api/v1/portfolio-analytics",json={"positions":positions},headers=h).status_code == 422
    assert client.post("/api/v1/portfolio-analytics",json={"positions":[{"symbol":"MSFT","weight_bps":9999}]},headers=h).status_code == 422
    r = client.post("/api/v1/portfolio-analytics",json={"positions":PAYLOAD["positions"]},headers=h)
    assert r.status_code == 200, r.text
    result = r.json()
    assert result["meta"]["status"] == "demo"
    assert sum(s["weight_bps"] for s in result["sectors"]) == 10000
    assert result["metrics"]["sample_count"] >= 60
    assert result["metrics"]["volatility"] > 0


@pytest.mark.parametrize("route", ["/universe?q=MSFT", "/markets?timeframe=1D", "/stocks/MSFT/prices?timeframe=5D", "/stocks/MSFT/analytics?peers=AAPL,NVDA", "/stocks/MSFT/fundamentals"])
def test_research_routes_real_response_contract(client, route):
    signin(client)
    response = client.get("/api/v1"+route)
    assert response.status_code == 200, response.text
    assert "NaN" not in response.text and "Infinity" not in response.text
    if "meta" in response.json():
        assert response.json()["meta"]["status"] == "demo"


def test_window_and_peer_validation(client):
    signin(client)
    assert client.get("/api/v1/stocks/INVALID/prices").status_code == 422
    assert client.get("/api/v1/stocks/MSFT/prices?timeframe=MAX").status_code == 422
    assert client.get("/api/v1/stocks/MSFT/analytics?peers=AAPL,NVDA,AMZN,META,GOOGL,TSLA").status_code == 422


def test_production_guard_and_owner_isolation(tmp_path):
    with pytest.raises(RuntimeError):
        create_app(Settings(storage_dir=tmp_path,_env_file=None))
    settings = Settings(mode="production",storage_dir=tmp_path,public_origin="https://research.example",proxy_secret="s"*48,allowed_emails="a@example.com,b@example.com",data_rights_confirmed=True,_env_file=None)
    app = create_app(settings,DataService(tmp_path/"demo-cache","demo"))
    with TestClient(app) as c:
        a = {"X-Proxy-Secret":"s"*48,"X-Auth-User":"google-a","X-Auth-Email":"a@example.com"}
        b = {**a,"X-Auth-User":"google-b","X-Auth-Email":"b@example.com"}
        assert c.get("/api/v1/auth/me",headers={"X-Auth-User":"google-a","X-Auth-Email":"a@example.com"}).status_code == 401
        assert c.get("/api/v1/auth/me",headers={**a,"X-Auth-Email":"unlisted@example.com"}).status_code == 403
        assert c.post("/api/v1/auth/demo").status_code == 404
        for h in [a,b]:
            h["X-CSRF-Token"] = c.get("/api/v1/auth/me",headers=h).json()["csrf_token"]
            h["Origin"] = settings.public_origin
        saved = c.post("/api/v1/portfolios",json=PAYLOAD,headers=a).json()
        url = "/api/v1/portfolios/"+saved["id"]
        assert c.get(url,headers=b).status_code == 404
        assert c.get("/api/v1/portfolios",headers=b).json()["items"] == []
        assert c.patch(url,json={**PAYLOAD,"revision":1},headers=b).status_code == 404
        assert c.delete(url+"?revision=1",headers=b).status_code == 404
        assert c.get(url,headers=a).status_code == 200
    app.state.store.engine.dispose()


def test_atomic_revision(tmp_path):
    from app.db import Conflict, PortfolioStore
    store = PortfolioStore(tmp_path/"portfolios.sqlite3")
    item = store.create("u","Basket",PAYLOAD["positions"])
    def writer(name):
        try:
            return store.update("u",item["id"],name,PAYLOAD["positions"],1)["revision"]
        except Conflict:
            return "conflict"
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(writer,["A","B"]))
    assert sorted(map(str,results)) == ["2","conflict"]
    store.engine.dispose()


def test_persistence_restart(tmp_path):
    from app.db import PortfolioStore
    path = tmp_path/"portfolios.sqlite3"
    first = PortfolioStore(path)
    item=first.create("user","Saved",PAYLOAD["positions"])
    first.engine.dispose()
    second=PortfolioStore(path)
    assert second.get("user",item["id"])["positions"] == PAYLOAD["positions"]
    second.engine.dispose()


def test_expired_demo_session_rejects_reads_and_writes(client, monkeypatch):
    from itsdangerous import TimestampSigner

    headers = signin(client)
    now = TimestampSigner.get_timestamp(TimestampSigner("test"))
    monkeypatch.setattr(TimestampSigner, "get_timestamp", lambda self: now + 28801)
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.get("/api/v1/portfolios").status_code == 401
    assert client.post("/api/v1/portfolios", json=PAYLOAD, headers=headers).status_code == 401


def test_portfolio_metadata_is_partial_when_risk_free_is_unavailable(tmp_path, monkeypatch):
    data = DataService(tmp_path / "fixture-cache", "demo")
    original_history = data.get_history

    def fresh_history(symbol, timeframe="1Y"):
        result = original_history(symbol, timeframe)
        meta = {**result.meta, "source": "fixture", "status": "fresh", "notes": []}
        return HistoryResult(result.frame, meta)

    monkeypatch.setattr(data, "get_history", fresh_history)
    monkeypatch.setattr(data, "risk_free_rate", lambda: {
        "rate": None,
        "date": None,
        "meta": {"status": "unavailable"},
    })
    settings = Settings(
        mode="production",
        storage_dir=tmp_path / "state",
        public_origin="https://research.example",
        proxy_secret="s" * 48,
        allowed_emails="a@example.com",
        data_rights_confirmed=True,
        _env_file=None,
    )
    app = create_app(settings, data)
    headers = {
        "X-Proxy-Secret": "s" * 48,
        "X-Auth-User": "google-a",
        "X-Auth-Email": "a@example.com",
    }
    with TestClient(app) as production_client:
        auth = production_client.get("/api/v1/auth/me", headers=headers).json()
        headers.update(Origin=settings.public_origin, **{"X-CSRF-Token": auth["csrf_token"]})
        response = production_client.post(
            "/api/v1/portfolio-analytics",
            json={"positions": [{"symbol": "MSFT", "weight_bps": 10000}]},
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["metrics"]["sharpe"] is None
        assert response.json()["meta"]["status"] == "partial"
    app.state.store.engine.dispose()
