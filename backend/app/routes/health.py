from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/api/health")
def health(request: Request):
    """Público. O app Android o consulta até aparecer o `boot` que ele mesmo passou por
    `APP_BOOT_ID`: assim sabe que quem respondeu é o processo que acabou de subir (e não um
    servidor antigo ainda segurando a porta)."""
    s = request.app.state.settings
    return {"ok": True, "boot": s.boot_id, "port": s.port}
