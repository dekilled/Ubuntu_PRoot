"""Gerenciador de arquivos da pasta de trabalho (no app: /root/files, onde o terminal começa).

Todos os caminhos (`path`) são RELATIVOS a essa pasta e nunca saem dela (nem por `..` nem por
symlink). No celular o upload normalmente é feito pelo lado nativo (plugin `importFiles`, sem
passar pela rede); o POST daqui é o caminho do navegador e de automações.
"""
from __future__ import annotations

import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/files")
CHUNK = 1 << 20


def _root(request: Request) -> Path:
    root = request.app.state.settings.uploads_dir
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def _resolve(root: Path, rel: str) -> Path:
    """`rel` (relativo à pasta de trabalho) → caminho absoluto, garantindo que fica dentro dela."""
    target = (root / rel.strip().lstrip("/")).resolve()
    if target != root and root not in target.parents:
        raise HTTPException(400, "Caminho fora da pasta de arquivos")
    return target


def _safe_name(name: str) -> str:
    """Só o nome final, sem diretórios nem caracteres de controle."""
    clean = "".join(c for c in Path(name.replace("\\", "/")).name if c.isprintable()).strip()
    if clean in ("", ".", ".."):
        raise HTTPException(400, f"Nome inválido: {name!r}")
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
    st = p.lstat()
    return {
        "name": p.name,
        "size": st.st_size,
        "is_dir": p.is_dir(),
        "modified": datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(),
    }


def _rel(root: Path, p: Path) -> str:
    return "" if p == root else str(p.relative_to(root))


@router.get("")
def list_dir(request: Request, path: str = ""):
    root = _root(request)
    folder = _resolve(root, path)
    if not folder.is_dir():
        raise HTTPException(404, "Pasta não encontrada")
    items = sorted(folder.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    return {"root": str(root), "path": _rel(root, folder), "abs": str(folder), "files": [_entry(p) for p in items]}


@router.post("", status_code=201)
async def upload(request: Request, files: list[UploadFile], path: str = ""):
    s = request.app.state.settings
    folder = _resolve(_root(request), path)
    if not folder.is_dir():
        raise HTTPException(404, "Pasta não encontrada")
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


class MkdirIn(BaseModel):
    path: str = ""  # pasta onde criar
    name: str = Field(min_length=1, max_length=200)


@router.post("/mkdir", status_code=201)
def mkdir(body: MkdirIn, request: Request):
    root = _root(request)
    parent = _resolve(root, body.path)
    if not parent.is_dir():
        raise HTTPException(404, "Pasta não encontrada")
    target = parent / _safe_name(body.name)
    if target.exists():
        raise HTTPException(409, "Já existe um item com esse nome")
    target.mkdir()
    return {"path": _rel(root, target)}


@router.delete("", status_code=204)
def delete(request: Request, path: str):
    root = _root(request)
    target = _resolve(root, path)
    if target == root:
        raise HTTPException(400, "Não dá para apagar a pasta de arquivos inteira")
    if target.is_dir() and not target.is_symlink():
        shutil.rmtree(target)
    elif target.exists() or target.is_symlink():
        target.unlink()
    else:
        raise HTTPException(404, "Não encontrado")
