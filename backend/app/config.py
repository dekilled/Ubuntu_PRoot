"""Configuração do servidor, toda por variáveis de ambiente.

No app Android quem define as `APP_*` é o plugin `capacitor-proot-runtime` (ver
`packages/capacitor-proot-runtime/android/.../RuntimeService.kt`); no PC, `scripts/dev-backend.sh`.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

# Origens do front: o Capacitor serve a UI em http://localhost (androidScheme "http"); as demais
# são o Vite em desenvolvimento. Somente estas — sem "*" — e o acesso exige token de qualquer forma.
DEFAULT_CORS = (
    "http://localhost",
    "https://localhost",
    "capacitor://localhost",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)


@dataclass(frozen=True)
class Settings:
    port: int
    boot_id: str
    api_token: str
    secret_key: str
    data_dir: Path
    cors_origins: tuple[str, ...]
    frontend_dist: Path | None
    # Base de testes: terminal (comandos no Ubuntu) e upload de arquivos. Ver app/routes/terminal.py.
    files_dir: Path | None = None  # padrão: <data_dir>/files
    enable_terminal: bool = True
    terminal_timeout_s: int = 600
    max_upload_mb: int = 1024

    @property
    def db_path(self) -> Path:
        return self.data_dir / "app.db"

    @property
    def uploads_dir(self) -> Path:
        return self.files_dir or self.data_dir / "files"


def load_settings(env: Mapping[str, str] = os.environ) -> Settings:
    token = env.get("APP_API_TOKEN", "")
    secret = env.get("APP_SECRET_KEY", "")
    if env.get("APP_DEV") == "1":
        token = token or "dev-token"
        secret = secret or "dev-secret-key-not-for-production"
    if len(token) < 8 or len(secret) < 8:
        raise RuntimeError(
            "APP_API_TOKEN e APP_SECRET_KEY são obrigatórios (o app Android os define). "
            "No PC, rode com APP_DEV=1 (scripts/dev-backend.sh já faz isso)."
        )
    extra = tuple(o.strip() for o in env.get("CORS_ORIGINS", "").split(",") if o.strip() and o.strip() != "*")
    dist = env.get("FRONTEND_DIST")
    files = env.get("APP_FILES_DIR")
    return Settings(
        port=int(env.get("APP_PORT", "8001")),
        boot_id=env.get("APP_BOOT_ID", ""),
        api_token=token,
        secret_key=secret,
        data_dir=Path(env.get("APP_DATA_DIR", "data")).resolve(),
        cors_origins=DEFAULT_CORS + extra,
        frontend_dist=Path(dist).resolve() if dist else None,
        files_dir=Path(files).resolve() if files else None,
        enable_terminal=env.get("APP_ENABLE_TERMINAL", "1") != "0",
        terminal_timeout_s=int(env.get("APP_TERMINAL_TIMEOUT", "600")),
        max_upload_mb=int(env.get("APP_MAX_UPLOAD_MB", "1024")),
    )
