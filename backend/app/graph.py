import posixpath
import re
from urllib.parse import unquote

from .content import Page

WIKILINK = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")
MDLINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
CODE = re.compile(r"```.*?```|`[^`\n]*`", re.DOTALL)


def _strip_md(s: str) -> str:
    return s[:-3] if s.lower().endswith(".md") else s


def resolve_wikilink(target: str, pages: list[Page]) -> str | None:
    t = _strip_md(target.strip()).lower()
    for p in pages:
        if _strip_md(p.path).lower() == t:
            return p.path
    for p in pages:
        if _strip_md(p.path).rsplit("/", 1)[-1].lower() == t or p.title.lower() == t:
            return p.path
    return None


def resolve_relative(href: str, current: str) -> str | None:
    if re.match(r"^[a-z][a-z0-9+.-]*:|^#|^//", href, re.IGNORECASE):
        return None
    file = unquote(href.split("#", 1)[0])
    if not file.lower().endswith(".md"):
        return None
    resolved = posixpath.normpath(posixpath.join(posixpath.dirname(current), file))
    return None if resolved.startswith("..") else resolved


def build_graph(pages: list[Page]) -> dict:
    known = {p.path for p in pages}
    edges: set[tuple[str, str]] = set()
    for p in pages:
        text = CODE.sub("", p.body)
        targets = [resolve_wikilink(m, pages) for m in WIKILINK.findall(text)]
        targets += [resolve_relative(m, p.path) for m in MDLINK.findall(text)]
        for t in targets:
            if t and t in known and t != p.path:
                edges.add((p.path, t))
    return {
        "nodes": [{"id": p.path, "title": p.title, "tags": p.tags} for p in pages],
        "links": [{"source": s, "target": t} for s, t in sorted(edges)],
    }


def backlinks(graph: dict, path: str) -> list[str]:
    return sorted(link["source"] for link in graph["links"] if link["target"] == path)
