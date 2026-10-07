# Research Hub v0.2.0 Release 验收

日期：2026-10-07（Asia/Shanghai）。应用基线 `89020d30aee07b608b4b47d614f20e24dab75741`。本次重新执行当前代码，未引用历史报告代替测试。RH-008 仅修复公开状态检查与发布文档不一致，不新增功能或修改应用数据模型。

## 发布基线

稳定主线 `main`、annotated tag `v0.2.0` 与 GitHub Release 应指向本轮 RH-008 封版提交。Release 名称：**Research Hub v0.2.0 — Modular Research Workspace**。用户明确授权仓库 Public；可见性检查只读，不再自动恢复 Private。原始 [V0.2_REPORT.md](V0.2_REPORT.md) 保留为开发完成时的历史证据，其旧私有状态由本报告更新。

版本能力：Modular Research Workspace、Capability System、Human/AI authority、Research lineage、Evidence traceability、Highlight system、Activity/Audit、Codex local MCP integration。18 个语义工具和 3 个兼容别名；本地科研数据库和文件不随公开代码发布。

## 本次重新验证

| 验证项 | 实际结果与范围 |
|---|---|
| Backend/MCP | 当前应用 HEAD 的 `tests/backend tests/mcp`：127 passed，4 个已知第三方/恶意 ZIP 测试输入警告。 |
| Release checker | `tests/release`：10 passed。先红后绿验证移除自动可见性写入、可选预期匹配、导入保护、认证不输出与 CI 查询。 |
| Frontend/TypeScript | 46 passed；tsc 无错误。Vite 扩展名提示保留。 |
| Production build | 原生 Next.js 生产构建、Docker API/Web/固定版本 MinIO 源码镜像构建均通过。 |
| Ruff | apps/api、apps/mcp、scripts、tests 通过。 |
| Docker Compose / PG / MinIO | 隔离 project `researchhub-v02-qa`，API/Web/PG/MinIO 启动并健康；个人端口和卷不参与测试。 |
| Migrations | 离线 SQL 生成通过；新建空 QA PostgreSQL 从 0001 迁移至 0005_connected，41 张表（含版本表）、0 用户，未复用个人数据库。临时检查初次使用了不存在的 parameter_revisions 表名，修正断言后新目标复测通过。 |
| 实际服务功能 | 当前镜像的认证、三模块、Run/参数/指标、Human/AI 权限、星标、能力与冻结快照、Activity/Audit、文件字节 SHA-256、证据/关卡降级、克隆/谱系、导入/导出及真实 PG 并发等，共21个实时 pytest 用例通过。包含2项真实STDIO MCP测试。 |
| Restart | 重启隔离四服务后，已有负结果 Run、Audit、MinIO 文件字节/校验值保留，1 passed。 |
| Backup/Restore | 停止 QA 写入后，PG dump 和 MinIO zip 恢复至全新数据库/桶，所有表行数及探针文件字节 SHA-256 一致，1 passed。实际服务pytest合计23项。 |
| Codex local MCP smoke | 已登录 Codex CLI 0.160.1 实际七工具调用及 HTTP 读回通过；marker `f3532ba5`，100.03秒。参数/指标零、未知单位、合成来源、笔记、显式星标、codex/mcp审计、空人工结论与临时令牌撤销均通过。未替换成协议客户端。 |

服务测试写入明确标识 SYNTHETIC 的隔离 QA 项目；测试替身和 SQLite 单元检查不作为真实服务验收。真实 smoke 使用进程范围已信任 CA 与指定七工具授权，没有改全局 Codex 设置或关闭 TLS。

## 个人数据安全

任何 QA 数据库动作前，停止个人 API/Web 写入并创建备份 `storage/backups/v020-release-20261007-063111/`：PostgreSQL dump、MinIO objects.zip、原始列快照和 SHA-256 manifest。当前个人桶有 0 对象，空桶备份仍存在；40 张原表、145 条原记录。恢复个人服务后逐行核对原始列保持，当前迁移仍为 0005_connected；无账号重置、数据覆盖、QA 导入或个人 MinIO 修改。桌面入口与本机 API/Web 健康检查通过。

## 封版修正

- README/AGENTS/CONTRIBUTING 尊重用户最新 Public 决定，保留科研数据与凭据不进 Git 的约束；修正 MCP 数量说明。
- check-github.py 移除 PATCH/--ensure-private，使用可选 --expect-visibility 与只读 GET。新增10项回归并纳入CI，规格与质量审查通过。
- README/CHANGELOG 和本报告明确稳定版本内容；历史报告不删除。

## 未验证与未实现

- ChatGPT Web/Desktop/Mobile 远程 MCP、宿主 Plugin 安装、实体手机/平板/PWA/相机/真实视频未验证。
- 完整真实 HTTP/UI 模块升级链未验收：现有 SQLite 全链、真实 PG 升级/行锁与浏览器预览分开报告。
- ChatGPT Remote MCP、Local-first 多端同步、完整 MATLAB/COMSOL Agent 未实现；不得写入 Release 已实现能力。
- 人工判断边界、未知单位、合成来源与科研负结果保持原有含义；软件验收不是科研验证。

## 冻结规则

发布后不得移动/重建 v0.2.0 标签，也不在 codex/researchhub-v0.2 继续开发。下一分支仅从该 tag 创建 `codex/researchhub-v0.3`；Sprint 0 只设计及隔离合成原型，人工架构审查之前不实施生产同步。
