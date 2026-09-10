import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.integrations.embeddings import cosine_similarity
from app.models.chunk import DocumentChunk
from app.models.document import Document


class DocumentChunkRepository:
    """Data access for DocumentChunk."""

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

    async def list_for_project(self, project_id: uuid.UUID) -> list[DocumentChunk]:
        """Every chunk in a project regardless of embedding status — used
        by keyword search (Phase 15), which doesn't need `embedding`."""
        result = await self._session.execute(
            select(DocumentChunk)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(Document.project_id == project_id)
            .options(selectinload(DocumentChunk.document))
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

    async def search_by_embedding(
        self, *, project_id: uuid.UUID, query_embedding: list[float], limit: int = 10
    ) -> list[tuple[DocumentChunk, float]]:
        """The `limit` chunks in `project_id` most similar to
        `query_embedding`, as (chunk, similarity) pairs — similarity in
        [-1, 1], higher is more similar, matching
        app.integrations.embeddings.cosine_similarity.

        On PostgreSQL this uses pgvector's native cosine-distance operator
        (`<=>`, indexed via the HNSW index from migration 0003) — the only
        path a real deployment ever takes. On any other dialect (reachable
        only in tests: SQLite has no pgvector) it falls back to computing
        cosine similarity in Python over every embedded chunk in the
        project — correct, just O(n), which is fine for a test database
        and never runs in production.
        """
        if self._session.bind is not None and self._session.bind.dialect.name == "postgresql":
            distance = DocumentChunk.embedding.cosine_distance(query_embedding)
            result = await self._session.execute(
                select(DocumentChunk, distance)
                .join(Document, Document.id == DocumentChunk.document_id)
                .where(Document.project_id == project_id, DocumentChunk.embedding.is_not(None))
                .options(selectinload(DocumentChunk.document))
                .order_by(distance)
                .limit(limit)
            )
            return [(chunk, 1 - dist) for chunk, dist in result.all()]

        result = await self._session.execute(
            select(DocumentChunk)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(Document.project_id == project_id, DocumentChunk.embedding.is_not(None))
            .options(selectinload(DocumentChunk.document))
        )
        scored = [
            (chunk, cosine_similarity(list(chunk.embedding), query_embedding))
            for chunk in result.scalars().all()
        ]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored[:limit]
