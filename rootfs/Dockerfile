# Root filesystem Ubuntu 24.04 ARM64 do app Android: Python + servidor (backend/) numa venv.
# Montado por scripts/build-rootfs.sh (o `docker export` desta imagem vira o rootfs.bin do APK).
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 python3-venv git ca-certificates curl xz-utils \
      nano less procps file unzip bash-completion \
 && apt-get clean && rm -rf /var/lib/apt/lists/* /var/cache/apt/* /usr/share/man/* \
 && find /usr/share/doc -type f ! -name copyright -delete

# apt dentro do PRoot: o root é simulado, então o apt não consegue trocar para o usuário _apt
# (o "sandbox" dele). Sem isto, `apt install` no terminal do app falha com erro de permissão.
# As listas de pacotes foram apagadas para o APK ficar menor: rode `apt update` antes do 1º install.
RUN echo 'APT::Sandbox::User "root";' > /etc/apt/apt.conf.d/99proot

# /root é montado de fora do rootfs (home persistente do app) e começa vazio: estes arquivos de
# shell são copiados para lá na 1ª partida (entry.sh), sem sobrescrever os que você editar.
RUN mkdir -p /opt/app/skel && cp /etc/skel/.bashrc /etc/skel/.profile /opt/app/skel/ \
 && sed -i 's/^#force_color_prompt=yes/force_color_prompt=yes/' /opt/app/skel/.bashrc

# Node.js LTS opcional (WITH_NODE=1): útil se o app roda ferramentas JS dentro do Ubuntu.
# Build oficial do nodejs.org, com SHA-256 conferido.
ARG WITH_NODE=0
ARG NODE_MAJOR=22
RUN if [ "$WITH_NODE" = "1" ]; then set -e; base="https://nodejs.org/dist/latest-v${NODE_MAJOR}.x"; \
    sums="$(curl -fsSL "$base/SHASUMS256.txt")"; \
    file="$(printf '%s\n' "$sums" | awk '$2 ~ /-linux-arm64\.tar\.xz$/ {print $2}')"; \
    curl -fsSLO "$base/$file"; \
    printf '%s\n' "$sums" | grep " $file\$" | sha256sum -c -; \
    tar -xJf "$file" -C /usr/local --strip-components=1 --no-same-owner; rm "$file"; \
    rm -rf /usr/local/include /usr/local/share/doc /usr/local/share/man /usr/local/CHANGELOG.md /usr/local/README.md; \
    node --version && npm --version; fi

# Dependências antes do código: o cache do Docker só refaz esta camada se o requirements mudar.
COPY backend/requirements.txt /opt/app/backend/requirements.txt
RUN python3 -m venv /opt/app/venv \
 && /opt/app/venv/bin/pip install --no-cache-dir -r /opt/app/backend/requirements.txt \
 && find /opt/app/venv -name '__pycache__' -prune -exec rm -rf {} +

COPY backend/ /opt/app/backend/
COPY rootfs/entry.sh /opt/app/entry.sh
# Qual build é este (aparece em /opt/app/BUILD).
ARG APP_BUILD=dev
RUN echo "$APP_BUILD" > /opt/app/BUILD
RUN chmod 755 /opt/app/entry.sh \
 && rm -rf /opt/app/backend/tests /opt/app/backend/.env /opt/app/backend/data /opt/app/backend/.venv /opt/app/backend/.pytest_cache
