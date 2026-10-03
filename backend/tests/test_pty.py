"""Terminal interativo (PTY por WebSocket)."""
import json
import time

import pytest
from starlette.websockets import WebSocketDisconnect

TOKEN = "test-token-123"


class Term:
    """Cliente mínimo do protocolo: lê frames até achar um texto na tela."""

    def __init__(self, ws):
        self.ws = ws
        self.screen = ""
        self.control: list[dict] = []

    def send(self, data: str) -> None:
        self.ws.send_json({"type": "input", "data": data})

    def expect(self, text: str, timeout: float = 10) -> str:
        deadline = time.monotonic() + timeout
        while text not in self.screen:
            assert time.monotonic() < deadline, f"não apareceu {text!r}; tela:\n{self.screen[-800:]}"
            msg = self.ws.receive()
            if msg.get("bytes") is not None:
                self.screen += msg["bytes"].decode("utf-8", "replace")
            elif msg.get("text") is not None:
                self.control.append(json.loads(msg["text"]))
                if self.control[-1]["type"] == "exit":
                    break
        return self.screen


def open_term(client, session=None, cols=80, rows=24):
    ws = client.websocket_connect("/api/terminal/ws")
    conn = ws.__enter__()
    conn.send_json({"type": "auth", "token": TOKEN, "session": session, "cols": cols, "rows": rows})
    ready = conn.receive_json()
    assert ready["type"] == "ready", ready
    return ws, conn, ready


def test_rejects_wrong_token(client):
    with client.websocket_connect("/api/terminal/ws") as ws:
        ws.send_json({"type": "auth", "token": "errado"})
        assert ws.receive_json() == {"type": "error", "message": "Não autenticado."}
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()


def test_rejects_foreign_origin(client):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/api/terminal/ws", headers={"Origin": "http://evil.example"}) as ws:
            ws.receive_json()


def test_interactive_program_reads_the_keyboard(client, settings):
    ws, conn, ready = open_term(client)
    try:
        t = Term(conn)
        assert ready["resumed"] is False
        t.send("pwd\r")
        t.expect(str(settings.uploads_dir))  # começa na pasta de arquivos
        # programa interativo: pergunta e espera a resposta digitada (impossível no modo antigo)
        t.send('read -p "nome? " n; echo "oi, $n!"\r')
        t.expect("nome? ")
        t.send("Luan\r")
        t.expect("oi, Luan!")
        t.send("stty size\r")
        t.expect("24 80")
        conn.send_json({"type": "resize", "cols": 100, "rows": 30})
        t.send("stty size\r")
        t.expect("30 100")
    finally:
        conn.send_json({"type": "close"})
        ws.__exit__(None, None, None)


def test_ctrl_c_interrupts_and_shell_survives(client):
    ws, conn, _ = open_term(client)
    try:
        t = Term(conn)
        t.send("sleep 300; echo nao-$((1+1))-devia\r")
        time.sleep(0.5)
        t.send("\x03")  # Ctrl+C
        t.send("echo vivo-$((40+2))\r")
        t.expect("vivo-42")
        assert "nao-2-devia" not in t.screen
    finally:
        conn.send_json({"type": "close"})
        ws.__exit__(None, None, None)


def test_reconnect_resumes_same_shell_with_scrollback(client):
    ws, conn, ready = open_term(client)
    t = Term(conn)
    t.send("export MARCA=persistiu; echo antes-de-cair\r")
    t.expect("antes-de-cair")
    ws.__exit__(None, None, None)  # a conexão cai (app em segundo plano)

    ws2, conn2, again = open_term(client, session=ready["session"])
    try:
        assert again == {"type": "ready", "session": ready["session"], "resumed": True}
        t2 = Term(conn2)
        t2.expect("antes-de-cair")  # tela de antes volta
        t2.send("echo $MARCA\r")
        t2.expect("persistiu")  # mesmo shell, mesmas variáveis
    finally:
        conn2.send_json({"type": "close"})
        ws2.__exit__(None, None, None)


def test_exit_ends_the_session(client):
    ws, conn, ready = open_term(client)
    try:
        t = Term(conn)
        t.send("exit 7\r")
        t.expect("\x00never")  # lê até o evento de saída
        assert t.control[-1] == {"type": "exit", "code": 7}
    finally:
        ws.__exit__(None, None, None)
    ws2, conn2, again = open_term(client, session=ready["session"])
    try:
        assert again["resumed"] is False and again["session"] != ready["session"]
    finally:
        conn2.send_json({"type": "close"})
        ws2.__exit__(None, None, None)


def test_secrets_not_in_terminal_env(client, monkeypatch):
    monkeypatch.setenv("APP_API_TOKEN", "segredo-token")
    ws, conn, _ = open_term(client)
    try:
        t = Term(conn)
        t.send('echo "[${APP_API_TOKEN:-vazio}] TERM=$TERM"\r')
        t.expect("TERM=xterm-256color")
        assert "[vazio]" in t.screen and "segredo-token" not in t.screen
    finally:
        conn.send_json({"type": "close"})
        ws.__exit__(None, None, None)
