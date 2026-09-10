import uuid

from pydantic import BaseModel


class CostDayRead(BaseModel):
    day: str
    model: str
    user_id: uuid.UUID
    total_cost_usd: float
    total_input_tokens: int
    total_output_tokens: int
    run_count: int


class CostSummaryRead(BaseModel):
    project_id: uuid.UUID
    total_cost_usd: float
    total_input_tokens: int
    total_output_tokens: int
    total_runs: int
    by_day: list[CostDayRead]
    by_model: dict[str, float]
    by_user: dict[str, float]
