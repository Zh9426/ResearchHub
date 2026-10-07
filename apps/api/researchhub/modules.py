import math
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .schemas import ValueType

CAPABILITIES = [
    {
        "id": "code_simulation",
        "name": "代码与仿真",
        "description": "计算模型、代码与数值实验",
    },
    {
        "id": "lab_experiment",
        "name": "实验记录",
        "description": "样品、条件、设备与实验观察",
    },
    {
        "id": "hardware_system",
        "name": "硬件系统",
        "description": "原型、物料、设计与固件",
    },
    {
        "id": "measurement_imaging",
        "name": "测量与成像",
        "description": "校准、原始数据与处理数据",
    },
    {"id": "fabrication", "name": "加工制造", "description": "制造版本、材料与工艺"},
    {"id": "data_analysis", "name": "数据分析", "description": "分析方法与派生结果"},
    {"id": "literature_sources", "name": "文献与来源", "description": "研究来源与引用"},
]
CAPABILITY_IDS = {c["id"] for c in CAPABILITIES}


class Named(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    name: str
    capability: str | None = None


class Schema(Named):
    value_type: ValueType
    unit: str = ""
    description: str | None = None
    required: bool = False
    optional: bool = True
    default: Any = None
    display_group: str = "parameters"
    order: int = 0
    help_text: str = ""
    visibility: Literal["basic", "advanced"] = "basic"
    optimization_direction: Literal[
        "maximize", "minimize", "target_range", "informational"
    ] = "informational"
    target_range: list[float] | None = Field(default=None, min_length=2, max_length=2)

    @model_validator(mode="after")
    def valid_target_range(self):
        if self.target_range is not None and (
            not all(math.isfinite(value) for value in self.target_range)
            or self.target_range[0] > self.target_range[1]
        ):
            raise ValueError("Target range requires finite ordered bounds")
        if self.optimization_direction == "target_range" and self.target_range is None:
            raise ValueError("Target range direction requires bounds")
        return self


class FormGroup(Named):
    fields: list[str]
    visibility: Literal["basic", "advanced"] = "basic"


class RunForm(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_type: str
    capability: str | None = None
    groups: list[FormGroup]


class Stage(Named):
    description: str


class Criterion(BaseModel):
    id: str
    description: str
    provenance: str


class StageGate(Stage):
    stage_id: str
    criteria: list[Criterion]


LayoutType = Literal[
    "research", "runs", "metrics", "evidence", "artifacts", "lineage", "hardware", "lab"
]
WidgetKind = Literal[
    "objective",
    "stage_gates",
    "highlighted_runs",
    "recent_runs",
    "representative_metrics",
    "validation",
    "current_tasks",
    "evidence_summary",
    "open_risks",
    "recent_decisions",
    "recent_activity",
]


class ViewFilters(Named):
    description: str = ""
    run_types: list[str] = []
    metric_ids: list[str] = []
    artifact_categories: list[str] = []
    evidence_filters: dict[Literal["status", "type"], list[str]] = {}
    layout_type: LayoutType = "research"


class CustomView(ViewFilters):
    pass


class DashboardWidget(ViewFilters):
    kind: WidgetKind


class Manifest(Stage):
    version: str
    default_capabilities: list[str] = []
    run_types: list[Named]
    parameter_schemas: list[Schema]
    metric_schemas: list[Schema]
    context_fields: list[Schema] = []
    run_forms: list[RunForm] = []
    research_stages: list[Stage]
    stage_gates: list[StageGate]
    artifact_categories: list[str]
    dashboard_widgets: list[str | DashboardWidget]
    navigation: list[Named]
    custom_views: list[CustomView]

    @model_validator(mode="after")
    def references_valid(self):
        definitions = (
            self.run_types
            + self.parameter_schemas
            + self.metric_schemas
            + self.context_fields
        )
        capabilities = (
            self.default_capabilities
            + [d.capability for d in definitions if d.capability]
            + [f.capability for f in self.run_forms if f.capability]
        )
        if any(c not in CAPABILITY_IDS for c in capabilities):
            raise ValueError("Unknown capability")
        for collection in (
            self.run_types,
            self.parameter_schemas,
            self.metric_schemas,
            self.context_fields,
            self.research_stages,
            self.stage_gates,
            self.navigation,
            self.custom_views,
        ):
            if len({x.id for x in collection}) != len(collection):
                raise ValueError("Duplicate manifest identifier")
        fields = {
            x.id
            for x in self.parameter_schemas + self.metric_schemas + self.context_fields
        }
        if len(fields) != len(
            self.parameter_schemas + self.metric_schemas + self.context_fields
        ):
            raise ValueError("Ambiguous run form field identifier")
        if len({form.run_type for form in self.run_forms}) != len(self.run_forms):
            raise ValueError("Duplicate run form type")
        types = {r.id for r in self.run_types}
        metrics = {metric.id for metric in self.metric_schemas}
        widget_ids = [
            widget if isinstance(widget, str) else widget.id
            for widget in self.dashboard_widgets
        ]
        if len(widget_ids) != len(set(widget_ids)):
            raise ValueError("Duplicate dashboard widget identifier")
        for view in self.custom_views + [
            widget for widget in self.dashboard_widgets if not isinstance(widget, str)
        ]:
            if (
                not set(view.run_types) <= types
                or not set(view.metric_ids) <= metrics
                or not set(view.artifact_categories) <= set(self.artifact_categories)
                or view.capability
                and view.capability not in CAPABILITY_IDS
            ):
                raise ValueError("Unknown custom view or widget reference")
            for identifiers in (
                view.run_types,
                view.metric_ids,
                view.artifact_categories,
                *view.evidence_filters.values(),
            ):
                if len(identifiers) != len(set(identifiers)):
                    raise ValueError("Duplicate view filter identifier")
        for form in self.run_forms:
            if form.run_type not in types or any(
                k not in fields for g in form.groups for k in g.fields
            ):
                raise ValueError("Unknown run form field or type")
        stages = {s.id for s in self.research_stages}
        if any(g.stage_id not in stages for g in self.stage_gates):
            raise ValueError("Invalid gate stage")
        return self


def load_modules():
    root = Path(__file__).resolve().parents[3] / "packages" / "project-modules"
    result = {}
    for path in sorted(root.glob("*/manifest.json")):
        manifest = Manifest.model_validate_json(path.read_text(encoding="utf-8"))
        if manifest.id in result:
            raise ValueError("Duplicate module")
        result[manifest.id] = manifest.model_dump()
    return result
