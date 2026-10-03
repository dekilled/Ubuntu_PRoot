# PRoot App — template

Ponto de partida para apps Android que **rodam um servidor Python dentro do próprio celular**, num
Ubuntu 24.04 completo (via [PRoot](https://github.com/termux/proot), sem root e sem PC), com a
interface em web (React) ligada ao servidor por um **plugin Capacitor**.

Extraído do app LUMNA / [NewHarnessV2](https://github.com/dekilled/NewHarnessV2), só com a
infraestrutura reaproveitável — sem nada específico daquele produto. O mapa do que veio de onde está
em [`docs/EXTRAIDO-DO-NEWHARNESS.md`](docs/EXTRAIDO-DO-NEWHARNESS.md).

```
┌─────────────────────────── APK ────────────────────────────┐
│  WebView (Capacitor)  ──── UI React (assets do APK)        │
│        │  ProotRuntime.getStatus() / evento stateChange    │
│        ▼                                                   │
│  Plugin capacitor-proot-runtime (Kotlin)                   │
│   ├─ RuntimeService   serviço em primeiro plano            │
│   ├─ RootfsExtractor  instala o Ubuntu (assets/rootfs.bin) │
│   └─ libproot.so      PRoot (nativo, da pasta de libs)     │
│        │ proot -r rootfs … /opt/app/entry.sh               │
│        ▼                                                   │
│  Ubuntu 24.04 ARM64 ── uvicorn + FastAPI + SQLite ◄────────┼── HTTP 127.0.0.1:8001
└────────────────────────────────────────────────────────────┘    (Bearer token)
```

## Criar um app novo

1. No GitHub: **Use this template** (ou clone e apague o `.git`).
2. Defina a identidade (id, nome e, opcionalmente, a porta do servidor):
   ```
   npm install
   npm run init -- --id com.suaempresa.meuapp --name "Meu App" --port 8001
   ```
   O `init` só edita `capacitor.config.json` (fonte única de id/nome/porta), o título do front e o
   `package.json`. **Não existe pacote Kotlin para renomear**: o `applicationId` e o nome vêm desse JSON.
3. Desenvolva no PC, sem Android:
   ```
   npm run dev:backend    # servidor Python (porta do capacitor.config.json, recarrega ao salvar)
   npm run dev:web        # front em http://127.0.0.1:5173
   ```
   No navegador o plugin tem um *web fallback*: em vez do PRoot ele usa o servidor que você subiu.
4. Gere o APK — pelo CI (recomendado) ou localmente:
   ```
   npm run android:proot      # baixa o PRoot do Termux (SHA-256 verificado)
   npm run android:rootfs     # monta o Ubuntu ARM64 com o backend (Docker buildx + QEMU em PC x86)
   npm run android:debug      # build do front + cap sync + gradle
   ```
   No GitHub, o workflow **Android APK** faz tudo isso a cada push e deixa o `.apk` em *Artifacts*.
   Requisitos do aparelho: Android 8+ (minSdk 24), ARM64, ~1,5 GB livres.

Na primeira abertura o app instala o Ubuntu (1–3 min, com barra de progresso na UI) e sobe o servidor.

## Base de testes: Terminal e Arquivos

O app de exemplo já vem com duas abas para testar o Ubuntu do celular antes de escrever o seu app:

- **Terminal** — um terminal de verdade: `bash` num PTY (como no Termux), ligado à tela por
  WebSocket e desenhado com [xterm.js](https://xtermjs.org). Programas interativos funcionam:
  `apt install` perguntando "Y/n", `nano`, `python3` (REPL), `top`, `less`, Tab para completar.
  - Barra de **teclas extras** que o teclado do celular não tem: ESC, TAB, CTRL e ALT (tocar uma vez
    = vale para a próxima tecla, ex.: CTRL e depois `c` = Ctrl+C), setas, HOME/END, PGUP/PGDN, `- / | ~`.
  - **A− / A+** (fonte), **Colar**, **📎** (envia arquivo para `~/files`) e **Nova sessão**.
  - A sessão **sobrevive** se a conexão cair (app em segundo plano, trocar de aba, recarregar): ao
    voltar, é o mesmo shell, com a tela restaurada. Sessões sem ninguém conectado morrem em 30 min;
    `exit` encerra na hora.
  - O Ubuntu já vem com `nano`, `less`, `ps`/`top`, `file`, `unzip`, `git`, `curl`. Para instalar mais:
    `apt update` (as listas não vão no APK, para ele ficar menor) e depois `apt install <pacote>`.
- **Arquivos** — gerenciador da pasta de trabalho `/root/files` (onde o terminal começa): navegar
  em pastas, **criar pasta**, **enviar arquivos para a pasta atual** e apagar (pastas inteiras também).
  - No celular, o envio usa o **seletor nativo do Android** e o plugin copia o arquivo direto para
    dentro do Ubuntu (`ProotRuntime.importFiles`) — sem passar pela rede, com progresso, sem limite
    prático de tamanho. No navegador (desenvolvimento), o envio é por HTTP.
  - Nunca sobrescreve (`foto (1).jpg`); nada sai de `/root/files` (nem por `..` nem por symlink).

Código: `backend/app/pty_sessions.py`, `backend/app/routes/terminal.py` e `files.py`;
`frontend/src/Terminal.tsx` e `Files.tsx`. Para um app final que não precisa disso, apague as abas em
`App.tsx` e, no servidor, defina `APP_ENABLE_TERMINAL=0` em `plugins.ProotRuntime.env`.

## O que tem em cada pasta

| Pasta | O que é | Você mexe? |
|---|---|---|
| `backend/` | Servidor FastAPI: `/api/health` público, resto com token; SQLite com migrações; cifra em repouso. Roda igual no PC e no PRoot. | **Sim** — é o seu app |
| `frontend/` | Vite + React + TS consumindo o plugin (tela de instalação/erro, exemplo de API). | **Sim** |
| `capacitor.config.json` | Identidade (`appId`, `appName`) e config do runtime (`plugins.ProotRuntime`). | Raramente |
| `packages/capacitor-proot-runtime/` | **O conector**: API TypeScript + plugin Android (serviço, extractor, PRoot). Documentado no README dele. | Só pra estender |
| `android/` | Projeto Capacitor (casca fina): `MainActivity`, assinatura, empacotamento do PRoot/rootfs. | Raramente |
| `rootfs/` | `Dockerfile` do Ubuntu e `entry.sh` (o que roda dentro do PRoot). | Pra instalar pacotes do sistema |
| `scripts/` | `init`, `dev-backend`, `fetch-proot`, `build-rootfs`, `signing-key`. | Não |
| `.github/workflows/` | CI: testes + APK assinado. | Não |

## Receitas

**Novo endpoint.** Crie `backend/app/routes/algo.py` com um `APIRouter`, registre em
`backend/app/server.py` (`private.include_router(algo.router)` — já vem com a exigência de token) e
um método em `frontend/src/api.ts`. Mude o esquema do banco **acrescentando** um item em
`MIGRATIONS` (`backend/app/db.py`).

**Pacote Python.** Acrescente em `backend/requirements.txt`. Prefira pacotes com wheel `aarch64`
ou puro Python (o rootfs é montado em ARM64, mas compilar C dentro do build é lento).

**Pacote do sistema ou Node.js no Ubuntu.** `apt-get install …` no `rootfs/Dockerfile`; Node:
`WITH_NODE=1 npm run android:rootfs` (e no CI, defina `WITH_NODE` no passo do rootfs).

**Variável de ambiente para o servidor.** `plugins.ProotRuntime.env` no `capacitor.config.json`.
Já existentes: `APP_ENABLE_TERMINAL` (`1`/`0`), `APP_TERMINAL_TIMEOUT` (s), `APP_MAX_UPLOAD_MB`,
`APP_FILES_DIR` (no app: `/root/files`), `CORS_ORIGINS` (extras).

**Novo método nativo** (câmera, biometria, intents…): é só um `@PluginMethod` em
`ProotRuntimePlugin.kt` (ou um plugin Capacitor próprio/oficial) — veja o README do plugin.

**Dados.** O banco e os arquivos vivem em `/root` dentro do PRoot (`/root/data`, `/root/files`),
montado de fora do rootfs: **sobrevivem** quando uma versão nova do app troca o Ubuntu.

## Atualizar o app sem perder os dados (assinatura)

O Android só instala uma versão por cima da outra se a assinatura for a mesma; senão é preciso
desinstalar (e perder os dados). Crie **um secret** no repositório (*Settings → Secrets and variables
→ Actions*): `APP_SIGNING_SEED` = uma frase longa e aleatória (30+ caracteres). **Guarde-a**: perder
a frase = não conseguir mais atualizar o app instalado; quem a tiver consegue assinar atualizações.
O CI deriva dela sempre a mesma chave (`scripts/signing-key.py`) e mostra o SHA-256 do certificado.
Alternativa: um keystore em `APP_KEYSTORE_BASE64` + `APP_KEYSTORE_PASSWORD` + `APP_KEY_ALIAS`.

## Segurança — o modelo

- O servidor escuta **só em 127.0.0.1**, mas qualquer app do celular alcança o loopback. Por isso o
  plugin gera um **token novo a cada partida** (`APP_API_TOKEN`) e só o entrega ao front pela ponte do
  Capacitor; sem ele só o `/api/health` responde. CORS só para as origens do app.
- `APP_SECRET_KEY` (estável por instalação) cifra o que você guardar no banco. Não troque.
- O **terminal executa qualquer comando** (é o propósito): o WebSocket exige o mesmo token (na 1ª
  mensagem, nunca na URL) e confere a origem; os comandos não recebem `APP_API_TOKEN`/`APP_SECRET_KEY`
  no ambiente. Para apps publicados, avalie desligá-lo (`APP_ENABLE_TERMINAL=0`).
- Erros inesperados do servidor voltam como JSON **com** cabeçalho CORS — no WebView aparecem com a
  mensagem real, em vez de um genérico "erro de rede".
- Sem `APP_API_TOKEN` o servidor **recusa subir** (fail-closed); `APP_DEV=1` só nos scripts de dev.
- Tráfego HTTP puro é liberado apenas para `127.0.0.1`/`localhost` (`network_security_config.xml`).
- Para contas de usuário, troque `app/auth.py:require_token` por login/JWT — o resto só depende dessa função.

## Limitações conhecidas

- Só ARM64. O PRoot só *simula* root: os comandos rodam como o próprio app (sem isolamento por usuário).
- O Android pode encerrar o servidor em segundo plano (economia de bateria/memória); a notificação só
  diminui a chance. O plugin expõe `restart()` para a UI oferecer "Tentar de novo".
- O PRoot é GPL-2.0 e o talloc LGPL-3.0: ao distribuir, mantenha o
  [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

Detalhes de funcionamento: [`docs/ARQUITETURA.md`](docs/ARQUITETURA.md).
