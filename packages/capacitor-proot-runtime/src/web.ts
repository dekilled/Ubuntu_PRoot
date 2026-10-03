import { WebPlugin } from "@capacitor/core";

import type { ProotRuntimePlugin, RuntimeConnection, RuntimeStatus } from "./definitions";

/** Onde o servidor roda quando o app abre num navegador comum (desenvolvimento no PC). */
export interface WebFallbackConfig {
  baseUrl: string;
  token: string;
}

const config: WebFallbackConfig = { baseUrl: "http://127.0.0.1:8001", token: "dev-token" };

/**
 * No navegador não há PRoot: o "runtime" é o servidor que você subiu na mão
 * (`npm run dev:backend`). Ajuste a URL/token com `configureWebFallback()` se precisar.
 */
export const configureWebFallback = (next: Partial<WebFallbackConfig>) => {
  Object.assign(config, next);
};

export class ProotRuntimeWeb extends WebPlugin implements ProotRuntimePlugin {
  private async probe(): Promise<RuntimeStatus> {
    const { baseUrl, token } = config;
    try {
      const res = await fetch(`${baseUrl}/api/health`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const { boot = "dev", port } = (await res.json()) as { boot?: string; port?: number };
      const connection: RuntimeConnection = {
        baseUrl,
        token,
        bootId: boot,
        port: port ?? Number(new URL(baseUrl).port || 80),
      };
      return { state: "ready", connection };
    } catch (e) {
      return {
        state: "failed",
        message: `Servidor de desenvolvimento não respondeu em ${baseUrl} (${String(e)}). Rode: npm run dev:backend`,
      };
    }
  }

  private async publish(): Promise<RuntimeStatus> {
    const status = await this.probe();
    this.notifyListeners("stateChange", status);
    return status;
  }

  start = () => this.publish();
  restart = () => this.publish();
  getStatus = () => this.probe();
  async stop() {}
  async importFiles(): Promise<{ files: never[] }> {
    throw this.unavailable("importFiles só existe no app Android; no navegador envie por HTTP (POST /api/files).");
  }
  async getLogs() {
    return { backend: "(no navegador os logs ficam no terminal do dev:backend)" };
  }
}
