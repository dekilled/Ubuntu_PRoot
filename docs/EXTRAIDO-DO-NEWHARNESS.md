# O que foi extraído do NewHarnessV2

Mapa do que veio de onde, o que mudou e o que ficou de fora de propósito.

## Mapa

| NewHarnessV2 | Neste template | O que mudou |
|---|---|---|
| `android/app/.../HarnessService.kt` | `packages/capacitor-proot-runtime/android/.../RuntimeService.kt` | Porta/entry/health/timeout/env vêm do `capacitor.config.json`; token novo por partida; saída por `RuntimeState`; sem constantes do Harness |
| `HarnessState.kt` (`HarnessStatus`) | `RuntimeState.kt` | `Ready` carrega a `Connection` (URL + token + boot id); listeners thread-safe |
| `RuntimeLayout` (em `HarnessService.kt`) | `RuntimeLayout.kt` | Igual; sem o log da WebView (o Capacitor usa o logcat) |
| `RootfsExtractor.kt` + teste | `RootfsExtractor.kt` + `RootfsExtractorTest.kt` | Só o pacote mudou |
| `Credentials.kt` (JWT, SECRETS_KEY, senha do admin) | `Secrets.kt` | Sem usuário/senha: `APP_SECRET_KEY` (estável) + `APP_API_TOKEN` (por partida) |
| `MainActivity.kt` (656 linhas: WebView, splash, status, canal `WebMessagePort`) | `MainActivity.java` (3 linhas) + plugin | A WebView, o canal de mensagens e as telas de status/erro passaram a ser do Capacitor + UI web |
| `frontend/src/lib/nativeApp.ts` (ações por string: `"bio-query"`, `tool:{…}`) | `src/definitions.ts` + `src/index.ts` do plugin | Ponte tipada: métodos (`start/stop/restart/getStatus/getLogs`) e evento `stateChange` |
| `android/app/build.gradle.kts`, `AndroidManifest.xml` | `android/app/build.gradle`, plugin `AndroidManifest.xml` | Base Capacitor 8; `applicationId`/nome lidos do `capacitor.config.json`; permissões do serviço moram no plugin |
| `res/xml/network_security_config.xml` | idem | Igual |
| `android/rootfs/{Dockerfile,entry.sh}` | `rootfs/{Dockerfile,entry.sh}` | `/opt/harness` → `/opt/app`; Node opcional (`WITH_NODE`); sem o front dentro do rootfs |
| `android/scripts/{fetch-proot.sh,build-rootfs.sh,signing-key.py}` | `scripts/…` | Mesmos; variáveis `HARNESS_*` → `APP_*` |
| `.github/workflows/android.yml` | idem | Job de checks (pytest + build) antes do APK; Java 21; Node 22 |
| `backend/server.py`, `core.py`, `auth.py`, `docstore.py` | `backend/app/*` | Reescrito enxuto: health+boot id, token, SQLite puro com migrações, cifra Fernet. **Não** carrega chat/LLM/projetos |
| `start.sh` | `scripts/dev-backend.sh` | Só o backend; o front roda com `npm run dev:web` |

## Ficou de fora (é do produto LUMNA, não da base)

Cada item abaixo seria um `@PluginMethod` novo (ou um plugin Capacitor próprio) — o padrão é o mesmo
de `ProotRuntimePlugin.kt`.

| Recurso | Onde está no NewHarnessV2 | Como portar |
|---|---|---|
| Login por digital | `BiometricLogin.kt`, `frontend/src/lib/biometric.ts` | Plugin Capacitor de biometria (ex.: `@aparajita/capacitor-biometric-auth`) ou os 143 linhas de `BiometricLogin.kt` como `@PluginMethod` |
| Voz (STT/TTS) | `VoiceBridge.kt`, `SystemRecognizer.kt`, `lib/voice*.ts` | `@capacitor-community/speech-recognition` + `text-to-speech`, ou portar `VoiceBridge` |
| Assistente digital / painel | `AssistPanel.kt`, `AssistActivity.kt`, `LumnaAssistant.kt`, `LumnaRecognitionService.kt` | Só se o app precisar ser o "assistente padrão"; é nativo puro (manifest + serviços) |
| Ferramentas do aparelho (alarme, brilho, abrir app) | `DeviceTools.kt`, `AppMatcher.kt`, `lib/deviceTools.ts` | `@PluginMethod`s |
| Download via seletor do sistema | `MainActivity.startDownload` | Com UI no APK basta `fetch` + Blob, ou `@capacitor/filesystem` + `@capacitor/share` |
| Câmera/arquivos (`<input type=file capture>`) | `MainActivity.onShowFileChooser`, `CaptureProvider.kt` | O Capacitor já trata `<input type=file>`; `@capacitor/camera` para câmera |
| Splash animada | `assets/splash/` | `@capacitor/splash-screen` ou a própria UI (a tela de instalação é do front) |
| Senha do admin / "esqueci a senha" | `Credentials.kt` + `MainActivity` | Específico de contas locais; use o auth do seu app |
| Chat, LLM, RAG, projetos, terminal, GitHub… | `backend/routes_*.py`, `llm.py`, `tools.py`… | É o produto. `docstore.py` (Mongo-sobre-SQLite) é reaproveitável se você já tem código escrito para Mongo |
