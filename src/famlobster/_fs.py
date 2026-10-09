"""Filesystem helpers."""

import os
from pathlib import Path


def write_private(path: str | os.PathLike[str], text: str) -> None:
    """Write text to path, readable and writable by the owner only (0600).

    The mode is applied on creation and re-applied to files that already exist,
    so files created by older versions with looser permissions get tightened.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.chmod(p, 0o600)
