# Research Hub v0.2.0

稳定产品与标签为 **v0.2.0**。[v0.3 Sync Sprint 0 报告](docs/sync/SPRINT_0_REPORT.md) 位于从该标签创建的 `codex/researchhub-v0.3` 分支：同步架构、14份设计/报告文档与隔离合成原型。它没有给当前应用增加生产同步、加密、移动离线引擎或 ChatGPT 远程连接；完成本轮后等待人工架构审查。原型运行方法见 [prototype README](prototypes/sync_sprint0/README.md)。

个人科研工作系统：项目、研究问题、假设、Run、参数来源、指标、文件、证据与结论共同形成可追溯的工作记录。Generic、HDSP、ICE 共用 Core，通过模块 manifest 保留各自专业工作流。

代码仓库：[Zh9426/ResearchHub](https://github.com/Zh9426/ResearchHub)，按用户明确决定为 **Public**。数据库、上传文件、凭据与备份保存在本地，不随 Git 提交。稳定主线为 `main`，封版标签为 `v0.2.0`；后续开发从此标签开始，不继续改动 v0.2 开发线。

## 从零启动

### 当前电脑直接使用（已准备原生环境）

桌面已建立 **Research Hub** 快捷方式，双击会自动启动本机 PostgreSQL、MinIO、API 和 Web，并打开浏览器。服务已运行时直接进入，不重复启动。也可双击仓库中的 `打开ResearchHub.cmd`。所有入口使用个人数据库，不创建账号或自动导入数据。

重新建立桌面入口可执行 `.\scripts\create-desktop-shortcut.ps1`；脚本保留同名已有快捷方式。后台数据保存在被忽略的 `storage/runtime/`，关闭浏览器不会停止存储服务。

当前电脑已准备真实 PostgreSQL17.11、MinIO 与生产 Web/API，可打开 [Research Hub](http://localhost:3000) 登录使用；新数据库首次创建自己的账户。个人数据库与验收数据库独立；没有预设个人账户或自动导入演示数据。若进程已停止：

```powershell
Set-Location H:\ResearchHub
.\scripts\native-qa.ps1 -Action Start
.\scripts\native-app.ps1 -Action Start
```

停止应用使用 `.\scripts\native-app.ps1 -Action Stop`；停止存储服务使用 `.\scripts\native-qa.ps1 -Action Stop`，均保留数据。这是 localhost 原生运行方式；新电脑的安装步骤见 [DEVELOPMENT](docs/DEVELOPMENT.md)，手机网络访问仍需下述 Docker/LAN HTTPS 验收。

### Docker Desktop 部署

安装 Docker Desktop，启用 WSL2/Linux containers；Windows 提示重启时先保存工作并完成重启。确认 Docker Desktop 已运行后，在 PowerShell 执行：

```powershell
Set-Location H:\ResearchHub
.\scripts\setup.ps1
.\scripts\start.ps1
```

打开 [Research Hub](http://localhost:3000)，首次创建自己的账户（密码至少 12 位）。setup 自动生成独立随机数据库与对象存储秘密，保留已有 `.env`；不提供默认账户或密码。首次构建需要下载依赖并编译固定版本 MinIO。

登录后创建 Project，选择 Generic Research、HDSP 或 ICE Sonocuring。在 Settings 可以**主动**生成明确标识为 `DEMO / SYNTHETIC` 的演示项目；这些示例不代表真实实验，也不会自动导入私人科研数据。

```powershell
.\scripts\stop.ps1
```

停止保留数据库与对象存储卷。不要用 `docker compose down -v` 停止系统，它会删除数据。备份和恢复见 [BACKUP](docs/BACKUP.md)。

## 使用能力

- 用户登录、HttpOnly 会话、CSRF、项目所有权隔离、受范围限制的 API Token。
- Project / Research Question / Hypothesis / Task / Milestone / Run / Evidence / Claim / Source / Note / Decision / Risk 的实际 API 与页面编辑。
- Parent / Child Run、参数来源与 unknown/null、指标、Run 对比；AI Analysis 与 Human Conclusion 分开保存，科研负结果与运行失败独立。
- Artifact 上传到 MinIO，数据库保存关系、SHA256 和 metadata；授权后下载，限制文件类型和大小。
- Stage/Gate 判据、关联证据、状态与阻塞原因；ICE 为 A–E 和 G0–G5，HDSP 为固定目标面声场—热—固化流程。
- 审计时间线、三模块演示项目、响应式桌面/手机界面、PWA manifest/service worker。
- 本地 stdio MCP 18 个语义工具和 3 个兼容别名复用同一 API、授权与审计，不提供 shell、SQL 或任意服务器文件访问。

## v0.2 研究工作流与互联

新增模块冻结版本与人工升级、组合能力、渐进 Run 创建/编辑、独立星标、活动与审计分离、分页检索、Bundle 预览导入、项目导出、参数/指标历史与完整差异、谱系及证据追踪、模块驱动视图和手机尺寸快速采集。项目与 Run 可保存 GitHub 代码来源。

Codex 连接配置与 Skill/插件包见 [CONNECTIONS](docs/CONNECTIONS.md)，工具契约见 [MCP](docs/MCP.md)。实际客户端、ChatGPT 和设备验证范围见 [v0.2 验收报告](docs/V0.2_REPORT.md)。

`v0.2.0` = Modular Research Workspace + Capability System + Human/AI authority + Research lineage + Evidence traceability + Highlight system + Activity/Audit + Codex local MCP integration。封版重新运行的测试、备份和限制见 [v0.2.0 Release 验收](docs/RELEASE_V0.2.0.md)。ChatGPT Remote MCP、多端 Local-first sync 和完整 MATLAB/COMSOL Agent 均未实现。

## 验证与限制

已完成实际 Docker PostgreSQL/MinIO/API/Web 启动、持久化与备份恢复验收；隔离测试与实际服务验收分别报告。最终范围见 [v0.2 验收报告](docs/V0.2_REPORT.md)，v0.1 历史限制保留在原报告中。

手机与电脑访问同一个本机服务器。局域网 HTTPS 与本地证书信任步骤见 [DEVELOPMENT](docs/DEVELOPMENT.md)。PWA 不缓存科研 API，也不支持离线编辑。ChatGPT、实体设备与 PWA 安装结果以 v0.2 报告为准；本地 STDIO 和宿主连接分开验收。

当前使用优先级为电脑端。手机与平板端保留现有响应式结构，本轮不打包或部署移动入口。系统预置界面、状态、模块阶段和表单使用简体中文；专业缩写、数据标识与用户录入内容保留原样。

## 开发

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r apps/api/requirements.txt -r apps/mcp/requirements.txt
.\.venv\Scripts\python.exe -m pytest tests/backend tests/mcp -q -p no:cacheprovider
Set-Location apps/web
npm ci
npm test
npm run build
```

直接运行 API 必须配置真实 PostgreSQL 和 MinIO 并先执行 Alembic 迁移，步骤见 [DEVELOPMENT](docs/DEVELOPMENT.md)。SQLite 和内存对象适配器只用于隔离测试。

| 文档 | 内容 |
|---|---|
| [ARCHITECTURE](docs/ARCHITECTURE.md) | 服务边界与存储 |
| [DATA_MODEL](docs/DATA_MODEL.md) | 表与关系、参数来源 |
| [MODULE_SYSTEM](docs/MODULE_SYSTEM.md) | Generic / HDSP / ICE 差异 |
| [EVIDENCE_MODEL](docs/EVIDENCE_MODEL.md) | 证据状态、结论与科研边界 |
| [DESIGN_SYSTEM](docs/DESIGN_SYSTEM.md) | UI 与响应式设计 |
| [MCP](docs/MCP.md) | 语义工具、Token 与连接状态 |
| [BACKUP](docs/BACKUP.md) | 备份与空目标恢复 |
| [CHANGELOG](CHANGELOG.md) | 每次迭代与实际验证 |

提交采用 `type(scope): 中文摘要`，正文包含提交详情、迭代说明、验证结果、后续工作。规则见 [CONTRIBUTING](CONTRIBUTING.md)。
