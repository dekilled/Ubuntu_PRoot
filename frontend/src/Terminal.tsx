import { useEffect, useRef, useState } from "react";
import { apiFetch, type RuntimeConnection } from "capacitor-proot-runtime";

import { createFilesApi, runCommand } from "./api";

const ANSI = /\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07]*\x07/g; // cores/cursor: a saída é texto puro
const MAX_OUTPUT = 200_000;
const HISTORY_KEY = "terminal.history";
const SHORTCUTS = ["ls -la", "pwd", "uname -a", "cat /etc/os-release", "python3 --version", "df -h", "free -m", "pip list"];

const loadHistory = (): string[] => {
  try {
    return JSON.parse(localStorage.getItem(HISTORY_KEY) ?? "[]");
  } catch {
    return [];
  }
};

/**
 * Terminal simples (não interativo): cada linha vira um `bash -c` no Ubuntu, com a saída ao vivo.
 * Programas que esperam teclado (vim, top, python sem argumentos) não funcionam aqui — use
 * versões não interativas (`python3 -c "..."`, `top -bn1`).
 */
export function Terminal({ conn }: { conn: RuntimeConnection }) {
  const [output, setOutput] = useState("Terminal do Ubuntu. Comandos rodam sem interação (stdin vazio).\n");
  const [cwd, setCwd] = useState<string>();
  const [command, setCommand] = useState("");
  const [running, setRunning] = useState<AbortController | null>(null);
  const [uploadPct, setUploadPct] = useState<number | null>(null);
  const history = useRef<string[]>(loadHistory());
  const cursor = useRef(history.current.length);
  const screen = useRef<HTMLPreElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const picker = useRef<HTMLInputElement>(null);

  const append = (text: string) => setOutput((o) => (o + text.replace(ANSI, "")).slice(-MAX_OUTPUT));

  // Diretório inicial (a pasta de arquivos) e se o terminal está ligado no servidor.
  useEffect(() => {
    apiFetch(conn, "/api/terminal")
      .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
      .then((info: { cwd: string }) => setCwd((c) => c ?? info.cwd))
      .catch((status) => status === 404 && append("[terminal desligado no servidor: APP_ENABLE_TERMINAL=0]\n"));
  }, [conn]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    screen.current?.scrollTo({ top: screen.current.scrollHeight });
  }, [output]);

  const run = async (cmd: string) => {
    const line = cmd.trim();
    if (!line || running) return;
    if (line === "clear") return setOutput("");
    history.current = [...history.current.filter((h) => h !== line), line].slice(-100);
    cursor.current = history.current.length;
    try {
      localStorage.setItem(HISTORY_KEY, JSON.stringify(history.current));
    } catch {
      /* sem armazenamento: histórico só nesta sessão */
    }
    setCommand("");
    append(`\n${cwd ?? "~"} $ ${line}\n`);
    const ctrl = new AbortController();
    setRunning(ctrl);
    try {
      await runCommand(
        conn,
        line,
        cwd,
        (e) => {
          if ("out" in e) append(e.out);
          else {
            setCwd(e.cwd);
            if (e.exit !== 0) append(`[código ${e.exit}]\n`);
          }
        },
        ctrl.signal,
      );
    } catch (e) {
      append(ctrl.signal.aborted ? "^C [interrompido]\n" : `[erro] ${String(e)}\n`);
    } finally {
      setRunning(null);
      input.current?.focus();
    }
  };

  const onKey = (e: React.KeyboardEvent<HTMLInputElement>) => {
    const h = history.current;
    if (e.key === "ArrowUp" && cursor.current > 0) {
      e.preventDefault();
      cursor.current -= 1;
      setCommand(h[cursor.current]);
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      cursor.current = Math.min(h.length, cursor.current + 1);
      setCommand(h[cursor.current] ?? "");
    } else if (e.key === "c" && e.ctrlKey && running) {
      e.preventDefault();
      running.abort();
    }
  };

  const upload = async (list: FileList | null) => {
    if (!list?.length) return;
    setUploadPct(0);
    try {
      const { saved } = await createFilesApi(conn).upload(Array.from(list), (f) => setUploadPct(Math.round(f * 100)));
      append(`\n[upload] ${saved.map((s) => s.path).join(", ")}\n`);
    } catch (e) {
      append(`\n[upload falhou] ${String(e)}\n`);
    } finally {
      setUploadPct(null);
      if (picker.current) picker.current.value = "";
    }
  };

  return (
    <section className="terminal">
      <div className="term-toolbar">
        <span className="cwd" title={cwd}>
          {cwd ?? "~"}
        </span>
        <button className="ghost" onClick={() => picker.current?.click()} disabled={uploadPct !== null}>
          {uploadPct === null ? "📎 Enviar arquivo" : `Enviando ${uploadPct}%`}
        </button>
        <button className="ghost" onClick={() => setOutput("")}>
          Limpar
        </button>
        <input ref={picker} type="file" multiple hidden onChange={(e) => upload(e.target.files)} />
      </div>
      <pre ref={screen} className="screen" onClick={() => input.current?.focus()}>
        {output}
      </pre>
      <div className="chips">
        {SHORTCUTS.map((s) => (
          <button key={s} className="chip" disabled={!!running} onClick={() => run(s)}>
            {s}
          </button>
        ))}
      </div>
      <form
        className="row prompt"
        onSubmit={(e) => {
          e.preventDefault();
          run(command);
        }}
      >
        <span>$</span>
        <input
          ref={input}
          value={command}
          onChange={(e) => setCommand(e.target.value)}
          onKeyDown={onKey}
          placeholder={running ? "rodando…" : "digite um comando"}
          autoCapitalize="off"
          autoCorrect="off"
          autoComplete="off"
          spellCheck={false}
          enterKeyHint="send"
        />
        {running ? (
          <button type="button" className="danger" onClick={() => running.abort()}>
            Parar
          </button>
        ) : (
          <button type="submit">Rodar</button>
        )}
      </form>
    </section>
  );
}
