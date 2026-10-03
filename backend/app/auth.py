"""Autenticação por token de dispositivo.

O app Android gera `APP_API_TOKEN` a cada partida do servidor e só o entrega ao front pela ponte do
Capacitor. Outros apps do celular conseguem abrir 127.0.0.1:8001, mas sem o token só veem o
`/api/health`. Para contas de usuário de verdade, troque esta dependência pela sua (JWT etc.): o
resto do servidor só depende de `require_token`.
"""
from __future__ import annotations

import secrets

from fastapi import HTTPException, Request


def require_token(request: Request) -> None:
    header = request.headers.get("authorization", "")
    given = header[7:] if header.lower().startswith("bearer ") else ""
    expected = request.app.state.settings.api_token
    if not secrets.compare_digest(given.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="Não autenticado", headers={"WWW-Authenticate": "Bearer"})
