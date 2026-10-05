from pathlib import Path

from pydantic import BaseModel, ConfigDict

from .schemas import ValueType


class Named(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    name: str


class Schema(Named):
    value_type: ValueType
    unit: str
    description: str | None = None


class Stage(Named):
    description: str


class Criterion(BaseModel):
    id: str
    description: str
    provenance: str


class StageGate(Stage):
    stage_id: str
    criteria: list[Criterion]


class Manifest(Stage):
    version: str
    run_types: list[Named]
    parameter_schemas: list[Schema]
    metric_schemas: list[Schema]
    research_stages: list[Stage]
    stage_gates: list[StageGate]
    artifact_categories: list[str]
    dashboard_widgets: list[str]
    navigation: list[Named]
    custom_views: list[Named]


def load_modules():
    root = Path(__file__).resolve().parents[3] / "packages" / "project-modules"
    result = {}
    for path in sorted(root.glob("*/manifest.json")):
        manifest = Manifest.model_validate_json(path.read_text(encoding="utf-8"))
        if manifest.id in result:
            raise ValueError("Duplicate module")
        stage_ids = {s.id for s in manifest.research_stages}
        if any(g.stage_id not in stage_ids for g in manifest.stage_gates):
            raise ValueError("Invalid gate stage")
        result[manifest.id] = manifest.model_dump()
    return result
