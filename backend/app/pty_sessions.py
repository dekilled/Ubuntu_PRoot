"""Sessões de terminal de verdade: um bash num PTY (pseudo-terminal), como no Termux.

Diferente de rodar um comando por vez, o PTY permite programas interativos — `apt` perguntando
"Y/n", `nano`, `python` (REPL), `top`, Ctrl+C, cores, setas, Tab para completar.

A sessão vive no servidor, independente da conexão: se a WebView cair (app em segundo plano,
troca de aba), o cliente reconecta com o id e recebe de volta o fim da tela (scrollback). Sessões
sem ninguém conectado morrem depois de DETACHED_TTL_S; o shell também morre quando você dá `exit`.
"""
from __future__ import annotations

import asyncio
import fcntl
import logging
import os
import pty
import secrets
import shutil
import signal
import struct
import termios
import warnings
from typing import Callable

log = logging.getLogger("app.pty")

SCROLLBACK_BYTES = 256 * 1024
MAX_SESSIONS = 8
DETACHED_TTL_S = 30 * 60
HIDDEN_ENV = {"APP_API_TOKEN", "APP_SECRET_KEY"}

Listener = Callable[[bytes | None], None]  # None = o shell terminou


class PtySession:
    def __init__(self, cwd: str, cols: int, rows: int):
        self.id = secrets.token_urlsafe(12)
        self.exit_code: int | None = None
        self._scrollback = bytearray()
        self._listeners: set[Listener] = set()
        self._pending = bytearray()  # entrada que o PTY ainda não aceitou
        self._expire: asyncio.TimerHandle | None = None
        self._loop = asyncio.get_running_loop()

        shell = shutil.which("bash") or "/bin/sh"
        env = {k: v for k, v in os.environ.items() if k not in HIDDEN_ENV}
        env.update(TERM="xterm-256color", COLORTERM="truecolor", LANG=env.get("LANG", "C.UTF-8"))
        with warnings.catch_warnings():  # "processo com threads": o filho só faz chdir + exec
            warnings.simplefilter("ignore", DeprecationWarning)
            pid, fd = pty.fork()
        if pid == 0:  # filho: vira o shell (o pty.fork já fez setsid + terminal de controle)
            try:
                os.chdir(cwd)
            except OSError:
                pass
            try:
                os.execvpe(shell, [shell, "-l"], env)
            finally:
                os._exit(127)
        self.pid, self.fd = pid, fd
        os.set_blocking(fd, False)
        self.resize(cols, rows)
        self._loop.add_reader(fd, self._on_readable)

    # ---- saída do shell → clientes ----
    def _on_readable(self) -> None:
        try:
            data = os.read(self.fd, 65536)
        except BlockingIOError:
            return
        except OSError:  # EIO: o lado do shell fechou
            data = b""
        if not data:
            return self._finish()
        self._scrollback += data
        if len(self._scrollback) > SCROLLBACK_BYTES:
            del self._scrollback[: len(self._scrollback) - SCROLLBACK_BYTES]
        for listener in list(self._listeners):
            listener(data)

    def _finish(self) -> None:
        if self.exit_code is not None:
            return
        self._loop.remove_reader(self.fd)
        self._loop.remove_writer(self.fd)
        try:
            _, status = os.waitpid(self.pid, 0)
            self.exit_code = os.waitstatus_to_exitcode(status)
        except ChildProcessError:
            self.exit_code = -1
        os.close(self.fd)
        for listener in list(self._listeners):
            listener(None)
        _SESSIONS.pop(self.id, None)

    @property
    def alive(self) -> bool:
        return self.exit_code is None

    def scrollback(self) -> bytes:
        return bytes(self._scrollback)

    # ---- clientes → shell ----
    def write(self, data: bytes) -> None:
        if not self.alive:
            return
        self._pending += data
        self._flush()

    def _flush(self) -> None:
        while self._pending:
            try:
                n = os.write(self.fd, self._pending)
            except BlockingIOError:  # PTY cheio (o programa não está lendo): espera ficar gravável
                self._loop.add_writer(self.fd, self._flush)
                return
            except OSError:
                self._pending.clear()
                return
            del self._pending[:n]
        self._loop.remove_writer(self.fd)

    def resize(self, cols: int, rows: int) -> None:
        if self.alive:
            cols, rows = max(2, min(cols, 1000)), max(2, min(rows, 500))
            fcntl.ioctl(self.fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))

    # ---- conexões ----
    def attach(self, listener: Listener) -> None:
        if self._expire:
            self._expire.cancel()
            self._expire = None
        self._listeners.add(listener)

    def detach(self, listener: Listener) -> None:
        self._listeners.discard(listener)
        if not self._listeners and self.alive:
            self._expire = self._loop.call_later(DETACHED_TTL_S, self.kill)

    def kill(self) -> None:
        """Encerra o shell e o que ele abriu (SIGHUP como ao fechar um terminal; SIGKILL se teimar)."""
        if not self.alive:
            return
        for sig in (signal.SIGHUP, signal.SIGCONT):
            try:
                os.killpg(self.pid, sig)
            except ProcessLookupError:
                pass

        def force() -> None:
            if self.alive:
                try:
                    os.killpg(self.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass

        self._loop.call_later(2, force)


_SESSIONS: dict[str, PtySession] = {}


def get(session_id: str | None) -> PtySession | None:
    s = _SESSIONS.get(session_id or "")
    return s if s and s.alive else None


def create(cwd: str, cols: int, rows: int) -> PtySession:
    if len(_SESSIONS) >= MAX_SESSIONS:
        oldest = next(iter(_SESSIONS.values()))
        oldest.kill()
        _SESSIONS.pop(oldest.id, None)
    s = PtySession(cwd, cols, rows)
    _SESSIONS[s.id] = s
    return s


def kill_all() -> None:
    for s in list(_SESSIONS.values()):
        s.kill()
    _SESSIONS.clear()
