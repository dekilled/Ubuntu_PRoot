from fastapi.testclient import TestClient

from app.config import Settings, load_settings
from app.crypto import SecretBox
from app.server import create_app

import pytest


def test_health_is_public_and_echoes_boot_id(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "boot": "boot-abc", "port": 8001}


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer nope"}, {"Authorization": "Basic test-token-123"}])
def test_private_routes_require_the_token(client, headers):
    assert client.get("/api/system", headers=headers).status_code == 401
    assert client.get("/api/notes", headers=headers).status_code == 401


def test_system_reports_runtime(client, auth):
    body = client.get("/api/system", headers=auth).json()
    assert body["python"] and body["os"]


def test_notes_crud_persists_in_sqlite(client, auth):
    assert client.get("/api/notes", headers=auth).json() == []
    created = client.post("/api/notes", json={"text": "  olá  "}, headers=auth)
    assert created.status_code == 201 and created.json()["text"] == "olá"
    assert [n["text"] for n in client.get("/api/notes", headers=auth).json()] == ["olá"]
    assert client.delete(f"/api/notes/{created.json()['id']}", headers=auth).status_code == 204
    assert client.delete("/api/notes/999", headers=auth).status_code == 404
    assert client.post("/api/notes", json={"text": ""}, headers=auth).status_code == 422


def test_migrations_are_idempotent(settings):
    with TestClient(create_app(settings)) as c:
        c.post("/api/notes", json={"text": "a"}, headers={"Authorization": "Bearer test-token-123"})
    with TestClient(create_app(settings)) as c:  # segunda partida sobre o mesmo arquivo
        assert len(c.get("/api/notes", headers={"Authorization": "Bearer test-token-123"}).json()) == 1


def test_cors_allows_the_capacitor_origin_only(client):
    ok = client.options("/api/notes", headers={"Origin": "http://localhost", "Access-Control-Request-Method": "GET", "Access-Control-Request-Headers": "authorization"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost"
    bad = client.options("/api/notes", headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in bad.headers


def test_serves_frontend_without_shadowing_api(settings, tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<h1>oi</h1>")
    (dist / "app.js").write_text("1")
    s = Settings(**{**settings.__dict__, "frontend_dist": dist})
    with TestClient(create_app(s)) as c:
        assert "oi" in c.get("/qualquer/rota").text
        assert c.get("/app.js").text == "1"
        assert c.get("/api/nada").status_code == 404
        assert c.get("/api/health").json()["ok"] is True
        assert "oi" in c.get("/../../etc/passwd").text  # nunca sai de dist


def test_secretbox_roundtrip_and_wrong_key():
    box = SecretBox("k1")
    token = box.encrypt("segredo")
    assert token.startswith("enc:") and box.decrypt(token) == "segredo"
    assert box.encrypt(token) == token  # não cifra duas vezes
    assert SecretBox("k2").decrypt(token) == ""
    assert box.decrypt("texto puro") == "texto puro"


def test_settings_fail_closed_without_token():
    with pytest.raises(RuntimeError):
        load_settings({})
    s = load_settings({"APP_DEV": "1"})
    assert s.api_token == "dev-token"
    s = load_settings({"APP_API_TOKEN": "abcdefgh", "APP_SECRET_KEY": "12345678", "CORS_ORIGINS": "*,http://x.test"})
    assert "*" not in s.cors_origins and "http://x.test" in s.cors_origins
