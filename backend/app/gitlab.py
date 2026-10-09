import os
import re
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import quote

import httpx


class ForgeError(Exception):
    """The forge rejected or failed a request; the message is safe to show to the user."""


def clean_author(author: str) -> str:
    """Make a client-supplied name safe for a Markdown description (no mentions, links, markup)."""
    cleaned = re.sub(r"[^\w .'-]", "", author, flags=re.UNICODE).strip()
    return cleaned[:60] or "anonymous"


FORBIDDEN = re.compile(r'[:*?"<>|\\\x00-\x1f]')


def validate_page_path(path: str) -> str:
    if (
        not path.endswith(".md")
        or path.startswith("/")
        or len(path) > 200
        or FORBIDDEN.search(path)
    ):
        raise ValueError("invalid page path")
    *folders, name = path.split("/")
    stem = name[:-3]
    for seg in [*folders, stem]:
        if seg in ("", ".", "..") or seg != seg.strip() or seg.endswith(".") or len(seg) > 80:
            raise ValueError("invalid page path")
    return path


def describe(exc: httpx.HTTPError) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code}"
    return type(exc).__name__


class Forge(Protocol):
    def propose(
        self, *, action: str, path: str, content: str | None, author: str, exists: bool
    ) -> str: ...


@dataclass
class GitLabForge:
    url: str
    token: str
    project_id: str
    target_branch: str
    content_prefix: str

    @classmethod
    def from_env(cls) -> "GitLabForge | None":
        token, project = os.environ.get("GITLAB_TOKEN"), os.environ.get("GITLAB_PROJECT_ID")
        if not token or not project:
            return None
        return cls(
            url=os.environ.get("GITLAB_URL", "https://gitlab.com").rstrip("/"),
            token=token,
            project_id=project,
            target_branch=os.environ.get("GITLAB_TARGET_BRANCH", "main"),
            content_prefix=os.environ.get("GITLAB_CONTENT_PREFIX", "content").strip("/"),
        )

    def propose(
        self, *, action: str, path: str, content: str | None, author: str, exists: bool
    ) -> str:
        repo_path = f"{self.content_prefix}/{path}" if self.content_prefix else path
        verb = {"save": "update" if exists else "create", "delete": "delete"}[action]
        branch = f"wiki/{re.sub(r'[^a-z0-9]+', '-', author.lower()).strip('-') or 'anon'}"
        branch += f"-{re.sub(r'[^a-z0-9]+', '-', path[:-3].lower()).strip('-')}"
        branch += f"-{os.urandom(3).hex()}"
        title = f"wiki: {verb} {path}"
        file_action: dict = {"action": verb, "file_path": repo_path}
        if content is not None:
            file_action["content"] = content
        base = f"{self.url}/api/v4/projects/{quote(self.project_id, safe='')}"
        author = clean_author(author)
        with httpx.Client(headers={"PRIVATE-TOKEN": self.token}, timeout=20) as client:
            try:
                client.post(
                    f"{base}/repository/commits",
                    json={
                        "branch": branch,
                        "start_branch": self.target_branch,
                        "commit_message": title,
                        "actions": [file_action],
                    },
                ).raise_for_status()
            except httpx.HTTPError as exc:
                raise ForgeError(f"GitLab commit failed: {describe(exc)}") from exc
            try:
                mr = client.post(
                    f"{base}/merge_requests",
                    json={
                        "source_branch": branch,
                        "target_branch": self.target_branch,
                        "title": title,
                        "description": f"Created via the wiki frontend by `{author}`.",
                        "remove_source_branch": True,
                        "squash": True,
                    },
                )
                mr.raise_for_status()
                return mr.json()["web_url"]
            except httpx.HTTPError as exc:
                try:
                    client.delete(f"{base}/repository/branches/{quote(branch, safe='')}")
                except httpx.HTTPError:
                    pass
                raise ForgeError(f"GitLab merge request failed: {describe(exc)}") from exc
