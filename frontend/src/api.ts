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
