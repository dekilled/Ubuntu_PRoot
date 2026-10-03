import { useEffect, useMemo, useRef, useState } from "react";
import { Capacitor } from "@capacitor/core";
import { ProotRuntime, type RuntimeConnection } from "capacitor-proot-runtime";

import { createFilesApi, type FileEntry } from "./api";

const size = (n: number) =>
  n < 1024 ? `${n} B` : n < 1 << 20 ? `${(n / 1024).toFixed(1)} KB` : n < 1 << 30 ? `${(n / (1 << 20)).toFixed(1)} MB` : `${(n / (1 << 30)).toFixed(2)} GB`;
const join = (dir: string, name: string) => (dir ? `${dir}/${name}` : name);
const NATIVE = Capacitor.isNativePlatform();

/**
 * Gerenciador da pasta de trabalho (no app: /root/files — onde o terminal começa).
 * Upload: no celular pelo seletor nativo (plugin importFiles, sem rede); no navegador por HTTP.
 */
export function Files({ conn }: { conn: RuntimeConnection }) {
  const api = useMemo(() => createFilesApi(conn), [conn]);
  const [path, setPath] = useState("");
  const [abs, setAbs] = useState("");
  const [files, setFiles] = useState<FileEntry[]>([]);
  const [progress, setProgress] = useState<string | null>(null);
  const [newFolder, setNewFolder] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const picker = useRef<HTMLInputElement>(null);

  const load = (p = path) =>
    api
      .list(p)
      .then((r) => {
        setPath(r.path);
        setAbs(r.abs);
        setFiles(r.files);
        setError("");
      })
      .catch((e) => setError(String(e.message ?? e)));
  useEffect(() => {
    load("");
  }, [api]); // eslint-disable-line react-hooks/exhaustive-deps

  // Progresso do import nativo.
  useEffect(() => {
    if (!NATIVE) return;
    const handle = ProotRuntime.addListener("importProgress", (p) => {
      const pct = p.total > 0 ? ` ${Math.round((p.loaded / p.total) * 100)}%` : ` ${size(p.loaded)}`;
      setProgress(`${p.count > 1 ? `(${p.index + 1}/${p.count}) ` : ""}${p.name}${pct}`);
    });
    return () => {
      handle.then((h) => h.remove());
    };
  }, []);

  const done = async (names: string[]) => {
    await load();
    setProgress(null);
    if (names.length) setInfo(`Enviado: ${names.join(", ")}`);
  };

  const upload = async () => {
    setError("");
    setInfo("");
    if (!NATIVE) return picker.current?.click();
    try {
      setProgress("abrindo…");
      const { files: saved } = await ProotRuntime.importFiles({ dir: path });
      await done(saved.map((f) => f.name));
    } catch (e) {
      setProgress(null);
      setError(String((e as Error).message ?? e));
    }
  };

  const uploadHttp = async (list: FileList | null) => {
    if (!list?.length) return;
    try {
      setProgress("0%");
      const r = await api.upload(Array.from(list), path, (f) => setProgress(`${Math.round(f * 100)}%`));
      await done(r.saved.map((f) => f.name));
    } catch (e) {
      setProgress(null);
      setError(String((e as Error).message ?? e));
    } finally {
      if (picker.current) picker.current.value = "";
    }
  };

  const createFolder = async () => {
    const name = (newFolder ?? "").trim();
    if (!name) return setNewFolder(null);
    try {
      await api.mkdir(path, name);
      setNewFolder(null);
      await load();
    } catch (e) {
      setError(String((e as Error).message ?? e));
    }
  };

  const remove = async (f: FileEntry) => {
    if (!window.confirm(f.is_dir ? `Apagar a pasta "${f.name}" e tudo dentro dela?` : `Apagar "${f.name}"?`)) return;
    try {
      await api.remove(join(path, f.name));
      await load();
    } catch (e) {
      setError(String((e as Error).message ?? e));
    }
  };

  const crumbs = path ? path.split("/") : [];

  return (
    <section>
      <h2>Arquivos</h2>
      <nav className="crumbs">
        <button className="link" onClick={() => load("")}>
          files
        </button>
        {crumbs.map((c, i) => (
          <span key={i}>
            {" / "}
            <button className="link" onClick={() => load(crumbs.slice(0, i + 1).join("/"))}>
              {c}
            </button>
          </span>
        ))}
      </nav>
      <small className="path" title="caminho dentro do Ubuntu (use no terminal)">{abs}</small>

      <div className="row wrap" style={{ marginTop: 12 }}>
        <button onClick={upload} disabled={progress !== null}>
          {progress === null ? "📎 Enviar arquivos" : `Enviando ${progress}`}
        </button>
        <button className="ghost" onClick={() => setNewFolder("")}>
          + Pasta
        </button>
        <button className="ghost" onClick={() => load()}>
          Atualizar
        </button>
        <input ref={picker} type="file" multiple hidden onChange={(e) => uploadHttp(e.target.files)} />
      </div>

      {newFolder !== null && (
        <form
          className="row"
          style={{ marginTop: 10 }}
          onSubmit={(e) => {
            e.preventDefault();
            createFolder();
          }}
        >
          <input autoFocus value={newFolder} onChange={(e) => setNewFolder(e.target.value)} placeholder="nome da pasta" autoCapitalize="off" />
          <button type="submit">Criar</button>
          <button type="button" className="ghost" onClick={() => setNewFolder(null)}>
            ✕
          </button>
        </form>
      )}

      {error && <p className="error">{error}</p>}
      {info && <p className="ok">{info}</p>}

      <ul className="files">
        {path && (
          <li>
            <button className="link" onClick={() => load(crumbs.slice(0, -1).join("/"))}>
              ⬆ ..
            </button>
          </li>
        )}
        {files.length === 0 && <li className="muted">Pasta vazia.</li>}
        {files.map((f) => (
          <li key={f.name}>
            {f.is_dir ? (
              <button className="link" onClick={() => load(join(path, f.name))}>
                📁 {f.name}
              </button>
            ) : (
              <span>
                📄 {f.name}
                <small className="inline"> · {size(f.size)}</small>
              </span>
            )}
            <button className="ghost" aria-label={`Apagar ${f.name}`} onClick={() => remove(f)}>
              ✕
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
