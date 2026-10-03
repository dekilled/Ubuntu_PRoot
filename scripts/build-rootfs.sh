#!/usr/bin/env bash
# Monta o rootfs Ubuntu 24.04 ARM64 (rootfs/Dockerfile) e grava nos assets do APK:
#   android/app/src/main/assets/rootfs.bin      (docker export da imagem, em tar.gz)
#   android/app/src/main/assets/rootfs.version  (hash do conteúdo; o app reinstala o rootfs quando muda)
# Precisa de docker com buildx; em PCs x86 usa emulação QEMU (docker/setup-qemu-action no CI).
#   WITH_NODE=1 scripts/build-rootfs.sh   inclui Node.js no Ubuntu
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ASSETS="$ROOT/android/app/src/main/assets"
IMAGE="proot-app-rootfs:arm64"

BUILD_ID="${GITHUB_RUN_NUMBER:-local}-$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo dev)"
docker buildx build --platform linux/arm64 --load \
  --build-arg APP_BUILD="$BUILD_ID" --build-arg WITH_NODE="${WITH_NODE:-0}" \
  -t "$IMAGE" -f "$ROOT/rootfs/Dockerfile" "$ROOT"
cid="$(docker create --platform linux/arm64 "$IMAGE")"
trap 'docker rm -f "$cid" >/dev/null' EXIT

mkdir -p "$ASSETS"
docker export "$cid" | gzip -6 > "$ASSETS/rootfs.bin"
sha256sum "$ASSETS/rootfs.bin" | cut -c1-16 > "$ASSETS/rootfs.version"
echo "rootfs: $(du -h "$ASSETS/rootfs.bin" | cut -f1), versão $(cat "$ASSETS/rootfs.version")"
