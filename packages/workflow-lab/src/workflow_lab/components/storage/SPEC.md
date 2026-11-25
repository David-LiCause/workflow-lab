# storage

## 1. Purpose

Read, write and list files through one interface, rooted at a base location. The root is a local
path today and an `s3://` or `gs://` URL later, with no change to calling code.

## 2. Interface

```python
class PathEscapesRootError(ValueError): ...


class Storage:
    def __init__(self, root: str | os.PathLike[str]) -> None: ...

    root: str  # the root as given (read-only property)

    def read_text(self, path: str) -> str: ...
    def write_text(self, path: str, text: str) -> None: ...
    def read_bytes(self, path: str) -> bytes: ...
    def write_bytes(self, path: str, data: bytes) -> None: ...
    def exists(self, path: str) -> bool: ...
    def list(self, pattern: str = "**/*") -> list[str]: ...
    def latest(self, pattern: str) -> str | None: ...
```

## 3. Inputs and outputs

- `root`: a local path (`"data"`, `Path("data")`, `"~/data"`) or a URL (`"memory://x"`,
  later `"s3://bucket/prefix"`, `"gs://bucket/prefix"`). A string with no `://` is a local path.
- `path`: a string relative to the root, using `/` separators (`"research/incumbents_2026-11-20.md"`).
- `pattern`: a glob relative to the root (`"research/incumbents_*.md"`, `"snapshots/**/*.md"`).
- `list` and `latest` return paths relative to the root, with `/` separators.
- Text methods use `str`; byte methods use `bytes`. Write methods return `None`.

## 4. Behavior rules

- **R1** All paths are relative to the root. `read_*`, `write_*`, `exists`, `list` and `latest`
  resolve against it.
- **R2** A path or pattern that escapes the root raises `PathEscapesRootError`. That covers
  `..` segments that climb above the root (`"../x"`, `"a/../../x"`) and absolute paths
  (`"/etc/passwd"`). `"a/../b"` stays inside the root and is allowed.
- **R3** An empty path or pattern, or one that normalizes to the root itself (`""`, `"."`,
  `"a/.."`), is rejected with `PathEscapesRootError` by every method.
- **R4** `write_text` and `write_bytes` create missing parent folders and overwrite an existing file.
- **R5** `read_text` and `read_bytes` on a path that is not an existing file raise
  `FileNotFoundError`, with a message that names the relative path and the root.
- **R6** Text is UTF-8. `write_text` encodes as UTF-8 and `read_text` decodes as UTF-8, with no
  newline translation. Non-ASCII text round-trips unchanged.
- **R7** `read_bytes` returns exactly the bytes `write_bytes` stored.
- **R8** `exists` is `True` for an existing file and `False` for a missing path or a directory.
- **R9** `list(pattern)` returns the files matching the glob, relative to the root, sorted
  lexicographically. Directories are not returned. No matches, or a root that does not exist yet,
  gives `[]`. The default pattern lists every file under the root.
- **R10** `latest(pattern)` returns the match whose filename contains the newest `YYYY-MM-DD`
  date, or `None` if nothing matches. The date is the first valid `YYYY-MM-DD` in the filename (not the
  folder names). Files with no valid date are ignored. Ties go to the path that sorts last.
- **R11** The same code works against any fsspec backend: a local path and a URL such as
  `memory://` give identical results for R1 to R10.
- **R12** If `fsspec` is not installed, constructing `Storage` raises `ImportError` with a message
  that says to install the `storage` extra.

## 5. Errors

| Raised | When |
| --- | --- |
| `PathEscapesRootError` (a `ValueError`) | R2, R3 |
| `FileNotFoundError` | R5 |
| `ImportError` | R12 |
| `UnicodeDecodeError` | `read_text` on a file that is not valid UTF-8 (not handled) |

Backend errors (permissions, network) propagate unchanged.

## 6. Config and dependencies

- Optional extra `storage`: `fsspec`. Install with `uv sync --extra storage`.
- No env vars. Cloud backends (`s3fs`, `gcsfs`) and their credentials are the caller's to install
  and configure, and are not installed by this project yet.

## 7. Out of scope

Downloading from URLs, unzipping, caching, versioning, and managing cloud credentials.
