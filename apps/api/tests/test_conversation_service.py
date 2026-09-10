import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import ForbiddenError, NotFoundError
from app.integrations.embeddings import LocalEmbeddingProvider
from app.integrations.generation import MockGenerationProvider
from app.models.chunk import DocumentChunk
from app.models.conversation import MessageRole
from app.models.project import ProjectRole
from app.rag.service import RagService
from app.repositories.chunk_repository import DocumentChunkRepository
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.model_run_repository import ModelRunRepository
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.project_repository import ProjectRepository
from app.repositories.prompt_version_repository import PromptVersionRepository
from app.repositories.user_repository import UserRepository
from app.retrieval.reranker import MockReranker
from app.services.conversation_service import ConversationService
from app.services.hybrid_search_service import HybridSearchService
from app.services.project_service import ProjectService
from app.services.prompt_version_service import PromptVersionService
from app.services.retrieval_service import RetrievalService

pytestmark = pytest.mark.asyncio


async def _seed(db_session: AsyncSession, canned_response: str = "The term is 90 days [1]."):
    owner = await UserRepository(db_session).create(email="owner@x.com", display_name="Owner")
    viewer = await UserRepository(db_session).create(email="viewer@x.com", display_name="Viewer")
    org = await OrganizationRepository(db_session).create(name="Co", slug="co")
    project_repository = ProjectRepository(db_session)
    project_service = ProjectService(project_repository)
    project = await project_service.create_project(
        organization_id=org.id, name="Legal", description=None, created_by=owner.id
    )
    await project_repository.add_member(
        project_id=project.id, user_id=viewer.id, role=ProjectRole.VIEWER, invited_by=owner.id
    )

    document_repository = DocumentRepository(db_session)
    document = await document_repository.create(
        project_id=project.id,
        filename="contract.txt",
        content_type="text/plain",
        size_bytes=1,
        checksum_sha256="x",
        storage_key="contract.txt",
        uploaded_by=owner.id,
    )
    await db_session.commit()
    document = await document_repository.get_by_id(document.id)

    embedder = LocalEmbeddingProvider(dimensions=32)
    text = "The term of this agreement is 90 days."
    [embedding] = await embedder.embed([text])
    await DocumentChunkRepository(db_session).bulk_create(
        [
            DocumentChunk(
                document_id=document.id,
                document_version_id=document.versions[0].id,
                page_number=1,
                section=None,
                text=text,
                token_count=8,
                start_offset=0,
                end_offset=len(text),
                embedding=embedding,
                chunk_metadata={},
            )
        ]
    )
    await db_session.commit()

    hybrid_service = HybridSearchService(
        DocumentChunkRepository(db_session), ProjectService(ProjectRepository(db_session)), embedder
    )
    retrieval_service = RetrievalService(hybrid_service, MockReranker())
    rag_service = RagService(
        retrieval_service, MockGenerationProvider(canned_response=canned_response)
    )
    prompt_version_service = PromptVersionService(
        PromptVersionRepository(db_session), ProjectService(ProjectRepository(db_session))
    )
    service = ConversationService(
        ConversationRepository(db_session),
        ProjectService(ProjectRepository(db_session)),
        rag_service,
        prompt_version_service,
        ModelRunRepository(db_session),
    )
    return service, owner, viewer, project


async def test_create_list_and_get_conversation(db_session: AsyncSession) -> None:
    service, owner, _viewer, project = await _seed(db_session)

    conversation = await service.create_conversation(
        project_id=project.id, user_id=owner.id, title="My Question"
    )
    await db_session.commit()

    listed = await service.list_conversations(project_id=project.id, user_id=owner.id)
    assert len(listed) == 1
    assert listed[0].id == conversation.id

    fetched = await service.get_conversation(
        conversation_id=conversation.id, project_id=project.id, user_id=owner.id
    )
    assert fetched.title == "My Question"


async def test_post_message_persists_user_and_assistant_messages_with_citations(
    db_session: AsyncSession,
) -> None:
    service, owner, _viewer, project = await _seed(db_session)
    conversation = await service.create_conversation(project_id=project.id, user_id=owner.id)
    await db_session.commit()

    result = await service.post_message(
        conversation_id=conversation.id,
        project_id=project.id,
        user_id=owner.id,
        content="How long is the term?",
    )
    await db_session.commit()

    assert result.user_message.role == MessageRole.USER
    assert result.assistant_message.role == MessageRole.ASSISTANT
    assert len(result.citations) == 1
    assert result.citations[0].document_filename == "contract.txt"
    assert result.insufficient_evidence is False
    # First message in the project auto-seeds an active "rag_answer"
    # prompt version (Phase 22) and credits the assistant message to it.
    assert result.assistant_message.prompt_version_id is not None
    assert result.user_message.prompt_version_id is None

    # Phase 23: a real generation call happened, so a ModelRun was created
    # and credited to the assistant message (never the user's message).
    assert result.assistant_message.model_run_id is not None
    assert result.user_message.model_run_id is None
    model_run = await ModelRunRepository(db_session).get_by_id(
        result.assistant_message.model_run_id
    )
    assert model_run is not None
    assert model_run.model == "mock-echo-v1"
    assert model_run.provider == "MockGenerationProvider"
    assert model_run.prompt_version_id == result.assistant_message.prompt_version_id
    assert model_run.retrieval_config["top_k"] == 6

    # Simulates a fresh request/session: without this, the `conversation`
    # object already in this session's identity map (loaded once above,
    # before these messages existed) would keep serving its stale,
    # already-loaded `.messages` collection instead of re-querying.
    db_session.expire(conversation, ["messages"])

    reloaded = await service.get_conversation(
        conversation_id=conversation.id, project_id=project.id, user_id=owner.id
    )
    assert len(reloaded.messages) == 2
    assert len(reloaded.messages[1].citations) == 1
    assert reloaded.messages[1].citations[0].document.filename == "contract.txt"


async def test_post_message_with_no_evidence_creates_no_model_run(db_session: AsyncSession) -> None:
    owner = await UserRepository(db_session).create(email="empty@x.com", display_name="Empty")
    org = await OrganizationRepository(db_session).create(name="Empty", slug="empty")
    project = await ProjectService(ProjectRepository(db_session)).create_project(
        organization_id=org.id, name="Empty project", description=None, created_by=owner.id
    )
    await db_session.commit()

    embedder = LocalEmbeddingProvider(dimensions=32)
    hybrid_service = HybridSearchService(
        DocumentChunkRepository(db_session), ProjectService(ProjectRepository(db_session)), embedder
    )
    retrieval_service = RetrievalService(hybrid_service, MockReranker())
    rag_service = RagService(retrieval_service, MockGenerationProvider())
    prompt_version_service = PromptVersionService(
        PromptVersionRepository(db_session), ProjectService(ProjectRepository(db_session))
    )
    service = ConversationService(
        ConversationRepository(db_session),
        ProjectService(ProjectRepository(db_session)),
        rag_service,
        prompt_version_service,
        ModelRunRepository(db_session),
    )

    conversation = await service.create_conversation(project_id=project.id, user_id=owner.id)
    await db_session.commit()

    result = await service.post_message(
        conversation_id=conversation.id,
        project_id=project.id,
        user_id=owner.id,
        content="anything",
    )
    await db_session.commit()

    assert result.sources_considered == 0
    assert result.assistant_message.model_run_id is None
    assert result.assistant_message.prompt_version_id is None


async def test_post_message_uses_bounded_history_on_followups(db_session: AsyncSession) -> None:
    # Each block below is expired-between to simulate separate HTTP
    # requests (a fresh session per request in production — see the note
    # in the previous test); otherwise this session's identity map would
    # keep serving each object's state as of when it was first loaded.
    service, owner, _viewer, project = await _seed(db_session, canned_response="Follow-up [1].")
    conversation = await service.create_conversation(project_id=project.id, user_id=owner.id)
    await db_session.commit()
    db_session.expire(conversation, ["messages"])

    await service.post_message(
        conversation_id=conversation.id,
        project_id=project.id,
        user_id=owner.id,
        content="First question",
    )
    await db_session.commit()
    db_session.expire(conversation, ["messages"])

    second = await service.post_message(
        conversation_id=conversation.id,
        project_id=project.id,
        user_id=owner.id,
        content="Second question",
    )
    await db_session.commit()
    db_session.expire(conversation, ["messages"])

    reloaded = await service.get_conversation(
        conversation_id=conversation.id, project_id=project.id, user_id=owner.id
    )
    assert len(reloaded.messages) == 4
    assert second.assistant_message.content == "Follow-up [1]."


async def test_rename_conversation_by_owner(db_session: AsyncSession) -> None:
    service, owner, _viewer, project = await _seed(db_session)
    conversation = await service.create_conversation(project_id=project.id, user_id=owner.id)
    await db_session.commit()

    updated = await service.rename_conversation(
        conversation_id=conversation.id, project_id=project.id, user_id=owner.id, title="Renamed"
    )
    assert updated.title == "Renamed"


async def test_viewer_can_rename_their_own_conversation(db_session: AsyncSession) -> None:
    service, _owner, viewer, project = await _seed(db_session)
    conversation = await service.create_conversation(project_id=project.id, user_id=viewer.id)
    await db_session.commit()

    updated = await service.rename_conversation(
        conversation_id=conversation.id, project_id=project.id, user_id=viewer.id, title="Mine"
    )
    assert updated.title == "Mine"


async def test_viewer_cannot_rename_someone_elses_conversation(db_session: AsyncSession) -> None:
    service, owner, viewer, project = await _seed(db_session)
    conversation = await service.create_conversation(project_id=project.id, user_id=owner.id)
    await db_session.commit()

    with pytest.raises(ForbiddenError):
        await service.rename_conversation(
            conversation_id=conversation.id,
            project_id=project.id,
            user_id=viewer.id,
            title="Hacked",
        )


async def test_delete_conversation(db_session: AsyncSession) -> None:
    service, owner, _viewer, project = await _seed(db_session)
    conversation = await service.create_conversation(project_id=project.id, user_id=owner.id)
    await db_session.commit()

    await service.delete_conversation(
        conversation_id=conversation.id, project_id=project.id, user_id=owner.id
    )
    await db_session.commit()

    with pytest.raises(NotFoundError):
        await service.get_conversation(
            conversation_id=conversation.id, project_id=project.id, user_id=owner.id
        )
