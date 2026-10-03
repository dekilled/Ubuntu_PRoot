# Componentes de terceiros empacotados no APK

| Componente | Origem | Licença | Código-fonte |
|---|---|---|---|
| PRoot (`libproot.so`, `libproot-loader.so`) | pacote `proot` do Termux (aarch64) | GPL-2.0-or-later | https://github.com/termux/proot |
| talloc (`libtalloc.so`) | pacote `libtalloc` do Termux | LGPL-3.0-or-later | https://talloc.samba.org / https://github.com/termux/termux-packages |
| libandroid-shmem (`libandroid-shmem.so`) | pacote `libandroid-shmem` do Termux | BSD-3-Clause | https://github.com/termux/libandroid-shmem |
| Ubuntu 24.04 (`assets/rootfs.bin`) | imagem `ubuntu:24.04` (arm64) + pacotes apt | licenças de cada pacote (`/usr/share/doc/*/copyright`, mantidos no rootfs) | https://ubuntu.com, `apt-get source <pacote>` |
| Node.js (`/usr/local` no rootfs, só com `WITH_NODE=1`) | build oficial linux-arm64 de nodejs.org (SHA-256 conferido) | MIT + licenças incluídas (`/usr/local/LICENSE`) | https://github.com/nodejs/node |
| Dependências Python do servidor | PyPI (`backend/requirements.txt`) | licenças de cada pacote | https://pypi.org |
| Capacitor | npm / Maven Central | MIT | https://github.com/ionic-team/capacitor |
| Apache Commons Compress | Maven Central | Apache-2.0 | https://commons.apache.org/proper/commons-compress/ |

Os binários do Termux são baixados por `scripts/fetch-proot.sh`, que verifica o SHA-256 publicado no
índice do repositório. As versões usadas em cada build aparecem no log do CI.

Ao distribuir um app feito com este template, mantenha este arquivo (ou equivalente) e ofereça o
código-fonte das partes GPL/LGPL, como acima.
