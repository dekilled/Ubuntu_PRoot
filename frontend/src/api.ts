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

export type TerminalEvent = { out: string } | { exit: number; cwd: string };

/** Roda um comando no Ubuntu e entrega a saída aos pedaços. Aborte com `signal` para matar o comando. */
export const runCommand = async (
  conn: RuntimeConnection,
  command: string,
  cwd: string | undefined,
  onEvent: (e: TerminalEvent) => void,
  signal?: AbortSignal,
) => {
  const res = await apiFetch(conn, "/api/terminal/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ command, cwd }),
    signal,
  });
  if (!res.ok || !res.body) throw new Error(`terminal: HTTP ${res.status} ${await res.text()}`);
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let nl: number;
    while ((nl = buffer.indexOf("\n")) >= 0) {
      const line = buffer.slice(0, nl);
      buffer = buffer.slice(nl + 1);
      if (line) onEvent(JSON.parse(line) as TerminalEvent);
    }
  }
};

export const createFilesApi = (conn: RuntimeConnection) => ({
  list: async () => {
    const res = await apiFetch(conn, "/api/files");
    if (!res.ok) throw new Error(`arquivos: HTTP ${res.status}`);
    return (await res.json()) as { dir: string; files: FileEntry[] };
  },
  remove: async (name: string) => {
    const res = await apiFetch(conn, `/api/files/${encodeURIComponent(name)}`, { method: "DELETE" });
    if (!res.ok) throw new Error(`apagar: HTTP ${res.status}`);
  },
  /** XHR (e não fetch) para ter progresso de envio — útil com arquivos grandes no celular. */
  upload: (files: File[], onProgress?: (fraction: number) => void) =>
    new Promise<{ saved: { name: string; size: number; path: string }[] }>((resolve, reject) => {
      const form = new FormData();
      files.forEach((f) => form.append("files", f, f.name));
      const xhr = new XMLHttpRequest();
      xhr.open("POST", `${conn.baseUrl}/api/files`);
      xhr.setRequestHeader("Authorization", `Bearer ${conn.token}`);
      xhr.upload.onprogress = (e) => e.lengthComputable && onProgress?.(e.loaded / e.total);
      xhr.onload = () =>
        xhr.status === 201 ? resolve(JSON.parse(xhr.responseText)) : reject(new Error(`upload: HTTP ${xhr.status} ${xhr.responseText}`));
      xhr.onerror = () => reject(new Error("upload: falha de rede"));
      xhr.send(form);
    }),
});
