# Arquitetura

## Linha do tempo de uma abertura

```
MainActivity (Capacitor)  carrega a UI de assets/public  (http://localhost)
  └─ ProotRuntimePlugin.load()
       ├─ pede POST_NOTIFICATIONS (Android 13+) se configurado
       └─ RuntimeService.start()  → startForegroundService
RuntimeService.runRuntime()  (thread "proot-runtime")
  1. installRootfsIfNeeded   assets/rootfs.version ≠ instalado?  → RootfsExtractor (progresso 0–99 %)
                              extrai em rootfs.new/ e troca por rootfs/ (home/ não é tocada)
  2. clearLeftovers          mata processos antigos do app (proot/python) e espera a porta liberar
  3. launchServer            libproot.so … /bin/sh /opt/app/entry.sh   (APP_PORT, APP_BOOT_ID,
                              APP_API_TOKEN novo, APP_SECRET_KEY estável)
  4. waitUntilHealthy        GET /api/health até o "boot" devolvido == APP_BOOT_ID  (timeout 180 s)
  5. RuntimeStatus.set(Ready(connection))  →  evento "stateChange" na UI
UI (watchRuntime)  recebe {state:"ready", connection:{baseUrl, token,…}} e passa a chamar a API
```

Estados: `idle → installing(0–99) → starting → ready` ou `failed(message)` (a mensagem inclui o fim do
log). Se o processo do servidor morrer depois de `ready`, o estado vira `failed` com o código de saída.

## Por que a UI mora no APK (e não é servida pelo Python)

O NewHarnessV2 servia o front pelo próprio backend e usava uma tela nativa de status. Aqui a UI vem
dos assets do Capacitor (`http://localhost`, `androidScheme: "http"`):

- abre na hora, mesmo enquanto o Ubuntu instala; a UI desenha a barra de progresso e os erros;
- a ponte do Capacitor funciona na origem local normal (nada de injetar JS em página remota);
- atualizar a UI não obriga a reinstalar o rootfs (o hash do rootfs só muda quando o backend muda);
- sem cookies: a autenticação é `Authorization: Bearer`, então CORS fica estrito e simples.

O backend ainda sabe servir um front compilado (`FRONTEND_DIST=/caminho/dist`) — útil para abrir o
app no navegador do PC/Termux. No APK isso não é usado.

## Por que o token é por partida

`127.0.0.1` é acessível por qualquer app do aparelho. Um token estático no APK seria extraível; um
token gerado a cada partida só existe na memória do serviço e na página que recebeu a `connection`
pela ponte. Se o servidor reiniciar, a UI recebe `stateChange` com a conexão nova
(`watchRuntime` também reconsulta ao voltar ao primeiro plano).

## Pontos delicados herdados do NewHarnessV2 (não remova sem entender)

- **PRoot e loader precisam estar na pasta de libs nativas** (`jniLibs/arm64-v8a/lib*.so`) com
  `useLegacyPackaging = true`: o Android 10+ não deixa dar `exec()` em arquivos de `/data/data`.
- **`libtalloc.so.2`**: o proot é linkado a esse soname; o APK só entrega `libtalloc.so`, então o
  serviço cria um symlink em `runtime/lib` antes de lançar.
- **`rootfs.bin` (não `.gz`)** e `noCompress "bin"`: o empacotador descompactaria/renomearia um `.gz`;
  sem `noCompress` o tamanho (barra de progresso) e o streaming se perdem.
- **`RootfsExtractor`**: rejeita `..`/caminhos absolutos, nunca escreve através de symlink (o rootfs
  tem symlinks absolutos que só fazem sentido dentro do PRoot), troca hardlinks por cópias, ignora
  device nodes. Tem testes de JVM (`./gradlew testDebugUnitTest`).
- **`--link2symlink`** no PRoot: o armazenamento do app não aceita hardlinks.
- **`APP_BOOT_ID`**: sem ele, um servidor antigo ainda vivo na porta passaria no health check.
- **`/etc/hosts`** reescrito: "localhost" precisa ser 127.0.0.1 (servidores de dev e clientes IPv4).
- **Dados fora do rootfs** (`runtime/home` → `/root`): é o que permite trocar o Ubuntu sem perder nada.

## Contrato do plugin

Ver [`packages/capacitor-proot-runtime/README.md`](../packages/capacitor-proot-runtime/README.md).
