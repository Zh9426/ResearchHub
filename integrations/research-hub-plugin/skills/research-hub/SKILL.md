---
name: research-hub
description: 使用已连接的 Research Hub MCP 查询科研项目、记录与证据，或按用户要求回写参数、指标、笔记及任务。
---

使用宿主已配置的 Research Hub MCP，先通过 get_projects 找到目标项目，读取 get_project_summary 和所需记录。返回分页时依据 total 继续查询，不能把第一页视为全量。

科研字段遵守 Hub 的来源边界：未知值使用 null，未知单位留空，零必须保留。区分假设、模拟、测量与验证。未经证据支撑的值不得补齐为实际结果。

创建记录时使用 create_run 的明确类型与目标；基于已有记录迭代使用 clone_run，并说明修改内容。使用 upsert_run_parameters 和 save_run_metrics 保存结构化数据，来源、适用条件与验证状态随值保留。笔记用 create_note，计划用 create_task，候选证据用 create_proposed_evidence。

人类负责确认参数、人工结论、接受决策、通过关卡与科研证据验证。AI 分析不能写入人工结论。只有用户明确要求星标某记录，才调用 set_run_highlight 并设 user_requested=true；不要因指标看起来最好而自动星标。

追踪研究依据使用 get_evidence_trace，迭代差异使用 compare_runs。register_artifact 仅关联同项目已有文件，不读取任意服务器路径。

写入后使用 get_run 或查询 API 结果核对，报告记录 ID、实际保存内容与限制。科研失败与软件执行失败分别记录。API 拒绝时保留事实，不换用 SQL、shell 或网页点击绕过权限。
