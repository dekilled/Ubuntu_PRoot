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

/** Arquivo copiado para dentro do Ubuntu por `importFiles`. */
export interface ImportedFile {
  name: string;
  size: number;
  /** Caminho visto de dentro do Ubuntu, ex.: `/root/files/foto.jpg`. */
  path: string;
}

export interface ImportProgress {
  name: string;
  /** Posição do arquivo atual (0…count-1). */
  index: number;
  count: number;
  loaded: number;
  /** -1 quando o Android não informa o tamanho. */
  total: number;
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
  /**
   * Abre o seletor de arquivos do Android e copia os escolhidos direto para a pasta de trabalho do
   * Ubuntu (`/root/<filesDir>/<dir>`; `filesDir` padrão "files"), sem passar pela rede.
   * Cancelar resolve com `files: []`. Só no app (no navegador: indisponível — use HTTP).
   */
  importFiles(options?: { dir?: string }): Promise<{ files: ImportedFile[] }>;
  /** Mudanças de estado (instalação, pronto, falha…). */
  addListener(
    eventName: "stateChange",
    listener: (status: RuntimeStatus) => void,
  ): Promise<{ remove: () => Promise<void> }>;
  addListener(
    eventName: "importProgress",
    listener: (progress: ImportProgress) => void,
  ): Promise<{ remove: () => Promise<void> }>;
  removeAllListeners(): Promise<void>;
}
