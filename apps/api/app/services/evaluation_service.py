"""Evaluation run authorization/orchestration (Phase 29) — the
request-time half; the actual grading runs in a background job
(app/jobs/evaluations.py), the same split as reports (Phase 24).

Resolving the dataset file and the current model/retriever identity both
happen here, synchronously, at creation time — neither costs an LLM call
(loading a dataset is a file read; `generation_provider.model` and
`RETRIEVER_VERSION` are just attributes/constants) — so an EvaluationRun
row's identifying "coordinates" (dataset+version, model, retriever
version, prompt version) are set the moment it's created, not only once
the job gets around to running. That's what lets two runs be compared
(Phase 31) without waiting on completion.
"""

import uuid

from caseflow_evals import DatasetValidationError, EvaluationDataset, load_dataset

from app.errors import NotFoundError, ValidationError
from app.evals.dataset_paths import DatasetNotFoundError, resolve_dataset_path
from app.integrations.generation import GenerationProvider
from app.models.evaluation import EvaluationRun
from app.models.project import ProjectRole
from app.rag.prompts import SYSTEM_PROMPT
from app.repositories.evaluation_repository import EvaluationRunRepository
from app.services.project_service import ProjectService
from app.services.prompt_version_service import RAG_ANSWER_PROMPT_NAME, PromptVersionService
from app.services.retrieval_service import RETRIEVER_VERSION


def load_evaluation_dataset(dataset_name: str) -> EvaluationDataset:
    """Resolves and loads a dataset by name, translating packages/evals's
    own errors into the app's error hierarchy so routes render a proper
    404/422 instead of a raw exception."""
    try:
        path = resolve_dataset_path(dataset_name)
    except DatasetNotFoundError as exc:
        raise NotFoundError(str(exc)) from exc
    try:
        return load_dataset(path)
    except DatasetValidationError as exc:
        raise ValidationError(str(exc)) from exc


class EvaluationRunService:
    def __init__(
        self,
        repository: EvaluationRunRepository,
        project_service: ProjectService,
        prompt_version_service: PromptVersionService,
        generation_provider: GenerationProvider,
    ) -> None:
        self._repository = repository
        self._project_service = project_service
        self._prompt_version_service = prompt_version_service
        self._generation_provider = generation_provider

    async def create_run(
        self, *, project_id: uuid.UUID, user_id: uuid.UUID, dataset_name: str
    ) -> EvaluationRun:
        # Grading a dataset spends real retrieval + LLM + judge calls per
        # example — same owner/editor gate as generating a report.
        await self._project_service.require_role(
            project_id=project_id,
            user_id=user_id,
            allowed={ProjectRole.OWNER, ProjectRole.EDITOR},
        )
        dataset = load_evaluation_dataset(dataset_name)

        prompt_version = await self._prompt_version_service.get_or_seed_active(
            project_id=project_id,
            user_id=user_id,
            name=RAG_ANSWER_PROMPT_NAME,
            default_template=SYSTEM_PROMPT,
        )

        return await self._repository.create(
            project_id=project_id,
            dataset_name=dataset.name,
            dataset_version=dataset.version,
            prompt_version_id=prompt_version.id,
            model=self._generation_provider.model,
            retriever_version=RETRIEVER_VERSION,
            created_by=user_id,
        )

    async def list_runs(self, *, project_id: uuid.UUID, user_id: uuid.UUID) -> list[EvaluationRun]:
        await self._project_service.get_project_for_user(project_id=project_id, user_id=user_id)
        return await self._repository.list_for_project(project_id)

    async def get_run(
        self, *, evaluation_run_id: uuid.UUID, project_id: uuid.UUID, user_id: uuid.UUID
    ) -> EvaluationRun:
        await self._project_service.get_project_for_user(project_id=project_id, user_id=user_id)
        run = await self._repository.get_by_id(evaluation_run_id)
        if run is None or run.project_id != project_id:
            raise NotFoundError(f"Evaluation run {evaluation_run_id} not found.")
        return run
