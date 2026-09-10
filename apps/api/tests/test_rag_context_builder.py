import uuid

from app.models.chunk import DocumentChunk
from app.models.document import Document, DocumentStatus
from app.rag.context_builder import build_context


def _chunk(text: str, *, page_number: int, filename: str) -> DocumentChunk:
    document = Document(
        id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        filename=filename,
        content_type="text/plain",
        size_bytes=1,
        checksum_sha256="x",
        status=DocumentStatus.READY,
        storage_key="x",
        uploaded_by=uuid.uuid4(),
    )
    chunk = DocumentChunk(
        id=uuid.uuid4(),
        document_id=document.id,
        document_version_id=uuid.uuid4(),
        page_number=page_number,
        section=None,
        text=text,
        token_count=len(text.split()),
        start_offset=0,
        end_offset=len(text),
        embedding=None,
        chunk_metadata={},
    )
    chunk.document = document
    return chunk


def test_build_context_numbers_sources_starting_at_one() -> None:
    context = build_context(
        [
            _chunk("First passage.", page_number=1, filename="a.txt"),
            _chunk("Second passage.", page_number=2, filename="b.txt"),
        ]
    )
    assert context.startswith("[1] (from a.txt, page 1)\nFirst passage.")
    assert "[2] (from b.txt, page 2)\nSecond passage." in context


def test_build_context_empty_list_is_empty_string() -> None:
    assert build_context([]) == ""
