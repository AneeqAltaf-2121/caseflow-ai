"""Object storage abstraction.

Routes/services never touch the filesystem or boto3 directly — they depend
on `StorageBackend` so the same document-upload code runs against local
disk in development and S3 in production (see docs/architecture.md).
"""

from pathlib import Path
from typing import Protocol

from app.config import Settings


class StorageBackend(Protocol):
    async def put(self, *, key: str, data: bytes) -> None: ...

    async def get(self, *, key: str) -> bytes: ...

    async def delete(self, *, key: str) -> None: ...


class LocalStorageBackend:
    """Writes under `settings.local_storage_path`. Dev/test default — no
    AWS account needed to exercise the full upload/ingestion pipeline."""

    def __init__(self, settings: Settings) -> None:
        self._root = Path(settings.local_storage_path)

    def _path_for(self, key: str) -> Path:
        # Reject absolute paths and ".." segments so a crafted storage key
        # can never escape the storage root.
        candidate = (self._root / key).resolve()
        root = self._root.resolve()
        if root not in candidate.parents and candidate != root:
            raise ValueError(f"Storage key resolves outside storage root: {key!r}")
        return candidate

    async def put(self, *, key: str, data: bytes) -> None:
        path = self._path_for(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    async def get(self, *, key: str) -> bytes:
        return self._path_for(key).read_bytes()

    async def delete(self, *, key: str) -> None:
        self._path_for(key).unlink(missing_ok=True)


class S3StorageBackend:
    """Boto3-backed storage for staging/production (see infra/aws). Also
    used for local MinIO via `settings.s3_endpoint_url`."""

    def __init__(self, settings: Settings) -> None:
        import boto3

        self._bucket = settings.s3_bucket
        client_kwargs: dict[str, str] = {}
        if settings.aws_region:
            client_kwargs["region_name"] = settings.aws_region
        if settings.s3_endpoint_url:
            client_kwargs["endpoint_url"] = settings.s3_endpoint_url
        if settings.aws_access_key_id:
            client_kwargs["aws_access_key_id"] = settings.aws_access_key_id
        if settings.aws_secret_access_key:
            client_kwargs["aws_secret_access_key"] = settings.aws_secret_access_key
        self._client = boto3.client("s3", **client_kwargs)

    async def put(self, *, key: str, data: bytes) -> None:
        # boto3 is sync; document sizes here are small enough (validated at
        # the API layer) that running it inline is acceptable. A worker-side
        # ingestion path (Phase 8) offloads larger transfers to a thread.
        self._client.put_object(Bucket=self._bucket, Key=key, Body=data)

    async def get(self, *, key: str) -> bytes:
        response = self._client.get_object(Bucket=self._bucket, Key=key)
        return response["Body"].read()

    async def delete(self, *, key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=key)


def get_storage_backend(settings: Settings) -> StorageBackend:
    if settings.storage_backend == "s3":
        return S3StorageBackend(settings)
    return LocalStorageBackend(settings)
