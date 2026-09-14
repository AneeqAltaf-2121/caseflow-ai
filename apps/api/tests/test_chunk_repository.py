import uuid

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


async def test_search_by_embedding_orders_by_similarity_and_scopes_to_project(
    db_session: AsyncSession,
) -> None:
    user = await UserRepository(db_session).create(email="search@x.com", display_name="Search")
    org = await OrganizationRepository(db_session).create(name="SearchCo", slug="searchco")
    project_service = ProjectService(ProjectRepository(db_session))
    project_a = await project_service.create_project(
        organization_id=org.id, name="A", description=None, created_by=user.id
    )
    project_b = await project_service.create_project(
        organization_id=org.id, name="B", description=None, created_by=user.id
    )
    document_repository = DocumentRepository(db_session)

    doc_a = await document_repository.create(
        project_id=project_a.id,
        filename="a.txt",
        content_type="text/plain",
        size_bytes=1,
        checksum_sha256="a",
        storage_key="a.txt",
        uploaded_by=user.id,
    )
    doc_b = await document_repository.create(
        project_id=project_b.id,
        filename="b.txt",
        content_type="text/plain",
        size_bytes=1,
        checksum_sha256="b",
        storage_key="b.txt",
        uploaded_by=user.id,
    )
    await db_session.commit()
    doc_a = await document_repository.get_by_id(doc_a.id)
    doc_b = await document_repository.get_by_id(doc_b.id)

    repository = DocumentChunkRepository(db_session)
    close_match = _chunk(doc_a, text="close match", embedding=[1.0, 0.0, 0.0])
    far_match = _chunk(doc_a, text="far match", embedding=[0.0, 1.0, 0.0])
    other_project_chunk = _chunk(doc_b, text="other project", embedding=[1.0, 0.0, 0.0])
    await repository.bulk_create([far_match, close_match, other_project_chunk])
    await db_session.commit()

    results = await repository.search_by_embedding(
        project_id=project_a.id, query_embedding=[1.0, 0.0, 0.0], limit=10
    )

    assert [chunk.text for chunk, _score in results] == ["close match", "far match"]
    assert results[0][1] == pytest.approx(1.0)
    assert results[1][1] == pytest.approx(0.0)


async def test_get_many_by_ids_with_document_returns_a_dict_keyed_by_id(
    db_session: AsyncSession,
) -> None:
    document = await _seed_document(db_session)
    repository = DocumentChunkRepository(db_session)
    first, second = await repository.bulk_create(
        [_chunk(document, text="first chunk"), _chunk(document, page_number=2, text="second chunk")]
    )
    await db_session.commit()

    found = await repository.get_many_by_ids_with_document([first.id, second.id])

    assert set(found) == {first.id, second.id}
    assert found[first.id].text == "first chunk"
    # `.document` is eager-loaded, same as get_by_id_with_document, so a
    # caller building HybridSearchResultRead never triggers a lazy load.
    assert found[first.id].document.filename == "notes.txt"


async def test_get_many_by_ids_with_document_silently_omits_ids_that_do_not_exist(
    db_session: AsyncSession,
) -> None:
    document = await _seed_document(db_session)
    repository = DocumentChunkRepository(db_session)
    [real_chunk] = await repository.bulk_create([_chunk(document)])
    await db_session.commit()

    found = await repository.get_many_by_ids_with_document([real_chunk.id, uuid.uuid4()])

    assert set(found) == {real_chunk.id}


async def test_get_many_by_ids_with_document_returns_empty_dict_for_empty_input(
    db_session: AsyncSession,
) -> None:
    repository = DocumentChunkRepository(db_session)
    assert await repository.get_many_by_ids_with_document([]) == {}


async def test_embedding_round_trips_as_a_float_list(db_session: AsyncSession) -> None:
    document = await _seed_document(db_session)
    repository = DocumentChunkRepository(db_session)
    vector = [float(i) / 384 for i in range(384)]

    created = await repository.bulk_create([_chunk(document, embedding=vector)])
    await db_session.commit()

    fetched = await repository.get_by_id(created[0].id)
    assert fetched is not None
    assert list(fetched.embedding) == pytest.approx(vector)
