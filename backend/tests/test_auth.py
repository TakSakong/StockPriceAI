from fastapi.testclient import TestClient


def test_register(client: TestClient) -> None:
    resp = client.post("/v1/auth/register", json={"email": "new@example.com", "password": "pass1234"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == "new@example.com"
    assert "id" in data


def test_register_duplicate_email(client: TestClient) -> None:
    payload = {"email": "dup@example.com", "password": "pass1234"}
    client.post("/v1/auth/register", json=payload)
    resp = client.post("/v1/auth/register", json=payload)
    assert resp.status_code == 409


def test_login(client: TestClient) -> None:
    client.post("/v1/auth/register", json={"email": "user@example.com", "password": "pass1234"})
    resp = client.post("/v1/auth/login", json={"email": "user@example.com", "password": "pass1234"})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


def test_login_wrong_password(client: TestClient) -> None:
    client.post("/v1/auth/register", json={"email": "user@example.com", "password": "pass1234"})
    resp = client.post("/v1/auth/login", json={"email": "user@example.com", "password": "wrongpass"})
    assert resp.status_code == 401


def test_refresh_token(client: TestClient) -> None:
    client.post("/v1/auth/register", json={"email": "user@example.com", "password": "pass1234"})
    login_resp = client.post("/v1/auth/login", json={"email": "user@example.com", "password": "pass1234"})
    refresh_token = login_resp.json()["refresh_token"]

    resp = client.post("/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 200
    assert "access_token" in resp.json()


def test_me(client: TestClient, auth_headers: dict) -> None:
    resp = client.get("/v1/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["email"] == "test@example.com"


def test_me_unauthenticated(client: TestClient) -> None:
    resp = client.get("/v1/auth/me")
    assert resp.status_code == 403
