from fastapi.testclient import TestClient


def test_list_watchlist_empty(client: TestClient, auth_headers: dict) -> None:
    resp = client.get("/v1/watchlist", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []


def test_add_and_list_watchlist(client: TestClient, auth_headers: dict) -> None:
    resp = client.post(
        "/v1/watchlist",
        json={"ticker": "aapl", "memo": "Apple stock"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["ticker"] == "AAPL"
    assert data["memo"] == "Apple stock"

    resp = client.get("/v1/watchlist", headers=auth_headers)
    assert len(resp.json()) == 1


def test_add_duplicate_ticker(client: TestClient, auth_headers: dict) -> None:
    client.post("/v1/watchlist", json={"ticker": "MSFT"}, headers=auth_headers)
    resp = client.post("/v1/watchlist", json={"ticker": "msft"}, headers=auth_headers)
    assert resp.status_code == 409


def test_update_watchlist_memo(client: TestClient, auth_headers: dict) -> None:
    client.post("/v1/watchlist", json={"ticker": "GOOG"}, headers=auth_headers)
    resp = client.patch("/v1/watchlist/GOOG", json={"memo": "Updated memo"}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["memo"] == "Updated memo"


def test_delete_watchlist_item(client: TestClient, auth_headers: dict) -> None:
    client.post("/v1/watchlist", json={"ticker": "NVDA"}, headers=auth_headers)
    resp = client.delete("/v1/watchlist/NVDA", headers=auth_headers)
    assert resp.status_code == 204

    resp = client.get("/v1/watchlist", headers=auth_headers)
    assert resp.json() == []


def test_delete_nonexistent_ticker(client: TestClient, auth_headers: dict) -> None:
    resp = client.delete("/v1/watchlist/FAKE", headers=auth_headers)
    assert resp.status_code == 404


def test_watchlist_requires_auth(client: TestClient) -> None:
    resp = client.get("/v1/watchlist")
    assert resp.status_code == 403
