from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

EvidenceState = Literal[
    "proposed",
    "unknown",
    "hypothesis",
    "assumed",
    "synthetic",
    "simulated",
    "measured",
    "calibrated",
    "validated",
    "reproduced",
    "rejected",
]
SourceKind = Literal[
    "unknown",
    "synthetic",
    "assumed",
    "literature",
    "manufacturer",
    "measured",
    "calibrated",
    "derived",
]
GateState = Literal["not_started", "in_progress", "passed", "failed", "blocked"]
ValueType = Literal["number", "integer", "string", "boolean", "object", "array"]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class AuthInput(Input):
    email: str = Field(
        min_length=3, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$"
    )
    password: str = Field(min_length=12, max_length=256)
    display_name: str = Field(default="Researcher", max_length=100)


class TokenInput(Input):
    name: str = Field(min_length=1, max_length=100)
    scopes: list[Literal["research:read", "research:write"]] = Field(min_length=1)
    actor_type: Literal["codex", "chatgpt"] = "codex"


class LifecycleInput(Input):
    action: Literal["archive", "trash", "restore"]


class PurgeInput(Input):
    confirm: Literal[True]


class ModuleUpgradeInput(PurgeInput):
    expected_version: str
    expected_target_digest: str = Field(min_length=64, max_length=64)


class StorageGCInput(PurgeInput):
    object_keys: list[str] = Field(min_length=1, max_length=100)


class ProjectInput(Input):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    module_id: str
    status: Literal["active", "paused", "completed", "archived", "blocked"] = "active"
    current_stage: str | None = None
    current_objective: str = ""


class TitleInput(Input):
    title: str = Field(min_length=1, max_length=200)
    description: str = ""


class QuestionInput(TitleInput):
    status: Literal["open", "investigating", "answered", "closed"] = "open"


class HypothesisInput(Input):
    research_question_id: UUID | None = None
    statement: str = Field(min_length=1)
    status: Literal["proposed", "testing", "supported", "rejected", "inconclusive"] = (
        "proposed"
    )
    evidence_status: EvidenceState = "hypothesis"


class MilestoneInput(TitleInput):
    status: Literal["not_started", "in_progress", "completed", "blocked"] = (
        "not_started"
    )
    target_date: datetime | None = None
    completed_at: datetime | None = None


class TaskInput(TitleInput):
    milestone_id: UUID | None = None
    status: Literal["todo", "doing", "blocked", "done"] = "todo"
    priority: Literal["low", "medium", "high", "critical"] = "medium"
    due_date: datetime | None = None


class RunInput(Input):
    title: str = Field(min_length=1, max_length=200)
    run_type: str = Field(min_length=1, max_length=100)
    parent_run_id: UUID | None = None
    objective: str = ""
    hypothesis: str = ""
    status: Literal[
        "planned", "running", "completed", "failed", "cancelled", "blocked"
    ] = "planned"
    scientific_outcome: Literal[
        "unknown",
        "positive_result",
        "negative_result",
        "inconclusive",
        "candidate_rejected",
    ] = "unknown"
    protocol: str = ""
    observation: str = ""
    ai_analysis: str = ""
    human_conclusion: str = ""
    next_step: str = ""
    environment: str = ""
    software_version: str = ""
    code_revision: str = ""
    changes_from_parent: str = ""
    started_at: datetime | None = None
    completed_at: datetime | None = None


class ParameterInput(Input):
    name: str = Field(min_length=1, max_length=200)
    value: Any = None
    value_type: ValueType = "number"
    unit: str | None = None
    source_kind: SourceKind = "unknown"
    source_id: UUID | None = None
    source_location: str | None = None
    uncertainty: str | None = None
    valid_conditions: str | None = None
    is_confirmed: bool = False

    @model_validator(mode="after")
    def valid_value(self):
        if self.value is None:
            return self
        types = {
            "number": (int, float),
            "integer": (int,),
            "string": (str,),
            "boolean": (bool,),
            "object": (dict,),
            "array": (list,),
        }
        if not isinstance(self.value, types[self.value_type]) or (
            self.value_type in ("number", "integer") and isinstance(self.value, bool)
        ):
            raise ValueError("value does not match value_type")
        return self


class MetricInput(Input):
    name: str = Field(min_length=1, max_length=200)
    value: float | int | str | bool | None = None
    unit: str | None = None
    metric_schema_id: str | None = None
    status: EvidenceState = "unknown"


class MetricsBatch(Input):
    metrics: list[MetricInput] = Field(min_length=1, max_length=100)


class SourceInput(TitleInput):
    source_kind: SourceKind = "unknown"
    url: str | None = None
    doi: str | None = None
    citation: str = ""
    source_location: str | None = None


class EvidenceInput(TitleInput):
    evidence_type: str = "observation"
    status: EvidenceState = "unknown"
    linked_run_id: UUID | None = None
    linked_artifact_id: UUID | None = None
    linked_source_id: UUID | None = None
    limitations: str = ""


class ClaimInput(Input):
    title: str = ""
    statement: str = Field(min_length=1)
    status: Literal["draft", "supported", "rejected", "inconclusive"] = "draft"
    limitations: str = ""
    evidence_ids: list[UUID] = []
    run_ids: list[UUID] = []
    artifact_ids: list[UUID] = []
    source_ids: list[UUID] = []


class NoteInput(Input):
    title: str = Field(min_length=1, max_length=200)
    content: str = ""
    run_id: UUID | None = None


class DecisionInput(Input):
    title: str = Field(min_length=1, max_length=200)
    run_id: UUID | None = None
    context: str = ""
    decision: str = ""
    reason: str = ""
    alternatives: str = ""
    status: Literal["proposed", "accepted", "superseded", "rejected"] = "proposed"
    evidence_ids: list[UUID] = []


class RiskInput(TitleInput):
    severity: Literal["low", "medium", "high", "critical"] = "medium"
    status: Literal["open", "mitigated", "closed"] = "open"
    mitigation: str = ""


class TagInput(Input):
    name: str = Field(min_length=1, max_length=100)
    color: str = "gray"


class CriterionInput(Input):
    id: str
    description: str
    provenance: str = "proposed"
    status: GateState = "not_started"
    evidence_ids: list[UUID] = []


class GateInput(Input):
    gate_id: str
    stage_id: str
    name: str
    description: str = ""
    status: GateState = "not_started"
    criteria: list[CriterionInput] = []
    evidence_ids: list[UUID] = []
    blocking_reason: str = ""


SCHEMAS = {
    "projects": ProjectInput,
    "runs": RunInput,
    "tasks": TaskInput,
    "milestones": MilestoneInput,
    "questions": QuestionInput,
    "hypotheses": HypothesisInput,
    "evidence": EvidenceInput,
    "claims": ClaimInput,
    "sources": SourceInput,
    "notes": NoteInput,
    "decisions": DecisionInput,
    "risks": RiskInput,
    "tags": TagInput,
    "gates": GateInput,
    "parameters": ParameterInput,
    "metrics": MetricInput,
}
