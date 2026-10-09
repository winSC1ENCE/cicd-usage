from dataclasses import dataclass
from pathlib import Path


@dataclass
class LocalForge:
    """Writes straight into the content directory; for local testing only."""

    root: Path

    def propose(
        self, *, action: str, path: str, content: str | None, author: str, exists: bool
    ) -> str:
        root = self.root.resolve()
        target = (root / path).resolve()
        if not target.is_relative_to(root):
            raise ValueError("invalid page path")
        if action == "delete":
            target.unlink(missing_ok=True)
            return f"Lokal gelöscht: {path}"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content or "", encoding="utf-8")
        return f"Lokal gespeichert: {path}"
