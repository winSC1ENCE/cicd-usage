from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import main


@pytest.fixture
def client(tmp_path: Path, monkeypatch):
    (tmp_path / "a.md").write_text("---\ntitle: Alpha\ntags: [x]\n---\nHello [[b]]\n")
    monkeypatch.setattr(main, "CONTENT_DIR", tmp_path)
    return TestClient(main.app)


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_list_pages(client):
    assert client.get("/api/pages").json() == [{"path": "a.md", "title": "Alpha", "tags": ["x"]}]


def test_get_page(client):
    data = client.get("/api/pages/a.md").json()
    assert data["title"] == "Alpha" and "Hello" in data["body"]


def test_path_traversal_rejected(client):
    assert client.get("/api/pages/../../etc/passwd").status_code == 404
    assert client.get("/api/pages/%2e%2e/%2e%2e/etc/passwd.md").status_code == 404
