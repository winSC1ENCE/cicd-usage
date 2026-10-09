from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import main
from app.content import Page
from app.graph import build_graph, resolve_relative


def page(path: str, body: str, title: str = "") -> Page:
    return Page(path=path, title=title or path, tags=[], body=body)


def test_edges_from_wikilinks_and_relative_links():
    pages = [
        page("index.md", "see [[HowTo/Beispiel]] and [x](HowTo/Beispiel.md)"),
        page("HowTo/Beispiel.md", "back [home](../index.md) [[missing]]"),
    ]
    g = build_graph(pages)
    assert g["links"] == [
        {"source": "HowTo/Beispiel.md", "target": "index.md"},
        {"source": "index.md", "target": "HowTo/Beispiel.md"},
    ]


def test_links_in_code_are_ignored():
    pages = [page("a.md", "`[[b]]`\n```\n[[b]]\n```"), page("b.md", "")]
    assert build_graph(pages)["links"] == []


def test_relative_escape_rejected():
    assert resolve_relative("../../x.md", "a.md") is None


@pytest.fixture
def client(tmp_path: Path, monkeypatch):
    (tmp_path / "a.md").write_text("---\ntitle: Alpha\n---\nlinks to [[b]]\n")
    (tmp_path / "b.md").write_text("---\ntitle: Beta\n---\nplain text about graphs\n")
    monkeypatch.setattr(main, "CONTENT_DIR", tmp_path)
    return TestClient(main.app)


def test_graph_endpoint_and_backlinks(client):
    assert client.get("/api/graph").json()["links"] == [{"source": "a.md", "target": "b.md"}]
    assert client.get("/api/pages/b.md").json()["backlinks"] == ["a.md"]


def test_search(client):
    hits = client.get("/api/search", params={"q": "graphs"}).json()
    assert [h["path"] for h in hits] == ["b.md"]
    assert client.get("/api/search", params={"q": "a"}).status_code == 422
