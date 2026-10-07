# Research Hub v0.2.0 — Modular Research Workspace

本版本正式冻结个人科研工作区：模块与能力驱动录入、Human/AI authority、研究记录谱系、证据追踪、独立星标、Activity/Audit 与真实 Codex 本地 MCP 互联。

具体功能包括四字段快捷创建、渐进编辑、参数/指标历史和完整差异、冻结 module_snapshot 与人工升级、归档/回收站/恢复、项目导出及 Bundle 人工预览确认、GitHub 代码来源。18 个语义 MCP 工具与 3 个兼容别名复用同一授权和审计边界；AI 不可代替人工确认科研结论或通过关卡。

封版当天重新执行：后端/MCP 127 项、Release 检查10项、前端46项、真实隔离PG/MinIO/API/MCP/并发/重启/备份恢复23项通过；TypeScript、Ruff、生产构建、新空PG迁移通过。真实Codex客户端七步smoke及读回通过，临时令牌撤销。个人PG和MinIO新备份后原始记录保持；未导入QA数据。

仓库按用户明确决定公开，科研数据、令牌、数据库及备份保留本机且不入Git。可见性检查现在为只读；不会自动更改仓库访问状态。

明确限制：ChatGPT Remote MCP、Local-first多端同步和完整MATLAB/COMSOL Agent未实现；实体设备/PWA、插件安装及真实HTTP/UI全程模块升级尚未验收。SQLite单元测试、真实服务和宿主smoke分开报告，软件合成验收不代表科研结果。

详见仓库 `docs/RELEASE_V0.2.0.md` 和保留的 `docs/V0.2_REPORT.md`。稳定主线与v0.2.0标签冻结后，后续工作从标签创建codex/researchhub-v0.3；架构Sprint0之后须等待人工审查，不自动启动生产同步。
