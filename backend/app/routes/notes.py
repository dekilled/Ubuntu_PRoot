"""Exemplo mínimo de CRUD sobre SQLite. Apague e substitua pelos recursos do seu app."""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/notes")


class NoteIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


@router.get("")
def list_notes(request: Request):
    with request.app.state.db.connect() as conn:
        rows = conn.execute("SELECT id, text, created_at FROM notes ORDER BY id DESC LIMIT 200").fetchall()
    return [dict(r) for r in rows]


@router.post("", status_code=201)
def create_note(body: NoteIn, request: Request):
    with request.app.state.db.connect() as conn:
        cur = conn.execute("INSERT INTO notes (text) VALUES (?)", (body.text.strip(),))
        row = conn.execute("SELECT id, text, created_at FROM notes WHERE id = ?", (cur.lastrowid,)).fetchone()
    return dict(row)


@router.delete("/{note_id}", status_code=204)
def delete_note(note_id: int, request: Request):
    with request.app.state.db.connect() as conn:
        if conn.execute("DELETE FROM notes WHERE id = ?", (note_id,)).rowcount == 0:
            raise HTTPException(404, "Nota não encontrada")
