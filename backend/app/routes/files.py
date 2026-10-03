"""Upload de arquivos para a pasta de trabalho (no app: /root/files, a mesma onde o terminal
começa). Lista, recebe (vários de uma vez, gravando em pedaços) e apaga."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, UploadFile

router = APIRouter(prefix="/api/files")
CHUNK = 1 << 20


def _safe_name(name: str) -> str:
    """Só o nome final, sem diretórios nem caracteres de controle."""
    clean = "".join(c for c in Path(name.replace("\\", "/")).name if c.isprintable()).strip()
    if clean in ("", ".", ".."):
        raise HTTPException(400, f"Nome de arquivo inválido: {name!r}")
    return clean[:200]


def _free_path(folder: Path, name: str) -> Path:
    """`foto.jpg` → `foto (1).jpg` se já existir: upload nunca sobrescreve."""
    target = folder / name
    stem, suffix = Path(name).stem, Path(name).suffix
    n = 1
    while target.exists():
        target = folder / f"{stem} ({n}){suffix}"
        n += 1
    return target


def _entry(p: Path) -> dict:
    st = p.stat()
    return {
        "name": p.name,
        "size": st.st_size,
        "is_dir": p.is_dir(),
        "modified": datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(),
    }


@router.get("")
def list_files(request: Request):
    folder = request.app.state.settings.uploads_dir
    folder.mkdir(parents=True, exist_ok=True)
    items = sorted(folder.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    return {"dir": str(folder), "files": [_entry(p) for p in items]}


@router.post("", status_code=201)
async def upload(request: Request, files: list[UploadFile]):
    s = request.app.state.settings
    folder = s.uploads_dir
    folder.mkdir(parents=True, exist_ok=True)
    limit = s.max_upload_mb << 20
    saved = []
    for f in files:
        target = _free_path(folder, _safe_name(f.filename or ""))
        partial = target.with_name(target.name + ".part")
        size = 0
        try:
            with open(partial, "wb") as out:
                while chunk := await f.read(CHUNK):
                    size += len(chunk)
                    if size > limit:
                        raise HTTPException(413, f"{f.filename}: maior que {s.max_upload_mb} MB")
                    out.write(chunk)
            os.replace(partial, target)
        finally:
            partial.unlink(missing_ok=True)
        saved.append({"name": target.name, "size": size, "path": str(target)})
    return {"saved": saved}


@router.delete("/{name}", status_code=204)
def delete_file(name: str, request: Request):
    target = request.app.state.settings.uploads_dir / _safe_name(name)
    if not target.is_file():
        raise HTTPException(404, "Arquivo não encontrado")
    target.unlink()
