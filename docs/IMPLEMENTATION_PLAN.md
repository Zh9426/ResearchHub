# Research Hub v0.1 Implementation Plan

> **For agentic workers:** 使用 superpowers:subagent-driven-development 与 dispatching-parallel-agents；后端、前端、部署/MCP 分属独立文件目录，集成后进行需求与代码审查。

**Goal:** 交付个人科研系统：可认证、持久化、模块化、桌面/手机/PWA 可用。

**Architecture:** Next.js 通过同源 `/api` 代理访问 FastAPI；SQLAlchemy/Alembic 管理 PostgreSQL；Artifact 字节进入 MinIO，关系与校验摘要进入数据库。模块 manifest 定义科研语义，Application Service 对 Web 与 MCP 共用授权和审计。

**Tech Stack:** Next.js/React/TypeScript、FastAPI、SQLAlchemy、Alembic、PostgreSQL、MinIO、Docker Compose、pytest、MCP Python SDK。

用户完整需求保存在 `docs/V0.1_REQUIREMENTS.txt`。用户明确授权直接实施，本轮不设置额外设计确认门槛。

## 固定集成合同

- 所有 Web API 位于 `/api`，JSON 响应为对象或对象数组，不包额外 envelope。
- `GET /api/auth/status` 返回 `{setup_required: boolean}`；`POST /api/auth/setup` 与 `/login` 接受 `{email,password,display_name?}`，返回 user 与 csrf_token；`GET /api/auth/me` 返回同一结构；`POST /api/auth/logout` 退出。
- HttpOnly 会话 Cookie；认证后的写请求携带 `X-CSRF-Token`。同源代理；生产 HTTPS 下 Secure Cookie。
- `GET /api/modules` 列出 manifest；`GET /api/modules/{id}` 返回单一 manifest。
- `GET|POST /api/projects`；`GET|PATCH|DELETE /api/projects/{id}`；`GET /api/projects/{id}/context` 返回 `{project,module,runs,tasks,milestones,questions,hypotheses,evidence,claims,sources,notes,decisions,risks,artifacts,gates,activity}`。
- 项目子集合：`GET|POST /api/projects/{id}/{runs|tasks|milestones|questions|hypotheses|evidence|claims|sources|notes|decisions|risks|tags|gates}`。
- `GET|PATCH|DELETE /api/{collection}/{id}`；资源 ID 为 UUID 字符串，所有访问验证项目所有者。
- `GET /api/runs/{id}/context` 返回 `{run,parameters,metrics,artifacts,evidence,parent,children,changes_from_parent}`。
- `GET|POST /api/runs/{id}/parameters` 与 `/metrics`；条目可 PATCH/DELETE；批量 metrics 的 MCP 工具复用服务。
- `GET /api/projects/{id}/artifacts`；`POST` 为 multipart（file, run_id 可选, category, metadata JSON 可选）；`GET /api/artifacts/{id}/download` 经过授权提供下载。
- `GET /api/activity` 与 `/api/tasks` 为当前用户全局集合；Audit 包含 actor_type/source/request_id/before/after。
- 模块 manifest 为 `packages/project-modules/{generic|hdsp|ice-sonocuring}/manifest.json`。schema 项为 `{id,name,value_type,unit,description?}`；stages 为 `{id,name,description}`；gates 为 `{id,name,description,stage_id,criteria:[{id,description,provenance}]}`。
- Claim 存储多条 evidence_ids/run_ids/artifact_ids/source_ids；Gate 存储 criteria、evidence_ids、blocking_reason；Decision 存储 evidence_ids。
- 自动化令牌由登录用户创建，数据库只存摘要，范围 `research:read` / `research:write`；MCP API 使用 Bearer token，写操作 actor_type 为 codex 或 chatgpt，由可信 MCP 服务指定，普通 Web 用户不能冒充。

## 实施与验证清单

- [x] 后端：实体关系、迁移、参数来源、三模块、认证、授权、审计、Artifact、demo seed；pytest 验证完整科研流程与隔离。
- [x] 前端：先概念图与 Design System，再真实 API 页面；Home、项目、Run、compare、research、evidence、tasks、files、notes、decisions、stage/gate、activity、settings。
- [x] 实现部署/MCP：Compose、Dockerfile、HTTPS 手机访问选项、PWA、安全 MCP 工具、备份恢复脚本与必要说明。
- [x] 安装运行依赖，实际启动原生 API/Web/PostgreSQL/MinIO，执行集成测试。
- [x] 浏览器实际操作桌面/平板/手机视口页面并截图，第二轮审查和修复。
- [x] 原生全部服务重启后的数据持久化、备份恢复测试；真实 API 的本地 MCP read/write/scopes 测试。
- [ ] Docker 构建启动与命名卷重启；Windows 虚拟化组件等待系统重启。
- [ ] 实体手机 LAN HTTPS、PWA 实际安装；不能用响应式视口或 worker ready 替代。
- [ ] 最终需求覆盖与代码审查、提交迭代详情、推送私有 GitHub 分支。

## 设计基线

白色工作面、浅灰导航、深灰文字、低饱和 teal 动作色。字体为系统 sans，数值与 ID 用 monospace。4/8px 间距，6px 圆角、1px 分隔线，表格和状态列表优先，44px 触摸目标，可见键盘焦点。桌面固定左导航；手机顶部项目选择与底部最多 5 项导航，宽表格在自己的区域滚动。DEMO/SYNTHETIC 必须持续可见。

ICE 工作流依据：`H:\print_transducer\docs\superpowers\plans\2026-09-26-ice-research-roadmap.md`。保留 A–E 与 G0–G5，不导入旧科研结果或假设设备参数。HDSP 按固定目标面声场—热—固化流程组织，不把当前厚度相位板称为严格超表面透镜。
