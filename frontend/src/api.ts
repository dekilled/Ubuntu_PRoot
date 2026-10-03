import { apiFetch, type RuntimeConnection } from "capacitor-proot-runtime";

export interface SystemInfo {
  os: string;
  machine: string;
  python: string;
  pid: number;
  uptime_s: number;
  data_dir: string;
}
export interface Note {
  id: number;
  text: string;
  created_at: string;
}

/** Cliente da API do servidor Python. Acrescente aqui um método por endpoint novo. */
export const createApi = (conn: RuntimeConnection) => {
  const json = async <T>(path: string, init?: RequestInit): Promise<T> => {
    const res = await apiFetch(conn, path, init);
    if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`);
    return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
  };
  const body = (data: unknown): RequestInit => ({
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });

  return {
    system: () => json<SystemInfo>("/api/system"),
    notes: () => json<Note[]>("/api/notes"),
    addNote: (text: string) => json<Note>("/api/notes", body({ text })),
    deleteNote: (id: number) => json<void>(`/api/notes/${id}`, { method: "DELETE" }),
  };
};
export type Api = ReturnType<typeof createApi>;

// ---- Base de testes: terminal e arquivos (backend/app/routes/terminal.py e files.py) ----

export interface FileEntry {
  name: string;
  size: number;
  is_dir: boolean;
  modified: string;
}
export interface DirListing {
  root: string;
  /** Relativo à pasta de arquivos ("" = raiz). */
  path: string;
  /** Caminho absoluto dentro do Ubuntu. */
  abs: string;
  files: FileEntry[];
}

export const createFilesApi = (conn: RuntimeConnection) => {
  const call = async <T>(path: string, init?: RequestInit): Promise<T> => {
    const res = await apiFetch(conn, path, init);
    if (!res.ok) {
      const detail = await res.json().then((b) => b.detail, () => res.statusText);
      throw new Error(typeof detail === "string" ? detail : `HTTP ${res.status}`);
    }
    return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
  };
  const q = (path: string) => `?path=${encodeURIComponent(path)}`;
  return {
    list: (path = "") => call<DirListing>(`/api/files${q(path)}`),
    mkdir: (path: string, name: string) =>
      call<{ path: string }>("/api/files/mkdir", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path, name }),
      }),
    remove: (path: string) => call<void>(`/api/files${q(path)}`, { method: "DELETE" }),
    /** Upload por HTTP (navegador). No app Android use ProotRuntime.importFiles (nativo, sem rede). */
    upload: (files: File[], path = "", onProgress?: (fraction: number) => void) =>
      new Promise<{ saved: { name: string; size: number; path: string }[] }>((resolve, reject) => {
        const form = new FormData();
        files.forEach((f) => form.append("files", f, f.name));
        const xhr = new XMLHttpRequest();
        xhr.open("POST", `${conn.baseUrl}/api/files${q(path)}`);
        xhr.setRequestHeader("Authorization", `Bearer ${conn.token}`);
        xhr.upload.onprogress = (e) => e.lengthComputable && onProgress?.(e.loaded / e.total);
        xhr.onload = () => {
          if (xhr.status === 201) return resolve(JSON.parse(xhr.responseText));
          let detail = xhr.responseText;
          try {
            detail = JSON.parse(xhr.responseText).detail;
          } catch {
            /* resposta não-JSON */
          }
          reject(new Error(`upload: HTTP ${xhr.status} ${detail}`));
        };
        xhr.onerror = () => reject(new Error("upload: falha de rede (o servidor caiu ou recusou a conexão)"));
        xhr.send(form);
      }),
  };
};

/** Conexão WebSocket com um shell (PTY) no Ubuntu. Reconecta sozinha e retoma a mesma sessão. */
export interface ShellCallbacks {
  onOutput: (data: Uint8Array) => void;
  onStatus: (status: "connecting" | "ready" | "reconnecting" | "exited" | "error", detail?: string) => void;
}

const SESSION_KEY = "terminal.session";

export const openShell = (conn: RuntimeConnection, size: () => { cols: number; rows: number }, cb: ShellCallbacks) => {
  let ws: WebSocket | null = null;
  let closedByUser = false;
  let exited = false;
  let retry = 0;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const store = {
    get: () => {
      try {
        return sessionStorage.getItem(SESSION_KEY);
      } catch {
        return null;
      }
    },
    set: (v: string | null) => {
      try {
        if (v) sessionStorage.setItem(SESSION_KEY, v);
        else sessionStorage.removeItem(SESSION_KEY);
      } catch {
        /* sem armazenamento: só não retoma após recarregar a página */
      }
    },
  };

  const connect = () => {
    cb.onStatus(retry ? "reconnecting" : "connecting");
    const sock = new WebSocket(`${conn.baseUrl.replace(/^http/, "ws")}/api/terminal/ws`);
    sock.binaryType = "arraybuffer";
    ws = sock;
    sock.onopen = () => sock.send(JSON.stringify({ type: "auth", token: conn.token, session: store.get(), ...size() }));
    sock.onmessage = (e) => {
      if (typeof e.data !== "string") return cb.onOutput(new Uint8Array(e.data as ArrayBuffer));
      const msg = JSON.parse(e.data);
      if (msg.type === "ready") {
        retry = 0;
        store.set(msg.session);
        cb.onStatus("ready", msg.resumed ? "resumed" : "new");
      } else if (msg.type === "exit") {
        exited = true;
        store.set(null);
        cb.onStatus("exited", String(msg.code));
      } else if (msg.type === "error") {
        exited = true;
        cb.onStatus("error", msg.message);
      }
    };
    sock.onclose = () => {
      if (closedByUser || exited) return;
      retry += 1;
      timer = setTimeout(connect, Math.min(5000, 300 * 2 ** retry)); // app voltou do segundo plano, etc.
    };
  };
  connect();

  const send = (msg: object) => ws?.readyState === WebSocket.OPEN && ws.send(JSON.stringify(msg));
  return {
    input: (data: string) => send({ type: "input", data }),
    resize: () => send({ type: "resize", ...size() }),
    /** Reabre a conexão já (ex.: app voltou ao primeiro plano). */
    wake: () => {
      if (!closedByUser && !exited && ws?.readyState !== WebSocket.OPEN && ws?.readyState !== WebSocket.CONNECTING) {
        clearTimeout(timer);
        connect();
      }
    },
    /** Encerra o shell no servidor. */
    kill: () => {
      send({ type: "close" });
      store.set(null);
    },
    /** Só desconecta (o shell continua vivo para reconectar). */
    dispose: () => {
      closedByUser = true;
      clearTimeout(timer);
      ws?.close();
    },
  };
};
