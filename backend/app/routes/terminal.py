"""Terminal da base de testes.

1) Terminal interativo (o que a UI usa): WebSocket /api/terminal/ws ligado a um bash num PTY —
   ver app/pty_sessions.py. Protocolo:
     cliente → {"type": "auth", "token": "...", "session": "<id para reconectar>"?, "cols": 80, "rows": 24}
     servidor → {"type": "ready", "session": "<id>", "resumed": bool}, depois a saída do shell em
                frames BINÁRIOS (bytes crus do terminal), e {"type": "exit", "code": n} no fim
     cliente → {"type": "input", "data": "ls\r"} | {"type": "resize", "cols", "rows"} | {"type": "close"}

2) Comando avulso, sem PTY (útil para automação e testes), descrito abaixo.

Roda um comando de shell no Ubuntu (dentro do PRoot, no app) e
transmite a saída enquanto ela acontece.

Protocolo: POST /api/terminal/run {"command": "...", "cwd": "/root/files"} → resposta NDJSON
(uma linha JSON por evento):
    {"out": "<pedaço de stdout+stderr>"}     zero ou mais vezes
    {"exit": <código>, "cwd": "<diretório depois do comando>"}   sempre por último

Cada comando roda num `bash -c` próprio (não interativo, stdin vazio): `cd` funciona porque o
diretório final volta no evento "exit" e o cliente o manda no próximo comando. Cancelar = abortar
o request: o grupo de processos inteiro é morto. Também há um limite de tempo
(APP_TERMINAL_TIMEOUT, padrão 600 s).

⚠️ Isto é execução arbitrária de comandos (protegida pelo token do app). É ótimo para testar e
depurar; num app publicado, desligue com APP_ENABLE_TERMINAL=0 se não precisar.
"""
from __future__ import annotations

import asyncio
import codecs
import json
import os
import secrets
import shutil
import signal
import tempfile
import time
from pathlib import Path

from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app import pty_sessions

router = APIRouter(prefix="/api/terminal")
# WebSocket não manda header Authorization pelo navegador: autentica na 1ª mensagem (fica fora do
# router "private" do server.py, que exige o header).
ws_router = APIRouter()

# Roda o comando no diretório pedido e grava o diretório final num arquivo à parte, para não
# misturar com a saída. Comando e caminhos vão por variáveis de ambiente: nada de aspas a escapar.
SCRIPT = 'cd -- "$TERM_CWD" 2>/dev/null || cd; eval "$TERM_CMD"; __s=$?; pwd > "$TERM_CWD_FILE"; exit $__s'
# Nunca repassados aos comandos.
HIDDEN_ENV = {"APP_API_TOKEN", "APP_SECRET_KEY"}


class RunIn(BaseModel):
    command: str = Field(min_length=1, max_length=20_000)
    cwd: str | None = None


def _shell() -> str:
    return shutil.which("bash") or "/bin/sh"


def _kill(proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is None:
        try:
            os.killpg(proc.pid, signal.SIGKILL)  # o comando e tudo o que ele criou
        except ProcessLookupError:
            pass


def _line(event: dict) -> bytes:
    return (json.dumps(event, ensure_ascii=False) + "\n").encode()


@router.get("")
def info(request: Request):
    s = request.app.state.settings
    if not s.enable_terminal:
        raise HTTPException(404, "Terminal desligado (APP_ENABLE_TERMINAL=0)")
    return {"cwd": str(s.uploads_dir), "shell": _shell(), "timeout_s": s.terminal_timeout_s}


@router.post("/run")
async def run(body: RunIn, request: Request):
    s = request.app.state.settings
    if not s.enable_terminal:
        raise HTTPException(404, "Terminal desligado (APP_ENABLE_TERMINAL=0)")
    s.uploads_dir.mkdir(parents=True, exist_ok=True)
    start_dir = body.cwd if body.cwd and Path(body.cwd).is_dir() else str(s.uploads_dir)

    fd, cwd_file = tempfile.mkstemp(prefix="term-cwd-")
    os.close(fd)
    env = {k: v for k, v in os.environ.items() if k not in HIDDEN_ENV}
    env.update(TERM="dumb", PYTHONUNBUFFERED="1", TERM_CMD=body.command, TERM_CWD=start_dir, TERM_CWD_FILE=cwd_file)

    proc = await asyncio.create_subprocess_exec(
        _shell(), "-c", SCRIPT,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env=env,
        start_new_session=True,  # grupo próprio: dá para matar o comando e seus filhos juntos
    )

    async def stream():
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        deadline = time.monotonic() + s.terminal_timeout_s
        timed_out = False
        try:
            assert proc.stdout is not None
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    timed_out = True
                    break
                try:
                    chunk = await asyncio.wait_for(proc.stdout.read(8192), timeout=remaining)
                except asyncio.TimeoutError:
                    timed_out = True
                    break
                if not chunk:
                    break
                text = decoder.decode(chunk)
                if text:
                    yield _line({"out": text})
            if timed_out:
                _kill(proc)
                yield _line({"out": f"\n[tempo esgotado: {s.terminal_timeout_s}s — comando encerrado]\n"})
            code = await proc.wait()
            tail = decoder.decode(b"", final=True)
            if tail:
                yield _line({"out": tail})
            final_cwd = Path(cwd_file).read_text().strip() or start_dir
            yield _line({"exit": 124 if timed_out else code, "cwd": final_cwd})
        finally:
            _kill(proc)  # cliente desconectou (cancelar) ou erro: não deixa nada rodando
            Path(cwd_file).unlink(missing_ok=True)

    return StreamingResponse(stream(), media_type="application/x-ndjson", headers={"Cache-Control": "no-store"})


def _origin_ok(ws: WebSocket) -> bool:
    """CORS não vale para WebSocket: a origem é conferida aqui (além do token)."""
    origin = ws.headers.get("origin")
    if not origin:
        return True  # cliente que não é navegador
    s = ws.app.state.settings
    return origin in s.cors_origins or urlparse(origin).netloc == ws.headers.get("host", "")


@ws_router.websocket("/api/terminal/ws")
async def terminal_ws(ws: WebSocket):
    s = ws.app.state.settings
    if not _origin_ok(ws):
        await ws.close(code=1008)
        return
    await ws.accept()

    async def fail(message: str) -> None:
        try:
            await ws.send_json({"type": "error", "message": message})
            await ws.close(code=1008)
        except (WebSocketDisconnect, RuntimeError):
            pass  # o cliente já foi embora (ex.: recarregou a página antes de autenticar)

    if not s.enable_terminal:
        return await fail("Terminal desligado no servidor (APP_ENABLE_TERMINAL=0).")
    try:
        hello = await asyncio.wait_for(ws.receive_json(), timeout=10)
    except (asyncio.TimeoutError, WebSocketDisconnect, ValueError):
        return await fail("Esperava a mensagem de autenticação.")
    token = str(hello.get("token", ""))
    if hello.get("type") != "auth" or not secrets.compare_digest(token.encode(), s.api_token.encode()):
        return await fail("Não autenticado.")

    cols, rows = int(hello.get("cols") or 80), int(hello.get("rows") or 24)
    session = pty_sessions.get(hello.get("session"))
    resumed = session is not None
    if session is None:
        s.uploads_dir.mkdir(parents=True, exist_ok=True)
        try:
            session = pty_sessions.create(str(s.uploads_dir), cols, rows)
        except OSError as e:
            return await fail(f"Não consegui abrir um terminal (PTY): {e}")
    else:
        session.resize(cols, rows)

    queue: asyncio.Queue[bytes | None] = asyncio.Queue()
    await ws.send_json({"type": "ready", "session": session.id, "resumed": resumed})
    if resumed and session.scrollback():
        await ws.send_bytes(session.scrollback())  # a tela de antes da reconexão
    session.attach(queue.put_nowait)

    async def pump() -> None:
        while True:
            data = await queue.get()
            buf, ended = bytearray(data or b""), data is None
            while not ended and not queue.empty():  # junta rajadas num frame só
                nxt = queue.get_nowait()
                if nxt is None:
                    ended = True
                else:
                    buf += nxt
            if buf:
                await ws.send_bytes(bytes(buf))
            if ended:
                await ws.send_json({"type": "exit", "code": session.exit_code})
                await ws.close()
                return

    sender = asyncio.create_task(pump())
    try:
        while True:
            msg = await ws.receive_json()
            kind = msg.get("type")
            if kind == "input":
                session.write(str(msg.get("data", "")).encode())
            elif kind == "resize":
                session.resize(int(msg.get("cols") or cols), int(msg.get("rows") or rows))
            elif kind == "close":
                session.kill()
    except (WebSocketDisconnect, RuntimeError, ValueError):
        pass  # conexão caiu: a sessão continua viva para reconectar
    finally:
        session.detach(queue.put_nowait)
        sender.cancel()
