import { registerPlugin } from "@capacitor/core";

import type { ProotRuntimePlugin, RuntimeConnection, RuntimeStatus } from "./definitions";

export * from "./definitions";
export { configureWebFallback } from "./web";
export type { WebFallbackConfig } from "./web";

/** O plugin cru. Prefira os helpers abaixo na maior parte dos casos. */
export const ProotRuntime = registerPlugin<ProotRuntimePlugin>("ProotRuntime", {
  web: () => import("./web").then((m) => new m.ProotRuntimeWeb()),
});

/**
 * Observa o runtime: entrega o estado atual na hora e cada mudança depois.
 * Também reconsulta ao voltar para o app (a WebView pausada pode perder eventos).
 * Retorna a função que cancela a observação.
 */
export const watchRuntime = (onStatus: (status: RuntimeStatus) => void): (() => void) => {
  let active = true;
  let handle: { remove: () => Promise<void> } | undefined;
  const refresh = () => ProotRuntime.getStatus().then((s) => active && onStatus(s), () => {});
  const onVisible = () => document.visibilityState === "visible" && refresh();

  ProotRuntime.addListener("stateChange", (s) => active && onStatus(s)).then((h) => {
    if (active) handle = h;
    else h.remove();
  });
  document.addEventListener("visibilitychange", onVisible);
  refresh();

  return () => {
    active = false;
    document.removeEventListener("visibilitychange", onVisible);
    handle?.remove();
  };
};

/** Espera o servidor ficar pronto (ou falhar). Útil fora de componentes. */
export const waitUntilReady = (
  onStatus?: (status: RuntimeStatus) => void,
  timeoutMs = 5 * 60_000,
): Promise<RuntimeConnection> =>
  new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      stop();
      reject(new Error("O servidor não ficou pronto a tempo."));
    }, timeoutMs);
    const stop = watchRuntime((s) => {
      onStatus?.(s);
      if (s.state === "ready" && s.connection) {
        clearTimeout(timer);
        stop();
        resolve(s.connection);
      } else if (s.state === "failed") {
        clearTimeout(timer);
        stop();
        reject(new Error(s.message ?? "O servidor falhou ao iniciar."));
      }
    });
  });

/** `fetch` já apontado para o servidor, com o token. `path` começa com `/`. */
export const apiFetch = (conn: RuntimeConnection, path: string, init: RequestInit = {}) => {
  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${conn.token}`);
  return fetch(`${conn.baseUrl}${path}`, { ...init, headers });
};
