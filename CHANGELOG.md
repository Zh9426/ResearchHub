# 迭代日志

每次提交均需更新本文件，按最新迭代在前记录。日期采用 Asia/Shanghai。

## RH-002 — 2026-10-05 — 实现并运行科研 Hub v0.1 主体

### 完成内容

- 建立 Next.js/FastAPI/PostgreSQL/MinIO 独立系统，29 张应用表与冻结 Alembic 迁移。
- 实现账户、Core CRUD、父子 Run、参数来源、Metrics、Artifact SHA256、Evidence/Claim 关联、Task/Milestone、Note/Decision/Risk、Stage/Gate 与审计。
- Generic/HDSP/ICE manifest 共用 Core；ICE 依据指定路线图保留 A–E/G0–G5，HDSP 保留固定目标面打印边界。
- 证据删除或降级使失去有效支持的已通过 Gate/Criteria 自动失效，并在同一事务审计。
- 实现响应式桌面/手机页面、PWA 静态离线说明、九个受范围控制的本地 MCP 工具、Compose 与备份恢复脚本。
- 准备真实原生服务供当前电脑使用；QA 数据独立且明确 SYNTHETIC。保留个人首次账户创建体验。

### 验证结果

- 后端/MCP 40、前端 18、真实 PostgreSQL/MinIO 集成 8、真实 MCP 2、服务重启持久化 1、空目标备份恢复 1，合计 70 项通过；环境与限制见 docs/V0.1_REPORT.md。
- Next.js 生产构建、Ruff、pip check、PowerShell 语法、三种 Compose config 与迁移检查通过。
- 实际浏览器桌面/平板/手机视口操作和截图，worker ready 与停服务后的静态离线回退均已验收。

### 遗留事项

- Windows 虚拟化组件等待电脑重启：Docker 完整构建启动、容器网络/命名卷、LAN HTTPS 与 Compose 恢复封装尚未运行。
- 实体手机访问/拍照与 PWA 安装、外部 ChatGPT/Codex 连接未验证；按用户标准尚未完整验收。
- 搜索分页/标签关联、对象垃圾回收、应用内 GitHub 进度读取与远程 MCP 尚未实现。

## RH-001 — 2026-10-05 — 建立 GitHub 私有仓库连接

### 完成内容

- 创建 `Zh9426/ResearchHub` 私有仓库，通过 GitHub 插件确认可见性为 `private`。
- 配置本地 `origin` 为 `https://github.com/Zh9426/ResearchHub.git`。
- 推送初始提交 `08dc717`，建立 `main` 到 `origin/main` 的跟踪关系。
- 更新项目说明、同步操作说明与开发路线，记录已完成的仓库连接。

### 验证结果

- 首次 `git push -u origin main` 成功。
- 本地与远程 `main` 初始提交 SHA 均为 `08dc717c1c90eb51a32ba9a762f788481cdb50e9`。
- 本次只更新连接状态和文档，不包含应用代码，无应用运行测试。

### 遗留事项

- 确定首版科研进度管理功能、使用方式与技术栈。
- 应用内读取科研项目的 GitHub 进展尚未实现。

## RH-000 — 2026-10-05 — 仓库与开发规范初始化

### 完成内容

- 初始化本地 Git 仓库，主分支为 `main`。
- 创建项目说明、开发约定、提交规范、提交模板和后续路线。
- 规定每次提交都包含提交详情、迭代说明、验证结果与后续工作。
- 配置常见构建产物、凭据及个人运行时数据的忽略规则。

### 验证结果

- 本次为文档与仓库初始化，不包含应用代码，无应用运行测试。
- 提交前检查文本差异与暂存文件清单。

### 遗留事项

- 创建并验证 GitHub 私有仓库，完成本地初始提交的推送（已在 RH-001 完成）。
- 确定首版功能、使用方式与技术栈。
