# Research Hub v0.1

个人科研工作系统：项目、研究问题、假设、Run、参数来源、指标、文件、证据与结论共同形成可追溯的工作记录。Generic、HDSP、ICE 共用 Core，通过模块 manifest 保留各自专业工作流。

代码仓库：[Zh9426/ResearchHub](https://github.com/Zh9426/ResearchHub)，保持 **Private**。数据库、上传文件、凭据与备份保存在本地，不随 Git 提交。开发分支为 `codex/researchhub-v0.1`。

## 从零启动

### 当前电脑直接使用（已准备原生环境）

当前电脑已准备真实 PostgreSQL17.11、MinIO 与生产 Web/API，可先打开 [Research Hub](http://localhost:3000) 创建自己的账户。个人数据库与验收数据库独立；没有预设个人账户或自动导入演示数据。若进程已停止：

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
- 本地 stdio MCP 九个工具复用同一 API、授权与审计，不提供 shell、SQL 或任意服务器文件访问。

## 验证与限制

**实现不等于全部验收完成。** 当前设备的 Docker 引擎受 Windows 虚拟化组件重启要求阻塞。Compose 配置检查、单元/协议测试与实际运行验收的具体状态，以 [v0.1 验收报告](docs/V0.1_REPORT.md) 为准；未验证事项会单独列出。

手机与电脑访问同一个本机服务器。局域网 HTTPS 与本地证书信任步骤见 [DEVELOPMENT](docs/DEVELOPMENT.md)。PWA 不缓存科研 API，也不支持离线编辑。外部 ChatGPT/Codex MCP 连接未验证；当前交付本地 stdio 服务和配置说明。

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
| [MCP](docs/MCP.md) | 九个工具、Token 与连接状态 |
| [BACKUP](docs/BACKUP.md) | 备份与空目标恢复 |
| [CHANGELOG](CHANGELOG.md) | 每次迭代与实际验证 |

提交采用 `type(scope): 中文摘要`，正文包含提交详情、迭代说明、验证结果、后续工作。规则见 [CONTRIBUTING](CONTRIBUTING.md)。
