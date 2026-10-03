#!/usr/bin/env bash
# Sobe o servidor Python no PC, igual ao que roda dentro do PRoot (mesmo app.server:create_app).
# O front em modo navegador (npm run dev:web) fala com ele pelo "web fallback" do plugin
# (URL http://127.0.0.1:<porta>, token "dev-token").
#   npm run dev:backend            usa a porta do capacitor.config.json
#   APP_PORT=9000 npm run dev:backend
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"
command -v python3 >/dev/null || { echo "python3 não encontrado (precisa do 3.11+)." >&2; exit 1; }

if [ ! -x "$BACKEND/.venv/bin/uvicorn" ]; then
  echo "[dev] preparando o ambiente Python (primeira vez)..."
  python3 -m venv "$BACKEND/.venv" || { echo "Falha ao criar o venv (Ubuntu/Debian: apt install python3-venv)." >&2; exit 1; }
  "$BACKEND/.venv/bin/pip" install -q -r "$BACKEND/requirements-dev.txt"
fi

PORT_FROM_CONFIG="$(python3 -c "import json;print(json.load(open('$ROOT/capacitor.config.json'))['plugins']['ProotRuntime'].get('port',8001))")"
export APP_PORT="${APP_PORT:-$PORT_FROM_CONFIG}"
export APP_DEV=1
export APP_BOOT_ID="${APP_BOOT_ID:-dev}"
export APP_DATA_DIR="${APP_DATA_DIR:-$BACKEND/data}"

cd "$BACKEND"
echo "[dev] servidor em http://127.0.0.1:$APP_PORT  (token: ${APP_API_TOKEN:-dev-token})"
# --reload-dir: recarrega só quando o código do servidor muda (não quando você cria .py pelo terminal
# em data/files — isso reiniciaria o servidor e mataria as sessões do terminal).
exec .venv/bin/python -m uvicorn --factory app.server:create_app --host 127.0.0.1 --port "$APP_PORT" --reload --reload-dir "$BACKEND/app"
