# 005 — Storage abstraction over local disk / S3

## Status
Accepted

## Context
Uploaded files must live outside PostgreSQL (see ADR 001), and development
needs to work without an AWS account while production needs S3. The app
code (upload, download, future ingestion) shouldn't be written twice or
branch on environment.

## Decision
Define a small `StorageBackend` protocol (`app/integrations/storage.py`)
with `put`/`get`/`delete`, and two implementations: `LocalStorageBackend`
(writes under a configured directory on disk) and `S3StorageBackend`
(boto3, also usable against a local S3-compatible endpoint like MinIO via
`S3_ENDPOINT_URL`). `settings.storage_backend` selects which one the app
constructs at startup; every route/service depends on the protocol only.

Documents are content-versioned: each upload/re-upload creates a new
`DocumentVersion` row pointing at its own storage key rather than
overwriting the previous file, so ingestion output and citations always
resolve to the exact bytes they were computed from.

## Rationale
- Matches the pattern already used for LLM/embedding providers
  (`app/integrations/`) and Redis/DB access: business logic depends on a
  narrow interface, not a specific vendor SDK.
- `LocalStorageBackend` means the full upload -> ingest -> retrieve ->
  cite pipeline is exercisable in tests and local dev with zero AWS
  dependency; `S3StorageBackend` is the same interface for staging/prod
  (infra/aws provisions the bucket — see ADR 006/AWS Terraform).
- Storage keys are namespaced per project and given a random component
  (`projects/{project_id}/{uuid}/{filename}`) rather than derived from
  user-supplied filenames alone, so a malicious filename can't collide
  with or overwrite another document's key. `LocalStorageBackend`
  additionally rejects any resolved path outside its storage root.

## Consequences
- Switching `STORAGE_BACKEND=s3` requires no code change, only
  `AWS_*`/`S3_BUCKET` configuration.
- Deleting a Document should eventually delete its S3 objects too (not yet
  implemented — there is no document-delete endpoint yet); tracked for
  when that endpoint is added.
- Byte-range/streaming reads aren't supported by this interface yet;
  `get()` returns the full object. Acceptable at current upload size limits
  (`MAX_UPLOAD_SIZE_MB`), revisit if large-file support is added.
