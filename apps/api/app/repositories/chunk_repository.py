import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chunk import DocumentChunk


class DocumentChunkRepository:
    """Data access for DocumentChunk. Similarity search
    (`search_by_embedding`) lands in Phase 14 alongside the retrieval
    service that needs it — this phase only needs chunks to exist and be
    queryable by document/version, ahead of the embedding pipeline
    (Phase 13) populating `embedding`.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def bulk_create(self, chunks: list[DocumentChunk]) -> list[DocumentChunk]:
        self._session.add_all(chunks)
        await self._session.flush()
        return chunks

    async def get_by_id(self, chunk_id: uuid.UUID) -> DocumentChunk | None:
        return await self._session.get(DocumentChunk, chunk_id)

    async def list_for_document(self, document_id: uuid.UUID) -> list[DocumentChunk]:
        result = await self._session.execute(
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.page_number, DocumentChunk.start_offset)
        )
        return list(result.scalars().all())

    async def list_for_version(self, document_version_id: uuid.UUID) -> list[DocumentChunk]:
        result = await self._session.execute(
            select(DocumentChunk)
            .where(DocumentChunk.document_version_id == document_version_id)
            .order_by(DocumentChunk.page_number, DocumentChunk.start_offset)
        )
        return list(result.scalars().all())

    async def list_unembedded(self, *, limit: int = 100) -> list[DocumentChunk]:
        """Chunks awaiting the embedding pipeline (Phase 13)."""
        result = await self._session.execute(
            select(DocumentChunk).where(DocumentChunk.embedding.is_(None)).limit(limit)
        )
        return list(result.scalars().all())

    async def delete_for_document(self, document_id: uuid.UUID) -> None:
        """Used before re-chunking a re-uploaded document (a new
        DocumentVersion) so stale chunks from the previous version don't
        linger and get retrieved alongside current ones."""
        chunks = await self.list_for_document(document_id)
        for chunk in chunks:
            await self._session.delete(chunk)
        await self._session.flush()
