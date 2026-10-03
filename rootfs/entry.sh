#!/bin/sh
# Roda DENTRO do PRoot (rootfs Ubuntu). /root é a home persistente do app, montada de fora do
# rootfs: banco e arquivos sobrevivem às atualizações do rootfs. As APP_* (porta, boot id, token,
# chave secreta) vêm do plugin Android como variáveis de ambiente.
set -e
mkdir -p /root/data /root/files
# Home nova (1ª partida): .bashrc/.profile do Ubuntu, para o terminal ter prompt, cores e aliases.
for f in .bashrc .profile; do [ -e "/root/$f" ] || cp "/opt/app/skel/$f" "/root/$f" 2>/dev/null || true; done
export HOME=/root
export PATH=/opt/app/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export LANG=C.UTF-8
export APP_DATA_DIR=/root/data
export APP_FILES_DIR=/root/files  # upload + diretório inicial do terminal
cd /opt/app/backend
exec python -m uvicorn --factory app.server:create_app --host 127.0.0.1 --port "${APP_PORT:-8001}"
