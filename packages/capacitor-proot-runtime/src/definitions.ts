/**
 * Contrato entre o front (Capacitor/WebView) e o runtime Linux do app.
 *
 * Fluxo: o plugin instala o Ubuntu (1ª vez), sobe o servidor dentro do PRoot e só então
 * publica `state: "ready"` com a `connection` (URL + token). O front fala HTTP direto com o
 * servidor; o plugin só cuida do ciclo de vida e da credencial.
 */

export type RuntimeStateName = "idle" | "installing" | "starting" | "ready" | "failed";

/** Como falar com o servidor. Só existe quando `state === "ready"`. */
export interface RuntimeConnection {
  /** Ex.: `http://127.0.0.1:8001` (sem barra no final). */
  baseUrl: string;
  /** Mandar em todo request: `Authorization: Bearer <token>`. Muda a cada partida do servidor. */
  token: string;
  /** Identifica esta partida; o servidor devolve o mesmo valor em `/api/health`. */
  bootId: string;
  port: number;
}

export interface RuntimeStatus {
  state: RuntimeStateName;
  /** 0–100, apenas em `installing`. */
  progress?: number;
  /** Motivo (com o fim do log), apenas em `failed`. */
  message?: string;
  /** Apenas em `ready`. */
  connection?: RuntimeConnection;
}

export interface ProotRuntimePlugin {
  /** Sobe o runtime (idempotente). Com `autoStart` (padrão) o plugin já faz isso ao carregar. */
  start(): Promise<RuntimeStatus>;
  /** Para o servidor e o serviço em primeiro plano. */
  stop(): Promise<void>;
  /** Para e sobe de novo o servidor (ex.: depois de `failed`). */
  restart(): Promise<RuntimeStatus>;
  /** Estado atual, sem esperar. */
  getStatus(): Promise<RuntimeStatus>;
  /** Final do log do servidor Python (stdout/stderr do PRoot). */
  getLogs(options?: { lines?: number }): Promise<{ backend: string }>;
  /** Mudanças de estado (instalação, pronto, falha…). */
  addListener(
    eventName: "stateChange",
    listener: (status: RuntimeStatus) => void,
  ): Promise<{ remove: () => Promise<void> }>;
  removeAllListeners(): Promise<void>;
}
