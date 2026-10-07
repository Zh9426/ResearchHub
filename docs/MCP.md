# MCP v0.2

本地 stdio MCP 提供 18 个语义工具和 3 个兼容别名。API 是所有权、scope、生命周期和 Human/AI authority 的统一边界；MCP 不访问数据库、不执行 shell、不读取任意服务器文件，不提供通用更新工具。协议验收、真实 PostgreSQL/MinIO 验收和真实 Codex 宿主连接是三个独立层次，实际结果见 Sprint 3 报告。

所有读集合默认 `limit=50, offset=0`，`limit` 为 1–100 的整数，`offset` 为非负整数。普通分页为 `{items,total,limit,offset}`；聚合结果的每个 `groups` 字段都有独立分页。`total` 是完整匹配集合计数，不能把第一页当全部事实。读操作默认排除回收站、归档资源及已归档项目；详情只返回当前所有者的活动资源。分页格式不会改变 Web 旧 API 的数组返回。

| READ 工具 | 参数和结果 | API |
|---|---|---|
| `get_projects` | `q?`, `limit`, `offset` → project page | `GET /api/projects?format=page` |
| `get_project_summary` | `project_id`, `limit`, `offset` → `project,module,counts,evidence_summary,groups` | `GET /api/projects/{id}/summary?format=page` |
| `search_research` | `q`, `project_id?`, `kind?`, `limit`, `offset` → text-match page | `GET /api/search` |
| `query_runs` | `project_id`, `q?`, `filters?`, `limit`, `offset` → Run page | `GET /api/projects/{id}/runs/query?active_only=true` |
| `get_run` | `run_id`, `limit`, `offset` → `run,parent,groups` | `GET /api/runs/{id}/context?format=page` |
| `compare_runs` | `run_id`, `other_run_id`, `limit`, `offset` → `current,other,groups` | `GET /api/runs/{id}/compare` |
| `get_highlighted_runs` | `project_id`, `limit`, `offset` → starred Run page | Run query，固定 `is_highlighted=true` |
| `get_current_blockers` | `project_id`, `limit`, `offset` → blocker page | `GET /api/projects/{id}/blockers` |
| `get_evidence_trace` | `project_id`, `kind`, `resource_id`, `limit`, `offset` → `subject,groups` | `GET /api/projects/{id}/evidence-trace/{kind}/{rid}` |

`get_project_summary.groups` 包含 `recent_runs`, `highlighted_runs`, `current_tasks`, `current_gates`, `current_risks`, `current_decisions`。`get_run.groups` 包含 `parameters`, `metrics`, `artifacts`, `referenced_artifacts`, `evidence`, `notes`, `children`，`parent` 为单个活动父 Run 或 null。`compare_runs.groups` 包含 `parameters`, `metrics` 两组分页差异；`current`/`other` 含真实保存的代码来源字段，不拉取 GitHub 内容。

`query_runs.filters` 只允许 `run_type`, `status`, `scientific_outcome`, `tag_id`, `parent_run_id`, `is_highlighted`, `date_from`, `date_to`, `sort`, `direction`。`q` 是文本搜索，不能通过 filters 覆盖项目或分页；布尔星标筛选在客户端转换为 API 的 `true/false`。文本通过 URL 参数编码，不能注入另一项目 ID。`search_research` 的 `project_id` 缺省时搜索当前所有者的活动项目，提供时严格限定该项目；`kind` 为项目集合名。trace 的 `kind` 只允许 `claims,evidence,runs,artifacts,sources,parameters,metrics,gates,criteria,decisions`。

阻塞项定义为：blocked Run/Task/Milestone，blocked 或 failed Gate，以及 open Risk。结果给出 `kind,id,project_id,title,status,detail,created_at`，只是已保存事实，不由 AI 推断科研关卡通过。

| WRITE 工具 | 参数及权限限制 |
|---|---|
| `create_run` | `project_id,run`；run 至少含 `title,run_type`，遵循导出 Run schema |
| `clone_run` | `run_id,clone`；clone 至少含 `title`，其余为显式继承开关；不继承确认、指标、结论、结果或星标 |
| `upsert_run_parameters` | `run_id,parameters`；按名称原子 upsert 1–100 项；AI 不可确认，也不可修改已确认参数 |
| `save_run_metrics` | `run_id,metrics`；原子 upsert 1–100 项；AI 不可升级 validated/reproduced，也不可修改已有此状态的指标 |
| `create_note` | `project_id,title,content,run_id?` |
| `create_task` | `project_id,title,description='',priority='medium'`；固定初始状态 todo |
| `register_artifact` | `run_id,file_id`；仅引用已存在的同项目、owned、活动附件；返回 `run_id,artifact,already_linked` |
| `create_proposed_evidence` | `project_id,evidence`；至少含 `title`，状态固定 proposed，显式其他状态直接拒绝 |
| `set_run_highlight` | `run_id,is_highlighted,user_requested=false,type=null,note=''`；用户显式要求时才可传 `user_requested=true`，服务层仍复核 |

所有写操作要求 `research:write`。自定义参数和指标名称可用，未知单位使用 null；标准单位与 metric schema 使用项目冻结模块。`register_artifact` 不接收路径、URL、文件内容或 arbitrary server file，附件须先由正常上传流程入库。重复注册幂等，不重复创建关系；新引用写入 `register_artifact` 审计。跨项目引用拒绝，已归档/回收站资源不可写。AI 不能写 `human_conclusion`、通过 Gate 或确认 Decision；星标与证据状态独立。

兼容工具保留 `get_project(project_id)`（活动项目详情）、`get_project_context(project_id,limit,offset)`（分页 summary 别名）、`list_runs(project_id,limit,offset)`（分页 query 别名）。v0.2 的分页结果替代旧 MCP 无限数组，调用方应检查 `items/total` 或 `groups`。

Token 由人工在 Settings 创建，只读选择 `research:read`，可写选择 `research:read,research:write`；审计身份选 `codex` 或 `chatgpt`。scope 与 actor_type 由 API 中 token 数据库记录决定，工具参数不能冒充身份。错误不向 MCP 回传可能含凭据的上游响应文本。

项目内连接脚本和插件包见 [CONNECTIONS.md](CONNECTIONS.md)。支持直接运行：

```powershell
.\.venv\Scripts\python.exe -m apps.mcp.server
# RESEARCHHUB_API_URL 和 RESEARCHHUB_API_TOKEN 由客户端秘密环境提供
```

stdio 不监听网络，不提供 HTTP/OAuth 远程 MCP。不要为 ChatGPT 连接开放公网、迁移科研数据或把本地 Token API 当远程 OAuth MCP。真实外部客户端尚未验收时须写 NOT VERIFIED。

验证命令：`.\.venv\Scripts\python.exe -m pytest tests/backend tests/mcp -q`。`tests/mcp/test_protocol.py` 使用官方 `ClientSession` 连接真实 stdio 子进程和隔离 SQLite HTTP API；这不等于 PostgreSQL/MinIO 或真实 Codex 宿主验收。`tests/integration/test_live_connected.py`、`test_live_mcp.py` 需要明确 disposable QA URL 和被忽略的 QA 凭据文件。GitHub 来源只做保存、校验、克隆和展示，不读凭据管理器、不自动调用外网或提交 Issue/PR。
