from pathlib import Path

import pytest

from app.config import Settings
from app.integrations.storage import LocalStorageBackend


async def test_local_backend_put_get_delete_round_trip(tmp_path: Path) -> None:
    backend = LocalStorageBackend(Settings(local_storage_path=str(tmp_path)))

    await backend.put(key="projects/abc/file.txt", data=b"hello world")
    assert await backend.get(key="projects/abc/file.txt") == b"hello world"

    await backend.delete(key="projects/abc/file.txt")
    with pytest.raises(FileNotFoundError):
        await backend.get(key="projects/abc/file.txt")


async def test_local_backend_rejects_path_traversal(tmp_path: Path) -> None:
    backend = LocalStorageBackend(Settings(local_storage_path=str(tmp_path)))

    with pytest.raises(ValueError):
        await backend.put(key="../../etc/passwd", data=b"pwned")
