import { useEffect, useMemo, useRef, useState } from "react";
import type { RuntimeConnection } from "capacitor-proot-runtime";

import { createFilesApi, type FileEntry } from "./api";

const size = (n: number) =>
  n < 1024 ? `${n} B` : n < 1 << 20 ? `${(n / 1024).toFixed(1)} KB` : `${(n / (1 << 20)).toFixed(1)} MB`;

/** Pasta de trabalho (no app: /root/files). O terminal começa nela, então dá para usar os arquivos direto. */
export function Files({ conn }: { conn: RuntimeConnection }) {
  const api = useMemo(() => createFilesApi(conn), [conn]);
  const [dir, setDir] = useState("");
  const [files, setFiles] = useState<FileEntry[]>([]);
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState("");
  const picker = useRef<HTMLInputElement>(null);

  const load = () =>
    api
      .list()
      .then((r) => {
        setDir(r.dir);
        setFiles(r.files);
      })
      .catch((e) => setError(String(e)));
  useEffect(() => {
    load();
  }, [api]); // eslint-disable-line react-hooks/exhaustive-deps

  const upload = async (list: FileList | null) => {
    if (!list?.length) return;
    setError("");
    setProgress(0);
    try {
      await api.upload(Array.from(list), setProgress);
      await load();
    } catch (e) {
      setError(String(e));
    } finally {
      setProgress(null);
      if (picker.current) picker.current.value = "";
    }
  };

  return (
    <section>
      <h2>Arquivos</h2>
      <small>{dir}</small>
      <div className="row" style={{ marginTop: 12 }}>
        <button onClick={() => picker.current?.click()} disabled={progress !== null}>
          {progress === null ? "📎 Enviar arquivos" : `Enviando ${Math.round(progress * 100)}%`}
        </button>
        <button className="ghost" onClick={load}>
          Atualizar
        </button>
        <input ref={picker} type="file" multiple hidden onChange={(e) => upload(e.target.files)} />
      </div>
      {progress !== null && <progress max={1} value={progress} />}
      {error && <p className="error">{error}</p>}
      <ul>
        {files.length === 0 && <li className="muted">Nenhum arquivo ainda.</li>}
        {files.map((f) => (
          <li key={f.name}>
            <span>
              {f.is_dir ? "📁 " : ""}
              {f.name}
              {!f.is_dir && <small className="inline"> · {size(f.size)}</small>}
            </span>
            {!f.is_dir && (
              <button className="ghost" aria-label={`Apagar ${f.name}`} onClick={() => api.remove(f.name).then(load, (e) => setError(String(e)))}>
                ✕
              </button>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
