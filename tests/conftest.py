import pytest
from fastapi.testclient import TestClient

from tests.helpers import HEADER


@pytest.fixture()
def db(tmp_path, monkeypatch):
    """A fresh empty database for engine-level tests."""
    import app.db as appdb
    monkeypatch.setattr(appdb, "DB_PATH", str(tmp_path / "test.db"))
    appdb.init_db()
    return appdb


def _prepare(tmp_path, monkeypatch):
    import app.db as appdb
    from app import ratelimit
    from app.engine.query import CONFIG
    from app.main import app as fastapi_app      # imported while cwd is the project root
    monkeypatch.setattr(appdb, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setitem(CONFIG, "min_group_size", 5)
    ratelimit._hits.clear()
    monkeypatch.chdir(tmp_path)                  # data/ and reports/ go to a temp folder
    return fastapi_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    fastapi_app = _prepare(tmp_path, monkeypatch)
    with TestClient(fastapi_app) as c:
        c.headers.update(HEADER)
        yield c


@pytest.fixture()
def quiet_client(tmp_path, monkeypatch):
    """Like client, but returns the 500 response instead of raising (safe-failure test)."""
    fastapi_app = _prepare(tmp_path, monkeypatch)
    with TestClient(fastapi_app, raise_server_exceptions=False) as c:
        c.headers.update(HEADER)
        yield c