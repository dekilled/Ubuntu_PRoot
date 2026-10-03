"""Terminal da base de testes: roda um comando de shell no Ubuntu (dentro do PRoot, no app) e
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
import shutil
import signal
import tempfile
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/terminal")

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
