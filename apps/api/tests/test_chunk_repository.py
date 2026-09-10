import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chunk import DocumentChunk
from app.repositories.chunk_repository import DocumentChunkRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.project_repository import ProjectRepository
from app.repositories.user_repository import UserRepository
from app.services.project_service import ProjectService

pytestmark = pytest.mark.asyncio


async def _seed_document(db_session: AsyncSession):
    user = await UserRepository(db_session).create(email="chunks@x.com", display_name="Chunks")
    org = await OrganizationRepository(db_session).create(name="ChunkCo", slug="chunkco")
    project = await ProjectService(ProjectRepository(db_session)).create_project(
        organization_id=org.id, name="Chunking", description=None, created_by=user.id
    )
    document_repository = DocumentRepository(db_session)
    document = await document_repository.create(
        project_id=project.id,
        filename="notes.txt",
        content_type="text/plain",
        size_bytes=10,
        checksum_sha256="abc",
        storage_key="docs/notes.txt",
        uploaded_by=user.id,
    )
    await db_session.commit()
    # get_by_id eager-loads `versions` (see DocumentRepository) — `create`
    # doesn't, so re-fetch rather than accessing the lazy collection here.
    return await document_repository.get_by_id(document.id)


def _chunk(document, *, page_number=1, text="hello", embedding=None) -> DocumentChunk:
    return DocumentChunk(
        document_id=document.id,
        document_version_id=document.versions[0].id,
        page_number=page_number,
        section=None,
        text=text,
        token_count=len(text.split()),
        start_offset=0,
        end_offset=len(text),
        embedding=embedding,
        chunk_metadata={},
    )


async def test_bulk_create_and_list_for_document(db_session: AsyncSession) -> None:
    document = await _seed_document(db_session)
    repository = DocumentChunkRepository(db_session)

    await repository.bulk_create(
        [
            _chunk(document, page_number=1, text="first chunk"),
            _chunk(document, page_number=2, text="second chunk"),
        ]
    )
    await db_session.commit()

    chunks = await repository.list_for_document(document.id)
    assert [c.page_number for c in chunks] == [1, 2]
    assert chunks[0].text == "first chunk"


async def test_list_unembedded_returns_only_null_embedding_chunks(
    db_session: AsyncSession,
) -> None:
    document = await _seed_document(db_session)
    repository = DocumentChunkRepository(db_session)

    embedded = _chunk(document, text="already embedded", embedding=[0.1] * 384)
    pending = _chunk(document, text="awaiting embedding", embedding=None)
    await repository.bulk_create([embedded, pending])
    await db_session.commit()

    unembedded = await repository.list_unembedded()
    assert len(unembedded) == 1
    assert unembedded[0].text == "awaiting embedding"


async def test_delete_for_document_removes_all_its_chunks(db_session: AsyncSession) -> None:
    document = await _seed_document(db_session)
    repository = DocumentChunkRepository(db_session)

    await repository.bulk_create([_chunk(document), _chunk(document, page_number=2)])
    await db_session.commit()

    await repository.delete_for_document(document.id)
    await db_session.commit()

    assert await repository.list_for_document(document.id) == []


async def test_embedding_round_trips_as_a_float_list(db_session: AsyncSession) -> None:
    document = await _seed_document(db_session)
    repository = DocumentChunkRepository(db_session)
    vector = [float(i) / 384 for i in range(384)]

    created = await repository.bulk_create([_chunk(document, embedding=vector)])
    await db_session.commit()

    fetched = await repository.get_by_id(created[0].id)
    assert fetched is not None
    assert list(fetched.embedding) == pytest.approx(vector)
