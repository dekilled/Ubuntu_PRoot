from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.server import create_app

TOKEN = "test-token-123"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        port=8001,
        boot_id="boot-abc",
        api_token=TOKEN,
        secret_key="test-secret-key",
        data_dir=tmp_path,
        cors_origins=("http://localhost",),
        frontend_dist=None,
    )


@pytest.fixture
def client(settings: Settings):
    with TestClient(create_app(settings)) as c:
        yield c


@pytest.fixture
def auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}"}
