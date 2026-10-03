import json
import os
import time
from dataclasses import replace

from fastapi.testclient import TestClient

from app.server import create_app

AUTH = {"Authorization": "Bearer test-token-123"}


def run(client, command, cwd=None):
    r = client.post("/api/terminal/run", json={"command": command, "cwd": cwd}, headers=AUTH)
    assert r.status_code == 200, r.text
    events = [json.loads(line) for line in r.text.splitlines() if line]
    out = "".join(e.get("out", "") for e in events)
    last = events[-1]
    assert "exit" in last
    return out, last["exit"], last["cwd"]


def test_terminal_requires_token(client):
    assert client.post("/api/terminal/run", json={"command": "id"}).status_code == 401


def test_runs_command_and_merges_stderr(client):
    out, code, _ = run(client, "echo olá; echo erro >&2; exit 3")
    assert "olá" in out and "erro" in out and code == 3


def test_starts_in_files_dir_and_cd_carries_over(client, settings, tmp_path):
    _, _, cwd = run(client, "true")
    assert cwd == str(settings.uploads_dir)
    (tmp_path / "sub").mkdir()
    _, _, cwd = run(client, f"cd {tmp_path}/sub", cwd)
    assert cwd == str(tmp_path / "sub")
    out, _, _ = run(client, "pwd", cwd)
    assert out.strip() == str(tmp_path / "sub")


def test_bad_cwd_falls_back_to_files_dir(client, settings):
    _, _, cwd = run(client, "true", "/nao/existe")
    assert cwd == str(settings.uploads_dir)


def test_secrets_are_not_visible_to_commands(client, monkeypatch):
    monkeypatch.setenv("APP_API_TOKEN", "segredo-token")
    monkeypatch.setenv("APP_SECRET_KEY", "segredo-chave")
    out, _, _ = run(client, "env")
    assert "segredo-token" not in out and "segredo-chave" not in out


def test_timeout_kills_the_whole_process_group(settings):
    with TestClient(create_app(replace(settings, terminal_timeout_s=1))) as c:
        started = time.monotonic()
        out, code, _ = run(c, "sleep 30 & sleep 30; echo nunca")
        assert code == 124 and "tempo esgotado" in out and "nunca" not in out
        assert time.monotonic() - started < 10


def test_terminal_can_be_disabled(settings):
    with TestClient(create_app(replace(settings, enable_terminal=False))) as c:
        assert c.post("/api/terminal/run", json={"command": "id"}, headers=AUTH).status_code == 404


def test_upload_list_and_delete(client, settings):
    r = client.post("/api/files", files=[("files", ("a.txt", b"um")), ("files", ("a.txt", b"dois"))], headers=AUTH)
    assert r.status_code == 201
    names = [f["name"] for f in r.json()["saved"]]
    assert names == ["a.txt", "a (1).txt"]  # nunca sobrescreve
    assert (settings.uploads_dir / "a (1).txt").read_bytes() == b"dois"
    listed = client.get("/api/files", headers=AUTH).json()
    assert [f["name"] for f in listed["files"]] == ["a (1).txt", "a.txt"]
    assert client.delete("/api/files/a.txt", headers=AUTH).status_code == 204
    assert client.delete("/api/files/a.txt", headers=AUTH).status_code == 404


def test_upload_strips_directories_from_names(client, settings):
    r = client.post("/api/files", files=[("files", ("../../etc/evil.sh", b"x"))], headers=AUTH)
    assert r.json()["saved"][0]["name"] == "evil.sh"
    assert (settings.uploads_dir / "evil.sh").exists()
    assert client.post("/api/files", files=[("files", ("..", b"x"))], headers=AUTH).status_code == 400


def test_upload_size_limit_leaves_nothing_behind(settings):
    with TestClient(create_app(replace(settings, max_upload_mb=1))) as c:
        r = c.post("/api/files", files=[("files", ("big.bin", b"0" * (2 << 20)))], headers=AUTH)
        assert r.status_code == 413
        assert os.listdir(settings.uploads_dir) == []


def test_uploaded_file_is_visible_in_terminal(client):
    client.post("/api/files", files=[("files", ("dados.csv", b"a,b\n1,2\n"))], headers=AUTH)
    out, code, _ = run(client, "cat dados.csv | wc -l")
    assert code == 0 and out.strip() == "2"
