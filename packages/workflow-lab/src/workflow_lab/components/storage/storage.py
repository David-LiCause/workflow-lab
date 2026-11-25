"""File storage behind one interface. See ``SPEC.md`` for the rules."""

from __future__ import annotations

import os
import posixpath
import re
from datetime import date

_DATE_RE = re.compile(r"(?<!\d)(\d{4}-\d{2}-\d{2})(?!\d)")


class PathEscapesRootError(ValueError):
    """A path or pattern resolves outside the storage root."""


def _normalize(path: str) -> str:
    """Return ``path`` normalized and relative to the root, or raise PathEscapesRootError."""
    if path.startswith("/"):
        raise PathEscapesRootError(f"Absolute path not allowed: {path!r}")
    norm = posixpath.normpath(path) if path else "."
    if norm == ".." or norm.startswith("../"):
        raise PathEscapesRootError(f"Path escapes the storage root: {path!r}")
    if norm == ".":
        raise PathEscapesRootError(f"Path must name something under the root, got {path!r}")
    return norm


def _filename_date(path: str) -> date | None:
    """First valid YYYY-MM-DD in the file's name (not its folders), or None."""
    for match in _DATE_RE.finditer(posixpath.basename(path)):
        try:
            return date.fromisoformat(match.group(1))
        except ValueError:
            continue
    return None


class Storage:
    """Read, write and list files relative to a root path or URL."""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        """Root is a local path or an fsspec URL (``memory://x``, later ``s3://bucket/p``)."""
        try:
            import fsspec.core
        except ImportError as exc:
            raise ImportError(
                "Storage needs fsspec. Install the 'storage' extra: uv sync --extra storage"
            ) from exc

        self._root = os.fspath(root)
        location = self._root if "://" in self._root else os.path.expanduser(self._root)
        self._fs, base = fsspec.core.url_to_fs(location)
        self._base: str = base.rstrip("/")

    @property
    def root(self) -> str:
        """The root as given."""
        return self._root

    def _full(self, path: str) -> str:
        return f"{self._base}/{_normalize(path)}"

    def read_bytes(self, path: str) -> bytes:
        """Read a file's bytes. Raises FileNotFoundError if it is missing."""
        full = self._full(path)
        if not self._fs.isfile(full):
            raise FileNotFoundError(f"No such file {path!r} under storage root {self._root!r}")
        return self._fs.cat_file(full)

    def read_text(self, path: str) -> str:
        """Read a UTF-8 text file. Raises FileNotFoundError if it is missing."""
        return self.read_bytes(path).decode("utf-8")

    def write_bytes(self, path: str, data: bytes) -> None:
        """Write bytes, creating parent folders and overwriting any existing file."""
        full = self._full(path)
        self._fs.makedirs(posixpath.dirname(full), exist_ok=True)
        self._fs.pipe_file(full, data)

    def write_text(self, path: str, text: str) -> None:
        """Write UTF-8 text, creating parent folders and overwriting any existing file."""
        self.write_bytes(path, text.encode("utf-8"))

    def exists(self, path: str) -> bool:
        """True if ``path`` is an existing file (False for a missing path or a directory)."""
        return bool(self._fs.isfile(self._full(path)))

    def list(self, pattern: str = "**/*") -> list[str]:
        """Files matching a glob, as sorted paths relative to the root."""
        prefix = f"{self._base}/"
        found = self._fs.glob(self._full(pattern), detail=True)
        return sorted(
            p.removeprefix(prefix)
            for p, info in found.items()
            if info.get("type") == "file" and p.startswith(prefix)
        )

    def latest(self, pattern: str) -> str | None:
        """Match with the newest YYYY-MM-DD in its filename, or None if there is no match."""
        dated = [(d, p) for p in self.list(pattern) if (d := _filename_date(p)) is not None]
        return max(dated)[1] if dated else None
