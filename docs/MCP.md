# MCP v0.1

状态：**IMPLEMENTED：本地 stdio MCP Server**。外部 ChatGPT/Codex 配置连接状态：**EXTERNAL INTEGRATION NOT VERIFIED**。本地协议与 API 授权测试的实际结果见最终验证报告；服务器存在不等于外部平台已经连通。

使用官方 Python SDK `mcp==1.26.0` 的 FastMCP，仅提供九个工具：

| 工具 | API | 范围 |
|---|---|---|
| get_projects | GET /api/projects | research:read |
| get_project | GET /api/projects/{id} | research:read |
| get_project_context | GET /api/projects/{id}/context | research:read |
| list_runs | GET /api/projects/{id}/runs | research:read |
| get_run | GET /api/runs/{id}/context | research:read |
| create_run | POST /api/projects/{id}/runs | research:write |
| save_run_metrics | POST /api/runs/{id}/metrics/batch | research:write |
| create_note | POST /api/projects/{id}/notes | research:write |
| create_task | POST /api/projects/{id}/tasks | research:write |

所有工具调用共享 API 应用服务。scope 不是 MCP 客户端传入的可信声明；API 根据 Token 数据库记录执行授权。只读 token 即使调用写工具也得到 403。项目/Run UUID 在适配器先验证，API 再检查真实存在性与所有权。错误内容不向 MCP 回传上游可能含凭据的响应文本。

先启动系统、注册登录。在 Settings 创建 token（只读建议仅 `research:read`；要写入则同时选择 `research:write`），选择审计身份 `codex` 或 `chatgpt`。Token 仅显示一次，通过客户端环境变量传入，绝不保存到仓库。

```powershell
.\.venv\Scripts\python.exe -m pip install -r apps/mcp/requirements.txt
$env:RESEARCHHUB_API_URL = 'http://localhost:3000'
# RESEARCHHUB_API_TOKEN 由凭据管理器或客户端秘密环境提供
.\.venv\Scripts\python.exe -m apps.mcp.server
```

支持 MCP stdio 客户端的配置示意（token 使用客户端秘密环境机制，勿把占位符直接当密钥）：

```json
{"command":"H:\\ResearchHub\\.venv\\Scripts\\python.exe","args":["-m","apps.mcp.server"],"cwd":"H:\\ResearchHub","env":{"RESEARCHHUB_API_URL":"http://localhost:3000"}}
```

stdio 不监听网络、不依赖公网，也不实现 HTTP/OAuth MCP 连接器。要使用要求远程 HTTPS/OAuth 的外部平台，仍需下一轮专门集成；不能把本地 token HTTP API 当作已通过官方远程连接验证。

本地测试：`.\.venv\Scripts\python.exe -m pytest tests/mcp -q`。协议测试通过官方 `ClientSession` 建立进程并执行 initialize/list_tools/call_tool；集成测试验证读 scope 拒绝写和写入审计身份。

参考：[官方 Python SDK v1.26.0](https://github.com/modelcontextprotocol/python-sdk/tree/v1.26.0)。
