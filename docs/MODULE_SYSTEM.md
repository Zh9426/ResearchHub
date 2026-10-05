# 项目模块

同一个 Core API 与数据库承载三种工作空间。`packages/project-modules/*/manifest.json` 声明 Run Types、参数与指标模板、研究阶段、门槛、Artifact 类别、Dashboard Widgets、Navigation、Custom Views。启动时通过 Pydantic 校验 manifest；创建项目初始化该模块的 Gate 与独立 Criterion。

Generic 不含任何超声字段；以问题、假设、Run、任务、证据为中心。HDSP 为固定目标平面的全息超声表面打印，参数包含频率/目标距离/相位级数，指标包含固化 IoU、覆盖、过固化、欠固化与 Energy Efficiency。厚度相位板不被标记为严格声学超透镜。

ICE Sonocuring 按 `2026-09-26-ice-research-roadmap.md` 提炼 A–E 阶段及 G0–G5 门槛，包含数值可信度、受控比较、成像、物理验证和动物前证据审查。Manifest 描述的是拟议流程，阈值明确标为 proposed；不导入旧输出或把历史规划当作当前通过证据。unknown、失败门槛、阻塞、阴性结果和候选淘汰均可保存。

项目模块创建后固定，避免已有参数与工作流被隐式重新解释。可自由改变 current_stage，但须为 manifest 已定义阶段。通用资源 schema 不添加模块专有固定列；参数、指标和视图通过模块配置变化。

认证后显式 POST `/api/demo/seed` 建立三种 DEMO / SYNTHETIC 项目，每用户幂等。ICE 演示门槛 G0 passed、G1 in_progress、G2 blocked，仅绑定明确 synthetic 的演示证据，不代表真实研究验证。
