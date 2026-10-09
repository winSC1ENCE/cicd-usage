from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import main
from app.gitlab import GitLabForge, validate_page_path


class FakeForge:
    def __init__(self):
        self.calls = []

    def propose(self, **kwargs):
        self.calls.append(kwargs)
        return "https://gitlab.example/mr/1"


@pytest.fixture
def setup(tmp_path: Path, monkeypatch):
    (tmp_path / "index.md").write_text("---\ntitle: Home\ntags: [a]\n---\nhi\n")
    (tmp_path / "x.md").write_text("---\ntitle: X\n---\nbody\n")
    monkeypatch.setattr(main, "CONTENT_DIR", tmp_path)
    forge = FakeForge()
    main.app.dependency_overrides[main.get_forge] = lambda: forge
    yield TestClient(main.app), forge
    main.app.dependency_overrides.clear()


def test_save_keeps_front_matter(setup):
    client, forge = setup
    r = client.put("/api/pages/x.md", json={"body": "# New", "author": "Nico"})
    assert r.json() == {"merge_request": "https://gitlab.example/mr/1"}
    call = forge.calls[0]
    assert call["exists"] is True and "title: X" in call["content"] and "# New" in call["content"]


def test_create_new_page(setup):
    client, forge = setup
    client.put("/api/pages/new/page.md", json={"body": "hi", "author": "n", "title": "Neu"})
    assert forge.calls[0]["exists"] is False and "title: Neu" in forge.calls[0]["content"]


def test_delete_and_protected_start_page(setup):
    client, forge = setup
    assert client.request("DELETE", "/api/pages/x.md", json={"author": "n"}).status_code == 200
    assert forge.calls[0]["action"] == "delete"
    assert client.request("DELETE", "/api/pages/index.md", json={"author": "n"}).status_code == 403


@pytest.mark.parametrize("bad", ["a:b.md", "../x.md", "a/.md", "x.txt", " a.md", "a /b.md"])
def test_invalid_paths_rejected(setup, bad):
    client, _ = setup
    r = client.put(f"/api/pages/{bad}", json={"body": "x", "author": "n"})
    assert r.status_code in (404, 422)


def test_validate_accepts_normal_paths():
    assert validate_page_path("HowTo/Mein Test.md") == "HowTo/Mein Test.md"
    with pytest.raises(ValueError):
        validate_page_path("a..md")


def test_not_configured(monkeypatch, tmp_path):
    monkeypatch.delenv("GITLAB_TOKEN", raising=False)
    monkeypatch.setattr(main, "CONTENT_DIR", tmp_path)
    client = TestClient(main.app)
    assert client.get("/api/config").json() == {"editable": False}
    r = client.put("/api/pages/a.md", json={"body": "x", "author": "n"})
    assert r.status_code == 503


def test_forge_from_env(monkeypatch):
    monkeypatch.setenv("GITLAB_TOKEN", "t")
    monkeypatch.setenv("GITLAB_PROJECT_ID", "group/proj")
    forge = GitLabForge.from_env()
    assert forge and forge.content_prefix == "content" and forge.target_branch == "main"


def test_gitlab_forge_commit_then_merge_request(monkeypatch):
    import json

    import httpx

    from app import gitlab

    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.raw_path.decode(), json.loads(request.content)))
        assert request.headers["PRIVATE-TOKEN"] == "secret"
        if request.url.path.endswith("/merge_requests"):
            return httpx.Response(201, json={"web_url": "https://gitlab.example/mr/7"})
        return httpx.Response(201, json={})

    real_client = httpx.Client
    monkeypatch.setattr(
        gitlab.httpx,
        "Client",
        lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw),
    )
    forge = GitLabForge("https://gitlab.example", "secret", "group/proj", "main", "content")
    url = forge.propose(action="save", path="a/b.md", content="x", author="Nico M.", exists=False)

    assert url == "https://gitlab.example/mr/7"
    (_, commit_path, commit), (_, _, mr) = seen
    assert commit_path == "/api/v4/projects/group%2Fproj/repository/commits"
    assert commit["start_branch"] == "main" and commit["branch"].startswith("wiki/nico-m-a-b-")
    assert commit["actions"] == [
        {"action": "create", "file_path": "content/a/b.md", "content": "x"}
    ]
    assert mr["source_branch"] == commit["branch"] and mr["target_branch"] == "main"


def test_local_mode_writes_and_deletes_files(tmp_path, monkeypatch):
    monkeypatch.setenv("WIKI_LOCAL_WRITE", "1")
    monkeypatch.setattr(main, "CONTENT_DIR", tmp_path)
    client = TestClient(main.app)
    assert client.get("/api/config").json() == {"editable": True}
    r = client.put("/api/pages/sub/neu.md", json={"body": "hallo", "author": "n", "title": "Neu"})
    assert r.json() == {"message": "Lokal gespeichert: sub/neu.md"}
    assert "title: Neu" in (tmp_path / "sub" / "neu.md").read_text()
    client.request("DELETE", "/api/pages/sub/neu.md", json={"author": "n"})
    assert not (tmp_path / "sub" / "neu.md").exists()


def test_sloppy_front_matter_does_not_break_the_wiki(tmp_path, monkeypatch):
    (tmp_path / "none.md").write_text("---\ntags:\ntitle:\n---\nx\n")
    (tmp_path / "scalar.md").write_text("---\ntags: demo\ntitle: [a, b]\n---\nx\n")
    (tmp_path / "broken.md").write_text("---\ntitle: [unclosed\n---\nx\n")
    (tmp_path / "ok.md").write_text("---\ntitle: Fine\n---\nx\n")
    monkeypatch.setattr(main, "CONTENT_DIR", tmp_path)
    data = {p["path"]: p for p in TestClient(main.app).get("/api/pages").json()}
    assert set(data) == {"none.md", "scalar.md", "ok.md"}
    assert data["none.md"]["tags"] == [] and data["none.md"]["title"] == "none"
    assert data["scalar.md"]["tags"] == ["demo"] and data["scalar.md"]["title"] == "scalar"


def test_save_preserves_unknown_front_matter_keys(setup, tmp_path):
    client, forge = setup
    page = main.CONTENT_DIR / "x.md"
    page.write_text("---\ntitle: X\ndate: 2026-01-02\naliases: [old]\ndraft: true\n---\nbody\n")
    client.put("/api/pages/x.md", json={"body": "new", "author": "n"})
    content = forge.calls[0]["content"]
    assert "aliases:" in content and "draft: true" in content and "date:" in content


def test_clean_author_strips_mentions_and_markup():
    from app.gitlab import clean_author

    assert clean_author("@all [x](http://e.vil) **b**") == "all xhttpe.vil b"
    assert clean_author("@@@") == "anonymous"
    assert clean_author("Zoë O'Neil-Müller") == "Zoë O'Neil-Müller"


def test_gitlab_errors_become_502_and_branch_is_cleaned_up(monkeypatch):
    import httpx

    from app import gitlab

    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path))
        if request.url.path.endswith("/merge_requests"):
            return httpx.Response(500, json={})
        return httpx.Response(201 if request.method == "POST" else 204, json={})

    real_client = httpx.Client
    monkeypatch.setattr(
        gitlab.httpx,
        "Client",
        lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw),
    )
    forge = GitLabForge("https://gitlab.example", "secret", "g/p", "main", "content")
    main.app.dependency_overrides[main.get_forge] = lambda: forge
    try:
        r = TestClient(main.app).put("/api/pages/a.md", json={"body": "x", "author": "n"})
    finally:
        main.app.dependency_overrides.clear()
    assert r.status_code == 502 and "merge request failed" in r.json()["detail"]
    assert seen[-1][0] == "DELETE" and "/repository/branches/" in seen[-1][1]


def test_expired_token_gives_502(monkeypatch):
    import httpx

    from app import gitlab

    real_client = httpx.Client
    monkeypatch.setattr(
        gitlab.httpx,
        "Client",
        lambda **kw: real_client(
            transport=httpx.MockTransport(lambda request: httpx.Response(401, json={})), **kw
        ),
    )
    forge = GitLabForge("https://gitlab.example", "bad", "g/p", "main", "content")
    main.app.dependency_overrides[main.get_forge] = lambda: forge
    try:
        r = TestClient(main.app).put("/api/pages/a.md", json={"body": "x", "author": "n"})
    finally:
        main.app.dependency_overrides.clear()
    assert r.status_code == 502 and "HTTP 401" in r.json()["detail"]
