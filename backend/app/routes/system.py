import os
import platform
import sys
import time

from fastapi import APIRouter, Request

router = APIRouter()
_STARTED = time.time()


def _os_name() -> str:
    try:
        with open("/etc/os-release") as f:
            for line in f:
                if line.startswith("PRETTY_NAME="):
                    return line.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    return platform.platform()


@router.get("/api/system")
def system(request: Request):
    """Mostra onde o servidor está rodando (no app: Ubuntu dentro do PRoot)."""
    s = request.app.state.settings
    return {
        "os": _os_name(),
        "machine": platform.machine(),
        "python": sys.version.split()[0],
        "pid": os.getpid(),
        "uptime_s": int(time.time() - _STARTED),
        "data_dir": str(s.data_dir),
    }
