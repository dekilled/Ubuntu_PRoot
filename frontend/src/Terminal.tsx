import { useEffect, useRef, useState } from "react";
import { Capacitor } from "@capacitor/core";
import { FitAddon } from "@xterm/addon-fit";
import { Terminal as XTerm } from "@xterm/xterm";
import "@xterm/xterm/css/xterm.css";
import { ProotRuntime, type RuntimeConnection } from "capacitor-proot-runtime";

import { openShell } from "./api";

type Mod = "ctrl" | "alt";
const FONT_KEY = "terminal.fontSize";

/** Teclas que o teclado do celular não tem (como a barra extra do Termux). */
const KEYS: { label: string; seq?: string; app?: string; mod?: Mod }[] = [
  { label: "ESC", seq: "\x1b" },
  { label: "TAB", seq: "\t" },
  { label: "CTRL", mod: "ctrl" },
  { label: "ALT", mod: "alt" },
  { label: "←", seq: "\x1b[D", app: "\x1bOD" },
  { label: "↓", seq: "\x1b[B", app: "\x1bOB" },
  { label: "↑", seq: "\x1b[A", app: "\x1bOA" },
  { label: "→", seq: "\x1b[C", app: "\x1bOC" },
  { label: "HOME", seq: "\x1b[H", app: "\x1bOH" },
  { label: "END", seq: "\x1b[F", app: "\x1bOF" },
  { label: "PGUP", seq: "\x1b[5~" },
  { label: "PGDN", seq: "\x1b[6~" },
  { label: "-", seq: "-" },
  { label: "/", seq: "/" },
  { label: "|", seq: "|" },
  { label: "~", seq: "~" },
];

/** Ctrl+<tecla> → caractere de controle (Ctrl+C = \x03, Ctrl+D = \x04, Ctrl+Z = \x1a…). */
const withCtrl = (s: string) => {
  if (s.length !== 1) return s;
  const c = s.toUpperCase().charCodeAt(0);
  if (c >= 64 && c <= 95) return String.fromCharCode(c - 64); // @ A–Z [ \ ] ^ _
  if (s === " ") return "\x00";
  if (s === "?") return "\x7f";
  return s;
};

const readFontSize = () => {
  try {
    return Number(localStorage.getItem(FONT_KEY)) || 14;
  } catch {
    return 14;
  }
};

/**
 * Terminal real: bash num PTY no Ubuntu (WebSocket) + xterm.js. Programas interativos funcionam
 * (apt com "Y/n", nano, python, top, Ctrl+C). O shell sobrevive se a conexão cair; ao voltar,
 * a tela é restaurada.
 */
/** Faz o elemento ir do seu topo até o fim da área visível (acompanha teclado e rotação). */
const useFillViewport = (ref: React.RefObject<HTMLElement | null>) => {
  useEffect(() => {
    const vv = window.visualViewport;
    const update = () => {
      const el = ref.current;
      if (!el) return;
      const visible = vv ? vv.height + vv.offsetTop : window.innerHeight;
      el.style.height = `${Math.max(260, visible - el.getBoundingClientRect().top - 8)}px`;
    };
    update();
    vv?.addEventListener("resize", update);
    window.addEventListener("resize", update);
    return () => {
      vv?.removeEventListener("resize", update);
      window.removeEventListener("resize", update);
    };
  }, [ref]);
};

export function Terminal({ conn }: { conn: RuntimeConnection }) {
  const section = useRef<HTMLElement>(null);
  useFillViewport(section);
  const host = useRef<HTMLDivElement>(null);
  const term = useRef<XTerm | null>(null);
  const shell = useRef<ReturnType<typeof openShell> | null>(null);
  const mods = useRef<Record<Mod, boolean>>({ ctrl: false, alt: false });
  const [modState, setModState] = useState({ ctrl: false, alt: false });
  const [status, setStatus] = useState("conectando…");
  const [ended, setEnded] = useState(false);
  const [fontSize, setFontSize] = useState(readFontSize);
  const [toast, setToast] = useState("");
  const [generation, setGeneration] = useState(0); // muda = nova sessão

  const setMod = (m: Mod, on: boolean) => {
    mods.current[m] = on;
    setModState({ ...mods.current });
  };

  /** Toda entrada (teclado do celular, teclas extras, colar) passa por aqui para aplicar CTRL/ALT. */
  const send = (data: string) => {
    let out = data;
    if (mods.current.ctrl) out = withCtrl(out);
    if (mods.current.alt) out = "\x1b" + out;
    if (mods.current.ctrl || mods.current.alt) setMod("ctrl", false), setMod("alt", false);
    shell.current?.input(out);
  };

  useEffect(() => {
    const xterm = new XTerm({
      fontSize,
      fontFamily: 'ui-monospace, "JetBrains Mono", Menlo, Consolas, "DejaVu Sans Mono", monospace',
      cursorBlink: true,
      scrollback: 5000,
      allowProposedApi: false,
      theme: { background: "#05070d", foreground: "#e6e9f2", cursor: "#8b8bf0", selectionBackground: "#8b8bf055" },
    });
    const fit = new FitAddon();
    xterm.loadAddon(fit);
    xterm.open(host.current!);
    term.current = xterm;
    const doFit = () => {
      try {
        fit.fit();
      } catch {
        /* ainda sem tamanho */
      }
    };
    doFit();

    setEnded(false);
    const sh = openShell(conn, () => ({ cols: xterm.cols, rows: xterm.rows }), {
      onOutput: (bytes) => xterm.write(bytes),
      onStatus: (s, detail) => {
        if (s === "ready") {
          xterm.reset(); // na reconexão o servidor reenvia a tela inteira
          setStatus(detail === "resumed" ? "sessão retomada" : "conectado");
          sh.resize();
        } else if (s === "exited") {
          xterm.write(`\r\n\x1b[2m[sessão encerrada (código ${detail}) — toque em "Nova sessão"]\x1b[0m\r\n`);
          setStatus("encerrado");
          setEnded(true);
        } else if (s === "error") {
          xterm.write(`\r\n\x1b[31m${detail}\x1b[0m\r\n`);
          setStatus("erro");
          setEnded(true);
        } else setStatus(s === "reconnecting" ? "reconectando…" : "conectando…");
      },
    });
    shell.current = sh;
    const typed = xterm.onData(send);

    const ro = new ResizeObserver(() => {
      doFit();
      sh.resize();
    });
    ro.observe(host.current!);
    const onVisible = () => document.visibilityState === "visible" && sh.wake();
    document.addEventListener("visibilitychange", onVisible);
    xterm.focus();

    return () => {
      document.removeEventListener("visibilitychange", onVisible);
      ro.disconnect();
      typed.dispose();
      sh.dispose(); // só desconecta: o shell continua vivo e volta ao reabrir a aba
      xterm.dispose();
      term.current = null;
    };
  }, [conn, generation]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!term.current) return;
    term.current.options.fontSize = fontSize;
    try {
      localStorage.setItem(FONT_KEY, String(fontSize));
    } catch {
      /* ignore */
    }
    window.dispatchEvent(new Event("resize"));
  }, [fontSize]);

  const pressKey = (k: (typeof KEYS)[number]) => {
    if (k.mod) return setMod(k.mod, !mods.current[k.mod]);
    const appMode = term.current?.modes.applicationCursorKeysMode;
    send(appMode && k.app ? k.app : k.seq!);
  };

  const paste = async () => {
    try {
      const text = await navigator.clipboard.readText();
      if (text) shell.current?.input(text);
    } catch {
      flash("Sem acesso à área de transferência: toque e segure no terminal para colar.");
    }
    term.current?.focus();
  };

  const flash = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(""), 4000);
  };

  const newSession = () => {
    shell.current?.kill();
    setGeneration((g) => g + 1);
  };

  const importHere = async () => {
    if (!Capacitor.isNativePlatform()) return flash("No navegador, envie pela aba Arquivos.");
    try {
      const { files } = await ProotRuntime.importFiles({});
      if (files.length) flash(`Salvo: ${files.map((f) => f.path).join(", ")}`);
    } catch (e) {
      flash(String(e));
    }
  };

  // Botões não podem roubar o foco do terminal (senão o teclado do celular fecha).
  const keep = (e: React.PointerEvent | React.MouseEvent) => e.preventDefault();

  return (
    <section className="terminal" ref={section}>
      <div className="term-toolbar">
        <span className="term-status">{status}</span>
        <button className="ghost" onMouseDown={keep} onClick={() => setFontSize((s) => Math.max(9, s - 1))} aria-label="Diminuir fonte">
          A−
        </button>
        <button className="ghost" onMouseDown={keep} onClick={() => setFontSize((s) => Math.min(24, s + 1))} aria-label="Aumentar fonte">
          A+
        </button>
        <button className="ghost" onMouseDown={keep} onClick={paste}>
          Colar
        </button>
        <button className="ghost" onMouseDown={keep} onClick={importHere} aria-label="Enviar arquivo">
          📎
        </button>
        <button className={ended ? "" : "ghost"} onMouseDown={keep} onClick={newSession}>
          Nova sessão
        </button>
      </div>
      <div ref={host} className="xterm-host" onClick={() => term.current?.focus()} />
      <div className="extra-keys" onPointerDown={keep}>
        {KEYS.map((k) => (
          <button
            key={k.label}
            className={k.mod && modState[k.mod] ? "on" : ""}
            onPointerDown={keep}
            onClick={() => pressKey(k)}
          >
            {k.label}
          </button>
        ))}
      </div>
      {toast && <div className="toast">{toast}</div>}
    </section>
  );
}
