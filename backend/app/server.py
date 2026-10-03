"""Servidor FastAPI do app.

    uvicorn --factory app.server:create_app --host 127.0.0.1 --port 8001

Para criar um recurso novo: um arquivo em `app/routes/` com um `APIRouter`, e um
`include_router(..., dependencies=[Depends(require_token)])` aqui embaixo.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from app import pty_sessions
from app.auth import require_token
from app.config import Settings, load_settings
from app.crypto import SecretBox
from app.db import Database
from app.routes import files, health, notes, system, terminal

log = logging.getLogger("app")


class ErrorsAsJson:
    """Erro inesperado → 500 em JSON com a mensagem (e passando pelo CORS); o traceback vai pro log."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        started = False

        async def tracking_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, tracking_send)
        except Exception as e:
            log.exception("erro em %s %s", scope.get("method"), scope.get("path"))
            if started:
                raise
            await JSONResponse({"detail": f"Erro interno: {type(e).__name__}: {e}"}, status_code=500)(scope, receive, send)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        version = app.state.db.migrate()
        log.info("pronto em 127.0.0.1:%s (esquema v%s, dados em %s)", settings.port, version, settings.data_dir)
        yield
        pty_sessions.kill_all()

    app = FastAPI(title="App", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.settings = settings
    app.state.db = Database(settings.db_path)
    app.state.secrets = SecretBox(settings.secret_key)

    # Ordem importa: o último adicionado fica por fora. ErrorsAsJson fica DENTRO do CORS, então até
    # um erro 500 sai com cabeçalho CORS — sem isso o WebView só mostra "erro de rede".
    app.add_middleware(ErrorsAsJson)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,  # autenticação é por header Authorization, nunca por cookie
        allow_methods=["*"],
        allow_headers=["Authorization", "Content-Type"],
    )

    app.include_router(health.router)  # público
    app.include_router(terminal.ws_router)  # WebSocket: autentica na 1ª mensagem
    private = APIRouter(dependencies=[Depends(require_token)])
    private.include_router(system.router)
    private.include_router(notes.router)
    private.include_router(terminal.router)
    private.include_router(files.router)
    app.include_router(private)

    dist = settings.frontend_dist
    if dist and (dist / "index.html").is_file():
        # Opcional: serve o front compilado (útil para abrir no navegador do PC/Termux). No APK
        # a UI vem dos assets do Capacitor e isto não é usado. Registrado por último: /api/* vence.
        @app.get("/{path:path}", include_in_schema=False)
        def frontend(path: str):
            if path == "api" or path.startswith("api/"):
                return JSONResponse({"detail": "Not Found"}, status_code=404)
            target = (dist / path).resolve()
            if path and target.is_file() and dist in target.parents:
                return FileResponse(target)
            return FileResponse(dist / "index.html", headers={"Cache-Control": "no-cache"})

    return app
