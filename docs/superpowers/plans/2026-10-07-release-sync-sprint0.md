# Research Hub 封版与 Sync Sprint 0 执行计划

> **For agentic workers:** 使用 superpowers:subagent-driven-development 逐任务执行并进行规格、质量两阶段审查；用户授权本轮完成隔离原型，架构人工审查位于 Sprint 0 交付之后。不得开始 Sprint 1。

**Goal:** 重新验收并发布 v0.2.0，然后从该标签创建 v0.3 分支，交付业务级同步设计和隔离合成原型。

**Architecture:** v0.2 应用及生产数据库冻结。v0.3 原型为独立 Python/SQLite 设备副本和 Relay simulator，不导入应用数据库或原生环境凭据；设计文档明确尚未实现的网络、加密和设备能力。

**Tech Stack:** 当前 Next.js/FastAPI/PostgreSQL/MinIO；原型 Python 标准库 sqlite3、UUID、hashlib 和 pytest。设计引用官方存储与密码标准文档。

## A：封版（RH-008）

- [ ] 核对当前 HEAD、跟踪分支和远端主线。当前基线 89020d3；先停止个人写入，运行 `python -m scripts.native-backup --label v020-release`，检查 PG dump、MinIO archive 和 manifest 校验值，恢复个人服务。
- [ ] 重新执行 `pytest tests/backend tests/mcp`、Web `npm run test/typecheck/build`、Ruff、Alembic 离线 SQL、Docker API/Web build 和 QA Compose。全部运行结果存入忽略的 runtime，文档只记录结果和脱敏路径。
- [ ] 隔离 QA 执行 tests/integration 中实时服务/MCP/并发等检查。停止写入后执行 test_compose_recovery；重启后执行 test_persistence。真实 Codex smoke 运行 scripts/codex-acceptance.py，要求七工具成功、HTTP 读回、审计与撤销均成立。
- [ ] 只修复封版阻断/安全/文档不一致。README、AGENTS、CONTRIBUTING 与 GitHub 检查脚本须尊重用户最新“公开”决定，不自动改回私有。修复脚本时新增回归并验证先红后绿。
- [ ] 新建 docs/RELEASE_V0.2.0.md，更新 README/CHANGELOG，保留 docs/V0.2_REPORT.md。记录当前重新运行结果及仍未验证能力。
- [ ] 检查暂存区，提交四段中文正文；同步 v0.2 分支。拉取远端 main，确认祖先关系后合并稳定主线，拒绝强推。创建 annotated `v0.2.0` tag 并推送；创建 GitHub Release，内容来自已验证报告。验证 tag/main/Release 目标 SHA 与 CI。

## B：架构与隔离原型（RH-009）

- [ ] `git switch -c codex/researchhub-v0.3 v0.2.0`，保存原始请求到 docs/sync/SPRINT_0_REQUIREMENTS.txt；不修改生产应用、迁移或部署。
- [ ] 建立 docs/sync/ 下用户指定的12份协议/决策文档、ER 图和最终报告。每份链接到具体 Research Hub 类型；建立 B1–B39 覆盖表。
- [ ] 比较 integer/server sequence/vector/HLC/content revision，明确离线因果关系、冲突和 Relay 游标的不同作用；协议包含 batch、commit marker、idempotency、版本检查和恢复状态机。
- [ ] 定义全部对象的冲突矩阵、生命周期/模块/人工权限规则。科学字段同基分叉必须冲突；Primary 不决定胜者；永久删除仅设计。
- [ ] 设计 E2E、配对、撤销、轮换、恢复、Relay保留/bootstrap、移动 IndexedDB/OPFS/cache与 AI bridge 取舍；依据成熟官方标准，标明决策待人工批准和生产未实现。
- [ ] 原型文件 prototypes/sync_sprint0/{model,relay,replica}.py、测试 tests/sync_prototype/test_sync_cases.py。测试先行：离线创建/独立创建、同参数分叉、重复 push/pull、batch中断、同 SHA dedup、trash/edit、人工结论分叉、审计去重至少10案例。
- [ ] 先运行失败测试，再实现最小协议；补身份/幂等键碰撞、rollback/cursor、损坏文件、禁purge/越权/未知schema和并发解决负向用例。仅使用 tmp_path 合成 SQLite/文件，无真实数据库配置和网络监听。
- [ ] 执行原型测试、Ruff和演示；规格后质量独立复审并修复。修改仅限 docs/sync、prototypes、原型tests和README/CHANGELOG/计划。
- [ ] 报告采用 DECIDED/PROTOTYPED/OPEN QUESTION/NOT IMPLEMENTED，覆盖22主题，明确原型不证明生产安全。提交RH-009并推送v0.3，验证以v0.2.0为祖先且稳定tag未改变。
- [ ] 输出“Research Hub v0.3 Sync Architecture Sprint 0 complete.”，列需人工确认决策，STOP。
