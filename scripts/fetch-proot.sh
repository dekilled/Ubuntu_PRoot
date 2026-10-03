#!/usr/bin/env bash
# Downloads PRoot (and the libraries it links against) from the Termux aarch64 repository and
# installs them as android/app/src/main/jniLibs/arm64-v8a/lib*.so.
#
# Android 10+ forbids exec() of files in the app's data dir, but files shipped in the APK's native
# library dir can be executed. The .so names are what the packager requires; the app symlinks the
# original sonames (libtalloc.so.2 …) to them at runtime.
#
# PRoot is GPL-2.0: see THIRD_PARTY_NOTICES.md for the source location.
set -euo pipefail

REPO="${TERMUX_REPO:-https://packages.termux.dev/apt/termux-main}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$HERE/android/app/src/main/jniLibs/arm64-v8a"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

curl -fsSL "$REPO/dists/stable/main/binary-aarch64/Packages" -o "$WORK/Packages"

fetch() { # fetch <package>: downloads, checks SHA-256 and extracts the .deb into $WORK/root
  local pkg="$1" filename sha
  filename="$(awk -v p="$pkg" '$0=="Package: "p{f=1} f&&/^Filename:/{print $2; exit}' "$WORK/Packages")"
  sha="$(awk -v p="$pkg" '$0=="Package: "p{f=1} f&&/^SHA256:/{print $2; exit}' "$WORK/Packages")"
  [ -n "$filename" ] && [ -n "$sha" ] || { echo "Pacote $pkg não encontrado em $REPO" >&2; exit 1; }
  curl -fsSL "$REPO/$filename" -o "$WORK/$pkg.deb"
  echo "$sha  $WORK/$pkg.deb" | sha256sum -c --quiet
  mkdir -p "$WORK/root"
  (cd "$WORK" && ar x "$pkg.deb" && tar -xf data.tar.* -C root && rm -f data.tar.* control.tar.* debian-binary)
  echo "$pkg: $(basename "$filename")"
}

fetch proot
fetch libtalloc
fetch libandroid-shmem

PREFIX="$WORK/root/data/data/com.termux/files/usr"
mkdir -p "$OUT"
rm -f "$OUT"/lib*.so
install -m 755 "$PREFIX/bin/proot" "$OUT/libproot.so"
install -m 755 "$PREFIX/libexec/proot/loader" "$OUT/libproot-loader.so"
install -m 644 "$(readlink -f "$PREFIX/lib/libtalloc.so.2")" "$OUT/libtalloc.so"
install -m 644 "$PREFIX/lib/libandroid-shmem.so" "$OUT/libandroid-shmem.so"
ls -l "$OUT"
