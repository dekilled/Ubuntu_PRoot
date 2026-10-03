# capacitor-proot-runtime

Plugin Capacitor (Android) que instala um **Ubuntu 24.04 ARM64** (PRoot), sobe um servidor dentro
dele num serviço em primeiro plano e entrega à UI **URL + token** para falar com ele.
No navegador (desenvolvimento no PC) há um *web fallback*.

## Uso (front)

```ts
import { watchRuntime, apiFetch } from "capacitor-proot-runtime";

const stop = watchRuntime(async (status) => {
  // status.state: "idle" | "installing" | "starting" | "ready" | "failed"
  if (status.state === "installing") console.log(`${status.progress}%`);
  if (status.state === "failed") console.error(status.message);
  if (status.state === "ready") {
    const res = await apiFetch(status.connection!, "/api/system"); // já com Authorization: Bearer
    console.log(await res.json());
  }
});
```

| API | O que faz |
|---|---|
| `watchRuntime(cb)` | Estado atual + cada mudança; reconsulta ao voltar ao primeiro plano. Retorna o "cancelar". |
| `waitUntilReady(onStatus?, timeoutMs?)` | Promise da `RuntimeConnection` (rejeita em `failed`/timeout). |
| `apiFetch(conn, path, init?)` | `fetch` para `conn.baseUrl + path` com o token. |
| `ProotRuntime.start() / stop() / restart() / getStatus()` | Ciclo de vida. `start` é idempotente. |
| `ProotRuntime.getLogs({lines})` | Fim do log do servidor. |
| `ProotRuntime.importFiles({dir?})` | Seletor de arquivos do Android → cópia direta para `/root/<filesDir>/<dir>` no Ubuntu (sem rede). Resolve com `{files: [{name, size, path}]}`; cancelar = `files: []`. Progresso no evento `importProgress`. Só no app. |
| `ProotRuntime.addListener("stateChange", cb)` | Evento cru. |
| `configureWebFallback({baseUrl, token})` | Navegador: onde está o servidor de dev (padrão `http://127.0.0.1:8001`, `dev-token`). |

Tipos em [`src/definitions.ts`](src/definitions.ts).

## Configuração

`capacitor.config.json` → `plugins.ProotRuntime` (o `cap sync` copia para os assets; o serviço lê de lá):

| Chave | Padrão | |
|---|---|---|
| `port` | `8001` | Porta do servidor em 127.0.0.1 |
| `entry` | `/opt/app/entry.sh` | Script dentro do rootfs que dá `exec` no servidor |
| `healthPath` | `/api/health` | Precisa devolver 200 + `{"boot": "<APP_BOOT_ID>"}` |
| `startupTimeoutMs` | `180000` | Tempo para o servidor responder |
| `autoStart` | `true` | Sobe o runtime ao carregar o plugin |
| `requestNotificationPermission` | `true` | Pede POST_NOTIFICATIONS (Android 13+) |
| `env` | `{}` | Variáveis extras para o servidor |
| `filesDir` | `files` | Pasta (relativa a `/root`) onde `importFiles` grava; casa com `APP_FILES_DIR` do `entry.sh` |

## Contrato com o servidor

O serviço roda `proot … /bin/sh <entry>` com estas variáveis:

| Variável | |
|---|---|
| `APP_PORT` | Porta em que escutar (127.0.0.1) |
| `APP_BOOT_ID` | Devolver no `healthPath` (`{"boot": …}`): prova que é este processo |
| `APP_API_TOKEN` | Exigir `Authorization: Bearer <token>` (novo a cada partida) |
| `APP_SECRET_KEY` | Segredo estável por instalação (cifrar dados em repouso) |

O rootfs vem de `assets/rootfs.bin` + `assets/rootfs.version` (gerados por `scripts/build-rootfs.sh`)
e o PRoot de `jniLibs/arm64-v8a` (`scripts/fetch-proot.sh`). `/root` do Ubuntu é o diretório
persistente `files/runtime/home`.

## Estender o lado nativo

Adicione um método em `android/src/main/kotlin/dev/prootkit/runtime/ProotRuntimePlugin.kt`:

```kotlin
@PluginMethod
fun vibrate(call: PluginCall) { /* … */ call.resolve() }
```

e declare-o em `ProotRuntimePlugin` (`src/definitions.ts`). Para recursos grandes, prefira um plugin
Capacitor separado (oficial/comunidade) em vez de inchar este.
