import logging
from dataclasses import dataclass, field
from pathlib import Path

import frontmatter

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Page:
    path: str
    title: str
    tags: list[str]
    body: str
    meta: dict = field(default_factory=dict)


def normalize_tags(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list | tuple | set):
        return [str(v) for v in value if v is not None]
    return [str(value)]


def normalize_title(value: object, fallback: str) -> str:
    if isinstance(value, str | int | float) and str(value).strip():
        return str(value)
    return fallback


def load_pages(root: Path) -> list[Page]:
    pages = []
    for file in sorted(root.rglob("*.md")):
        rel = file.relative_to(root).as_posix()
        try:
            post = frontmatter.load(file)
        except Exception:
            log.warning("skipping %s: front matter could not be parsed", rel, exc_info=True)
            continue
        pages.append(
            Page(
                path=rel,
                title=normalize_title(post.get("title"), file.stem),
                tags=normalize_tags(post.get("tags")),
                body=post.content,
                meta=dict(post.metadata),
            )
        )
    return pages


def read_page(root: Path, rel: str) -> Page | None:
    target = (root / rel).resolve()
    if not target.is_relative_to(root.resolve()) or target.suffix != ".md" or not target.is_file():
        return None
    wanted = target.relative_to(root.resolve()).as_posix()
    return next((p for p in load_pages(root) if p.path == wanted), None)
