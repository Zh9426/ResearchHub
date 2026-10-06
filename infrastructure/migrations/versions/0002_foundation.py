"""Freeze v0.1 module definitions and add reversible record lifecycle + object deletion outbox.

The snapshots below are embedded deployment definitions, never loaded from current manifests.
"""

import json

import sqlalchemy as sa
from alembic import op

revision = "0002_foundation"
down_revision = "0001_core"
branch_labels = None
depends_on = None

FROZEN_V01 = json.loads(r"""{
  "generic": {
    "id": "generic",
    "name": "通用科研",
    "version": "0.1.0",
    "description": "通用科研工作空间；不预置任何超声参数。",
    "run_types": [
      {
        "id": "simulation",
        "name": "仿真"
      },
      {
        "id": "numerical_validation",
        "name": "数值验证"
      },
      {
        "id": "measurement",
        "name": "测量"
      },
      {
        "id": "benchmark",
        "name": "基准测试"
      },
      {
        "id": "optimization",
        "name": "优化"
      },
      {
        "id": "physical_experiment",
        "name": "物理实验"
      },
      {
        "id": "parameter_sweep",
        "name": "参数扫描"
      },
      {
        "id": "material_test",
        "name": "material_test"
      },
      {
        "id": "imaging_test",
        "name": "imaging_test"
      }
    ],
    "parameter_schemas": [],
    "metric_schemas": [],
    "research_stages": [
      {
        "id": "question",
        "name": "研究问题",
        "description": "研究问题"
      },
      {
        "id": "design",
        "name": "研究设计",
        "description": "研究设计"
      },
      {
        "id": "execution",
        "name": "研究执行",
        "description": "研究执行"
      },
      {
        "id": "analysis",
        "name": "结果分析",
        "description": "结果分析"
      },
      {
        "id": "review",
        "name": "复核",
        "description": "复核"
      }
    ],
    "stage_gates": [],
    "artifact_categories": [
      "data",
      "figure",
      "report",
      "protocol",
      "code",
      "other"
    ],
    "dashboard_widgets": [
      "research_questions",
      "tasks",
      "recent_runs",
      "evidence_summary"
    ],
    "navigation": [
      {
        "id": "overview",
        "name": "概览"
      },
      {
        "id": "research",
        "name": "研究"
      },
      {
        "id": "runs",
        "name": "研究记录"
      },
      {
        "id": "evidence",
        "name": "证据"
      },
      {
        "id": "tasks",
        "name": "任务"
      },
      {
        "id": "milestones",
        "name": "里程碑"
      },
      {
        "id": "artifacts",
        "name": "研究文件"
      },
      {
        "id": "notes",
        "name": "笔记"
      },
      {
        "id": "decisions",
        "name": "决策"
      },
      {
        "id": "timeline",
        "name": "时间线"
      }
    ],
    "custom_views": []
  },
  "hdsp": {
    "id": "hdsp",
    "name": "HDSP",
    "version": "0.1.0",
    "description": "固定目标平面的全息超声表面打印；厚度相位板设计、声场、热与固化验证。",
    "run_types": [
      {
        "id": "phase_retrieval",
        "name": "相位检索"
      },
      {
        "id": "phase_plate_design",
        "name": "相位板设计"
      },
      {
        "id": "acoustic_simulation",
        "name": "声场仿真"
      },
      {
        "id": "zscan",
        "name": "轴向扫描"
      },
      {
        "id": "thermal_simulation",
        "name": "热仿真"
      },
      {
        "id": "curing_prediction",
        "name": "固化预测"
      },
      {
        "id": "optimization",
        "name": "优化"
      },
      {
        "id": "physical_validation",
        "name": "物理验证"
      }
    ],
    "parameter_schemas": [
      {
        "id": "frequency",
        "name": "频率",
        "value_type": "number",
        "unit": "Hz"
      },
      {
        "id": "z_target",
        "name": "固定目标平面距离",
        "value_type": "number",
        "unit": "m"
      },
      {
        "id": "pressure",
        "name": "声压",
        "value_type": "number",
        "unit": "Pa"
      },
      {
        "id": "algorithm",
        "name": "算法",
        "value_type": "string",
        "unit": ""
      },
      {
        "id": "iterations",
        "name": "迭代数",
        "value_type": "integer",
        "unit": ""
      },
      {
        "id": "beta",
        "name": "β 系数",
        "value_type": "number",
        "unit": ""
      },
      {
        "id": "phase_levels",
        "name": "相位级数",
        "value_type": "integer",
        "unit": ""
      }
    ],
    "metric_schemas": [
      {
        "id": "IoU",
        "name": "固化 IoU",
        "value_type": "number",
        "unit": ""
      },
      {
        "id": "correlation",
        "name": "相关性",
        "value_type": "number",
        "unit": ""
      },
      {
        "id": "coverage",
        "name": "覆盖率",
        "value_type": "number",
        "unit": ""
      },
      {
        "id": "p_max",
        "name": "最大声压",
        "value_type": "number",
        "unit": "Pa"
      },
      {
        "id": "Tmax",
        "name": "最高温度",
        "value_type": "number",
        "unit": "K"
      },
      {
        "id": "Omega",
        "name": "Arrhenius 积分",
        "value_type": "number",
        "unit": ""
      },
      {
        "id": "best_z",
        "name": "最佳平面",
        "value_type": "number",
        "unit": "m"
      },
      {
        "id": "Energy Efficiency",
        "name": "能量效率",
        "value_type": "number",
        "unit": ""
      },
      {
        "id": "over_cure",
        "name": "过固化面积",
        "value_type": "number",
        "unit": ""
      },
      {
        "id": "under_cure",
        "name": "欠固化面积",
        "value_type": "number",
        "unit": ""
      }
    ],
    "research_stages": [
      {
        "id": "target_design",
        "name": "目标设计",
        "description": "目标设计"
      },
      {
        "id": "phase_retrieval",
        "name": "相位检索",
        "description": "相位检索"
      },
      {
        "id": "phase_plate_design",
        "name": "相位板设计",
        "description": "相位板设计"
      },
      {
        "id": "acoustic_simulation",
        "name": "声场仿真",
        "description": "声场仿真"
      },
      {
        "id": "zscan",
        "name": "轴向扫描",
        "description": "轴向扫描"
      },
      {
        "id": "thermal_simulation",
        "name": "热仿真",
        "description": "热仿真"
      },
      {
        "id": "curing_prediction",
        "name": "固化预测",
        "description": "固化预测"
      },
      {
        "id": "optimization",
        "name": "优化",
        "description": "优化"
      },
      {
        "id": "physical_validation",
        "name": "物理验证",
        "description": "物理验证"
      }
    ],
    "stage_gates": [],
    "artifact_categories": [
      "data",
      "figure",
      "report",
      "protocol",
      "code",
      "other"
    ],
    "dashboard_widgets": [
      "current_stage",
      "current_goal",
      "recent_runs",
      "best_metrics",
      "open_tasks",
      "recent_decisions",
      "artifacts",
      "activity"
    ],
    "navigation": [
      {
        "id": "overview",
        "name": "概览"
      },
      {
        "id": "research",
        "name": "研究"
      },
      {
        "id": "runs",
        "name": "研究记录"
      },
      {
        "id": "evidence",
        "name": "证据"
      },
      {
        "id": "tasks",
        "name": "任务"
      },
      {
        "id": "milestones",
        "name": "里程碑"
      },
      {
        "id": "artifacts",
        "name": "研究文件"
      },
      {
        "id": "notes",
        "name": "笔记"
      },
      {
        "id": "decisions",
        "name": "决策"
      },
      {
        "id": "timeline",
        "name": "时间线"
      }
    ],
    "custom_views": []
  },
  "ice-sonocuring": {
    "id": "ice-sonocuring",
    "name": "ICE 声固化",
    "version": "0.1.0",
    "description": "双功能 ICE 探头局部声响应封堵研究。路线图仅定义拟议流程，历史结果不作为当前事实。",
    "run_types": [
      {
        "id": "numerical_validation",
        "name": "数值验证"
      },
      {
        "id": "controlled_probe_comparison",
        "name": "受控探头比较"
      },
      {
        "id": "steering_test",
        "name": "声束偏转测试"
      },
      {
        "id": "scan_protocol_test",
        "name": "扫描方案测试"
      },
      {
        "id": "robustness_test",
        "name": "稳健性测试"
      },
      {
        "id": "imaging_psf",
        "name": "成像点扩散函数"
      },
      {
        "id": "kwave_validation",
        "name": "k-Wave 验证"
      },
      {
        "id": "hydrophone_measurement",
        "name": "水听器测量"
      },
      {
        "id": "material_response",
        "name": "材料响应"
      },
      {
        "id": "thermal_flow_test",
        "name": "热与流动测试"
      },
      {
        "id": "prototype_validation",
        "name": "原型验证"
      },
      {
        "id": "phantom_test",
        "name": "模型体测试"
      }
    ],
    "parameter_schemas": [
      {
        "id": "frequency",
        "name": "频率",
        "value_type": "number",
        "unit": "Hz"
      },
      {
        "id": "element_count",
        "name": "阵元数",
        "value_type": "integer",
        "unit": ""
      },
      {
        "id": "pitch",
        "name": "阵元间距",
        "value_type": "number",
        "unit": "m"
      },
      {
        "id": "source_velocity",
        "name": "表面速度",
        "value_type": "number",
        "unit": "m/s"
      },
      {
        "id": "roi",
        "name": "固定评价域",
        "value_type": "object",
        "unit": ""
      },
      {
        "id": "sound_speed",
        "name": "声速",
        "value_type": "number",
        "unit": "m/s"
      },
      {
        "id": "dwell_time",
        "name": "停留时间",
        "value_type": "number",
        "unit": "s"
      },
      {
        "id": "material_threshold",
        "name": "材料响应阈值（未知时保持 null（未知值））",
        "value_type": "number",
        "unit": ""
      }
    ],
    "metric_schemas": [
      {
        "id": "coverage",
        "name": "声学代理覆盖 C",
        "value_type": "number",
        "unit": ""
      },
      {
        "id": "leakage",
        "name": "声学泄漏 L",
        "value_type": "number",
        "unit": ""
      },
      {
        "id": "outside_threshold_volume",
        "name": "目标外超阈值体积",
        "value_type": "number",
        "unit": "m3"
      },
      {
        "id": "outside_peak",
        "name": "目标外峰值",
        "value_type": "number",
        "unit": "Pa"
      },
      {
        "id": "numerical_sensitivity",
        "name": "经验数值敏感性",
        "value_type": "number",
        "unit": ""
      },
      {
        "id": "psf_width",
        "name": "PSF 宽度",
        "value_type": "number",
        "unit": "m"
      },
      {
        "id": "material_response",
        "name": "实测材料响应",
        "value_type": "number",
        "unit": ""
      }
    ],
    "research_stages": [
      {
        "id": "A",
        "name": "数值可信度与声学筛选",
        "description": "数值可信度与声学筛选"
      },
      {
        "id": "B",
        "name": "成像评价与增强仿真",
        "description": "成像评价与增强仿真"
      },
      {
        "id": "C",
        "name": "物理闭环验证",
        "description": "物理闭环验证"
      },
      {
        "id": "D",
        "name": "系统与原型验证",
        "description": "系统与原型验证"
      },
      {
        "id": "E",
        "name": "动物实验前证据评审",
        "description": "动物实验前证据评审"
      }
    ],
    "stage_gates": [
      {
        "id": "G0",
        "name": "基线可复现性",
        "stage_id": "A",
        "description": "依据 2026-09-26 ICE roadmap 的拟议门槛；不表示项目已通过。",
        "criteria": [
          {
            "id": "G0-1",
            "description": "冻结配置、代码版本与环境，记录可重复基线。",
            "provenance": "proposed: 2026-09-26-ice-research-roadmap.md"
          },
          {
            "id": "G0-2",
            "description": "归档原始输出与校验摘要，区分历史记录和新验证。",
            "provenance": "proposed: 2026-09-26-ice-research-roadmap.md"
          }
        ]
      },
      {
        "id": "G1",
        "name": "数值可信度",
        "stage_id": "A",
        "description": "依据 2026-09-26 ICE roadmap 的拟议门槛；不表示项目已通过。",
        "criteria": [
          {
            "id": "G1-1",
            "description": "固定评价 ROI 的三级数值细化，报告经验敏感性与数值限制。",
            "provenance": "proposed: 2026-09-26-ice-research-roadmap.md"
          },
          {
            "id": "G1-2",
            "description": "扩大搜索域检查峰值与截断；截断外域保持 未知。",
            "provenance": "proposed: 2026-09-26-ice-research-roadmap.md"
          },
          {
            "id": "G1-3",
            "description": "拟议容差：关键幅值变化 ≤2%，宽度变化 ≤5%；需项目负责人冻结后使用。",
            "provenance": "proposed: 2026-09-26-ice-research-roadmap.md"
          }
        ]
      },
      {
        "id": "G2",
        "name": "受控比较",
        "stage_id": "A",
        "description": "依据 2026-09-26 ICE roadmap 的拟议门槛；不表示项目已通过。",
        "criteria": [
          {
            "id": "G2-1",
            "description": "共同目标、评价 ROI、阈值、冻结公共参考及独立复核场景。",
            "provenance": "proposed: 2026-09-26-ice-research-roadmap.md"
          },
          {
            "id": "G2-2",
            "description": "分开等速度、等面积/计数、等平方速度积分；不称为等真实功率。",
            "provenance": "proposed: 2026-09-26-ice-research-roadmap.md"
          },
          {
            "id": "G2-3",
            "description": "同活动孔径负对照；报告覆盖、泄漏、绝对外域量及阴性结果。",
            "provenance": "proposed: 2026-09-26-ice-research-roadmap.md"
          }
        ]
      },
      {
        "id": "G3",
        "name": "可交付证据",
        "stage_id": "B",
        "description": "依据 2026-09-26 ICE roadmap 的拟议门槛；不表示项目已通过。",
        "criteria": [
          {
            "id": "G3-1",
            "description": "结论追溯到运行、配置、结果与适用边界。",
            "provenance": "proposed: 2026-09-26-ice-research-roadmap.md"
          },
          {
            "id": "G3-2",
            "description": "复跑代表候选和失败案例；声学覆盖与实测固化覆盖分开。",
            "provenance": "proposed: 2026-09-26-ice-research-roadmap.md"
          }
        ]
      },
      {
        "id": "G4",
        "name": "制造与水槽验证评审",
        "stage_id": "D",
        "description": "依据 2026-09-26 ICE roadmap 的拟议门槛；不表示项目已通过。",
        "criteria": [
          {
            "id": "G4-1",
            "description": "制造约束、成像设计、驱动来源、材料先导与关键模型复核有证据。",
            "provenance": "proposed: 2026-09-26-ice-research-roadmap.md"
          },
          {
            "id": "G4-2",
            "description": "参考声源到目标探头的迁移差距与原型重新标定计划明确。",
            "provenance": "proposed: 2026-09-26-ice-research-roadmap.md"
          }
        ]
      },
      {
        "id": "G5",
        "name": "模型体与离体验证",
        "stage_id": "E",
        "description": "依据 2026-09-26 ICE roadmap 的拟议门槛；不表示项目已通过。",
        "criteria": [
          {
            "id": "G5-1",
            "description": "电声与温度测量、材料重复性、成像串扰、封堵功能判据有记录。",
            "provenance": "proposed: 2026-09-26-ice-research-roadmap.md"
          },
          {
            "id": "G5-2",
            "description": "动物前判断由专业团队与机构流程执行；数值 pass 不代替该评审。",
            "provenance": "proposed: 2026-09-26-ice-research-roadmap.md"
          }
        ]
      }
    ],
    "artifact_categories": [
      "data",
      "figure",
      "report",
      "protocol",
      "code",
      "other"
    ],
    "dashboard_widgets": [
      "current_stage",
      "current_gate",
      "gate_progress",
      "blocking_issues",
      "recent_runs",
      "open_risks",
      "evidence_summary",
      "tasks"
    ],
    "navigation": [
      {
        "id": "overview",
        "name": "概览"
      },
      {
        "id": "research",
        "name": "研究"
      },
      {
        "id": "runs",
        "name": "研究记录"
      },
      {
        "id": "evidence",
        "name": "证据"
      },
      {
        "id": "tasks",
        "name": "任务"
      },
      {
        "id": "milestones",
        "name": "里程碑"
      },
      {
        "id": "artifacts",
        "name": "研究文件"
      },
      {
        "id": "notes",
        "name": "笔记"
      },
      {
        "id": "decisions",
        "name": "决策"
      },
      {
        "id": "timeline",
        "name": "时间线"
      }
    ],
    "custom_views": [
      {
        "id": "probe_architecture",
        "name": "探头架构"
      },
      {
        "id": "acoustic_screening",
        "name": "声学筛选"
      },
      {
        "id": "beam_steering",
        "name": "声束偏转"
      },
      {
        "id": "sequential_scanning",
        "name": "顺序扫描"
      },
      {
        "id": "imaging",
        "name": "成像"
      },
      {
        "id": "kwave_validation",
        "name": "k-Wave 验证"
      },
      {
        "id": "electroacoustics",
        "name": "电声特性"
      },
      {
        "id": "hydrophone_measurement",
        "name": "水听器测量"
      },
      {
        "id": "material_response",
        "name": "材料响应"
      },
      {
        "id": "thermal_flow",
        "name": "热与流动"
      },
      {
        "id": "dual_function_coexistence",
        "name": "双功能共存"
      },
      {
        "id": "tank_validation",
        "name": "水槽验证"
      },
      {
        "id": "phantom_ex_vivo",
        "name": "模型体与离体验证"
      }
    ]
  }
}""")
TABLES = [
    "projects",
    "research_questions",
    "hypotheses",
    "milestones",
    "tasks",
    "research_runs",
    "parameters",
    "metrics",
    "sources",
    "artifacts",
    "evidence",
    "claims",
    "notes",
    "decisions",
    "risks",
    "tags",
    "stage_gates",
    "gate_criteria",
]


def upgrade():
    op.add_column("projects", sa.Column("module_version", sa.String(80), nullable=True))
    op.add_column("projects", sa.Column("module_snapshot", sa.JSON(), nullable=True))
    dialect = op.get_bind().dialect.name
    for mid, definition in FROZEN_V01.items():
        escaped = json.dumps(definition, ensure_ascii=False).replace("'", "''")
        literal = "'" + escaped + "'"
        if dialect == "postgresql":
            literal += "::json"
        op.execute(
            sa.text(
                "UPDATE projects SET module_version='0.1.0', module_snapshot="
                + literal
                + " WHERE module_id='"
                + mid
                + "'"
            )
        )
    with op.batch_alter_table("projects") as batch:
        batch.alter_column(
            "module_version", existing_type=sa.String(80), nullable=False
        )
        batch.alter_column("module_snapshot", existing_type=sa.JSON(), nullable=False)
    for table in TABLES:
        for field in ("archived_at", "trashed_at"):
            op.add_column(
                table, sa.Column(field, sa.DateTime(timezone=True), nullable=True)
            )
            op.create_index("ix_" + table + "_" + field, table, [field])
    op.execute("UPDATE projects SET archived_at=updated_at WHERE status='archived'")
    op.create_table(
        "object_deletions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("owner_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("object_key", sa.String(500), nullable=False, unique=True),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.String(100), nullable=True),
    )
    op.create_index("ix_object_deletions_owner_id", "object_deletions", ["owner_id"])
    op.create_index(
        "ix_object_deletions_project_id", "object_deletions", ["project_id"]
    )
    if dialect == "postgresql":
        op.execute(
            "CREATE FUNCTION researchhub_audit_append_only() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'audit_logs is append-only'; END; $$"
        )
        op.execute(
            "CREATE TRIGGER audit_logs_append_only BEFORE UPDATE OR DELETE ON audit_logs FOR EACH ROW EXECUTE FUNCTION researchhub_audit_append_only()"
        )
    elif dialect == "sqlite":
        for action in ("UPDATE", "DELETE"):
            op.execute(
                "CREATE TRIGGER audit_logs_no_"
                + action.lower()
                + " BEFORE "
                + action
                + " ON audit_logs BEGIN SELECT RAISE(ABORT, 'audit_logs is append-only'); END"
            )


def downgrade():
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute("DROP TRIGGER audit_logs_append_only ON audit_logs")
        op.execute("DROP FUNCTION researchhub_audit_append_only()")
    elif dialect == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS audit_logs_no_update")
        op.execute("DROP TRIGGER IF EXISTS audit_logs_no_delete")
    op.drop_table("object_deletions")
    for table in reversed(TABLES):
        for field in ("trashed_at", "archived_at"):
            op.drop_index("ix_" + table + "_" + field, table)
            op.drop_column(table, field)
    op.drop_column("projects", "module_snapshot")
    op.drop_column("projects", "module_version")
