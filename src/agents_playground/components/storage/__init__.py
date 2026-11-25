"""File storage behind one interface: local paths now, ``s3://`` / ``gs://`` later.

See ``SPEC.md`` for the rules.
"""

from agents_playground.components.storage.storage import PathEscapesRootError, Storage

__all__ = ["PathEscapesRootError", "Storage"]
