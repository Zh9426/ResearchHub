# 开发路线

## 已确定要求

- 面向个人使用的科研进度 Hub。
- 在当前项目目录开发。
- GitHub 仓库名 `ResearchHub`，保持私有。
- 每次 commit 写清提交详情和迭代说明。

## RH-000：开发基础

- [x] 初始化本地仓库。
- [x] 写入提交和迭代管理规范。
- [x] 创建并确认 GitHub 私有仓库（RH-001）。
- [x] 将初始提交推送到 `origin/main`，核对提交 SHA（RH-001）。

## RH-001：GitHub 连接

- [x] 创建私有仓库 `Zh9426/ResearchHub`。
- [x] 配置 `origin` 并建立主分支跟踪关系。
- [x] 验证初始提交已同步，更新连接状态文档。

## RH-002：Research Hub v0.1

- 已实现 Next.js/FastAPI/PostgreSQL/MinIO 的 Core、Module 与工作流。
- 已实现 Generic / HDSP / ICE、参数来源、证据与 Claim 关联、Run 对比、审计、响应式界面与本地 MCP。
- 实际运行与环境验收结果集中记录在 [V0.1_REPORT](V0.1_REPORT.md)，保留未验证项目。
- Docker 引擎在当前 Windows 上等待虚拟化组件重启；不自动重启电脑。

## 下一版建议（尚未实现）

1. 在重启后的 Docker/局域网 HTTPS 上完成部署回归、真机 PWA 与恢复演练，加入 CI。
2. 扩展可筛选搜索、分页、标签关联与科研证据反向追踪。
3. 导入本地实验结果与项目 GitHub Commit/Issue/PR 进度，导入前展示来源与冲突。
4. 提供参数、指标与证据的版本历史，以及 Gate 支撑失效的完整影响视图。
5. 验证外部 ChatGPT/Codex MCP 接入；按平台需要添加 HTTPS/OAuth 服务，保留最小授权和审计。
