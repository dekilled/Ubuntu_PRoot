import { useEffect, useMemo, useState } from "react";

import type { RuntimeConnection } from "capacitor-proot-runtime";

import { createApi, type Api, type Note, type SystemInfo } from "./api";
import { Files } from "./Files";
import { fetchLogs, restartRuntime, useRuntime } from "./runtime";
import { Terminal } from "./Terminal";

const TABS = { home: "Início", terminal: "Terminal", files: "Arquivos" } as const;
type Tab = keyof typeof TABS;

export function App() {
  const status = useRuntime();
  const api = useMemo(() => (status.connection ? createApi(status.connection) : null), [status.connection]);
  const [tab, setTab] = useState<Tab>("home");

  return (
    <main>
      <h1>PRoot App</h1>
      {status.state === "ready" && api && status.connection ? (
        <>
          <nav className="tabs">
            {(Object.keys(TABS) as Tab[]).map((t) => (
              <button key={t} className={t === tab ? "active" : ""} onClick={() => setTab(t)}>
                {TABS[t]}
              </button>
            ))}
          </nav>
          <TabBody tab={tab} api={api} conn={status.connection} />
        </>
      ) : (
        <Booting status={status} />
      )}
    </main>
  );
}

/** Terminal e Arquivos são a base de testes: apague as abas que seu app não precisar. */
function TabBody({ tab, api, conn }: { tab: Tab; api: Api; conn: RuntimeConnection }) {
  if (tab === "terminal") return <Terminal conn={conn} />;
  if (tab === "files") return <Files conn={conn} />;
  return <Ready api={api} />;
}

function Booting({ status }: { status: ReturnType<typeof useRuntime> }) {
  const [logs, setLogs] = useState<string | null>(null);

  if (status.state === "failed") {
    return (
      <section>
        <p className="error">Não consegui iniciar o servidor.</p>
        <pre>{status.message}</pre>
        <div className="row">
          <button onClick={() => restartRuntime()}>Tentar de novo</button>
          <button className="ghost" onClick={() => fetchLogs().then(setLogs)}>
            Ver logs
          </button>
        </div>
        {logs && <pre>{logs}</pre>}
      </section>
    );
  }

  const installing = status.state === "installing";
  return (
    <section>
      <p>
        {installing
          ? `Instalando o Ubuntu… ${status.progress ?? 0}%`
          : status.state === "starting"
            ? "Iniciando o servidor…"
            : "Conectando…"}
      </p>
      <progress max={100} value={installing ? status.progress ?? 0 : undefined} />
      {installing && <small>Só acontece na primeira vez (ou depois de atualizar o app).</small>}
    </section>
  );
}

function Ready({ api }: { api: Api }) {
  const [info, setInfo] = useState<SystemInfo | null>(null);
  const [notes, setNotes] = useState<Note[]>([]);
  const [text, setText] = useState("");
  const [error, setError] = useState("");

  const load = () => api.notes().then(setNotes);
  useEffect(() => {
    api.system().then(setInfo).catch((e) => setError(String(e)));
    load().catch((e) => setError(String(e)));
  }, [api]); // eslint-disable-line react-hooks/exhaustive-deps

  const add = async () => {
    if (!text.trim()) return;
    await api.addNote(text);
    setText("");
    load();
  };

  return (
    <>
      {info && (
        <section>
          <h2>Servidor</h2>
          <p>
            <b>{info.os}</b> ({info.machine}) · Python {info.python}
          </p>
          <small>dados em {info.data_dir}</small>
        </section>
      )}
      <section>
        <h2>Notas (exemplo: API Python + SQLite)</h2>
        <form
          className="row"
          onSubmit={(e) => {
            e.preventDefault();
            add();
          }}
        >
          <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Escreva algo…" />
          <button type="submit">Salvar</button>
        </form>
        <ul>
          {notes.map((n) => (
            <li key={n.id}>
              <span>{n.text}</span>
              <button className="ghost" onClick={() => api.deleteNote(n.id).then(load)} aria-label="Apagar">
                ✕
              </button>
            </li>
          ))}
        </ul>
        {error && <p className="error">{error}</p>}
      </section>
    </>
  );
}
