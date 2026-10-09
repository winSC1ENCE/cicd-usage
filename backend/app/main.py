import os
from pathlib import Path
from typing import Annotated

import frontmatter
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .content import load_pages, read_page
from .gitlab import Forge, ForgeError, GitLabForge, validate_page_path
from .graph import backlinks, build_graph
from .local import LocalForge

CONTENT_DIR = Path(os.environ.get("CONTENT_DIR", "content"))
STATIC_DIR = Path(os.environ.get("STATIC_DIR", "static"))

app = FastAPI(title="Wiki")


def get_forge() -> Forge | None:
    if os.environ.get("WIKI_LOCAL_WRITE") == "1":
        return LocalForge(CONTENT_DIR)
    return GitLabForge.from_env()


def outcome(result: str) -> dict:
    return {"merge_request": result} if result.startswith("http") else {"message": result}


ForgeDep = Annotated[Forge | None, Depends(get_forge)]


class SaveRequest(BaseModel):
    body: str = Field(max_length=500_000)
    author: str = Field(min_length=1, max_length=60)
    title: str | None = Field(default=None, max_length=200)
    tags: list[str] | None = None


class DeleteRequest(BaseModel):
    author: str = Field(min_length=1, max_length=60)


def require_forge(forge: Forge | None) -> Forge:
    if forge is None:
        raise HTTPException(503, "editing is not configured")
    return forge


def propose(forge: Forge, **kwargs) -> str:
    try:
        return forge.propose(**kwargs)
    except ForgeError as exc:
        raise HTTPException(502, str(exc)) from exc


def checked_path(path: str) -> str:
    try:
        return validate_page_path(path)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get("/api/config")
def config(forge: ForgeDep) -> dict:
    return {"editable": forge is not None}


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/pages")
def pages() -> list[dict]:
    return [{"path": p.path, "title": p.title, "tags": p.tags} for p in load_pages(CONTENT_DIR)]


@app.get("/api/graph")
def graph() -> dict:
    return build_graph(load_pages(CONTENT_DIR))


@app.get("/api/search")
def search(q: str = Query(min_length=2, max_length=100)) -> list[dict]:
    needle = q.lower()
    results = []
    for p in load_pages(CONTENT_DIR):
        idx = p.body.lower().find(needle)
        if needle in p.title.lower() or idx >= 0:
            snippet = p.body[max(0, idx - 40) : idx + 80].replace("\n", " ") if idx >= 0 else ""
            results.append({"path": p.path, "title": p.title, "snippet": snippet})
    return results


@app.put("/api/pages/{path:path}")
def save_page(path: str, req: SaveRequest, forge: ForgeDep) -> dict:
    forge = require_forge(forge)
    path = checked_path(path)
    existing = read_page(CONTENT_DIR, path)
    meta = dict(existing.meta) if existing else {}
    if req.title is not None:
        meta["title"] = req.title
    if req.tags is not None:
        meta["tags"] = req.tags
    text = frontmatter.dumps(frontmatter.Post(req.body.rstrip() + "\n", **meta)) + "\n"
    url = propose(
        forge,
        action="save",
        path=path,
        content=text,
        author=req.author,
        exists=existing is not None,
    )
    return outcome(url)


@app.delete("/api/pages/{path:path}")
def delete_page(path: str, req: DeleteRequest, forge: ForgeDep) -> dict:
    forge = require_forge(forge)
    path = checked_path(path)
    if read_page(CONTENT_DIR, path) is None:
        raise HTTPException(404, "page not found")
    if path == "index.md":
        raise HTTPException(403, "the start page cannot be deleted")
    url = propose(forge, action="delete", path=path, content=None, author=req.author, exists=True)
    return outcome(url)


@app.get("/api/pages/{path:path}")
def page(path: str) -> dict:
    pages = load_pages(CONTENT_DIR)
    found = next((p for p in pages if p.path == path), None)
    if found is None or read_page(CONTENT_DIR, path) is None:
        raise HTTPException(404, "page not found")
    return {
        "path": found.path,
        "title": found.title,
        "tags": found.tags,
        "body": found.body,
        "backlinks": backlinks(build_graph(pages), found.path),
    }


if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
