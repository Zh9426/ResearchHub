# 本地连接与外部宿主

更新时间：2026-10-07。PostgreSQL/MinIO 仍由本机 Research Hub 控制；连接结果以验收报告为准。

## Codex 本地 MCP

设置页面创建专属 Codex 令牌，默认只读；需要回写时选择 research:write。把令牌写入被忽略的 `storage/runtime/mcp-local.json`，仅本机保管：

```json
{"api_url":"http://localhost:3000","token":"填写自己的 Hub 令牌"}
```

将 `integrations/codex/config.example.toml` 的 MCP 段放入宿主的项目配置（或在 MCP 设置填入同样的 command/args/cwd）。当前电脑使用仓库 `.venv` Python 与 `scripts/mcp-local.py`。示例不含凭据，不会自动改写宿主或全局设置。也可由启动环境传入 RESEARCHHUB_API_TOKEN 与 RESEARCHHUB_API_URL；验收仅指向隔离 QA。

连接包 `integrations/research-hub-plugin/` 包含 portable plugin.json 与 Research Hub Skill，可供本地导入。包内不注册虚构的远程 app ID；STDIO 连接按上述配置单独启用。未实际安装的宿主插件不能视为安装成功。

[官方 MCP 文档](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)说明 STDIO 的 command、args、cwd 与 env_vars 配置。[插件包装文档](https://developers.openai.com/plugins/build/plugins)说明根目录 plugin.json、skills 与本地分发结构。此包用于个人本地连接，没有公开发布。

## ChatGPT Web / Desktop / Mobile

当前交付本地 STDIO；ChatGPT 云端不能直接访问本机 localhost。远程 HTTP/OAuth 生产接入与实际宿主连接尚未验证，不能把本地协议通过写成 ChatGPT 已连接。

[Secure MCP Tunnel](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels)提供出站通道，需 Platform 创建的 tunnel_id、运行密钥、关联目标工作区及使用权限；仍需要本机客户端持续运行。Tunnel 不等于公开插件分发。当前没有配置这些凭据或扩大网络访问权限。

Remote MCP HTTPS 是另一连接方式，需要稳定 HTTPS 地址和对应认证。[官方认证文档](https://developers.openai.com/plugins/build/auth)说明 OAuth 授权码、PKCE S256、元数据发现和用户授权；Hub 现有个人 API 令牌不能冒称已完成 OAuth。推荐下一阶段接入短期、可撤销的范围令牌与完整 OAuth，而非把长期令牌放进公开配置。

## 实际 Codex 验收

2026-10-07 使用已登录的 Codex CLI 0.160.1，通过本地 STDIO 和隔离 QA 的真实 PostgreSQL/MinIO 服务完成查询项目、创建 Run、保存参数/指标、添加笔记、显式星标和读回。工具结果及 HTTP 读回共同校验，审计 actor_type=codex、source=mcp；临时令牌已撤销。个人服务的持久令牌与全局 Codex 配置没有自动改写；本机长期使用仍需按上面的配置启用。

初次连接遇到证书信任错误，随后将 Windows 已信任的公共根证书导出为本机 PEM，通过进程环境 `CODEX_CA_CERTIFICATE` 指定；没有关闭 TLS 校验或修改证书库。[官方 CA 配置](https://learn.chatgpt.com/docs/auth)支持该环境变量。非交互客户端还需要工具授权：验收只在临时配置中授权本次七个工具，且逐工具配置置于服务器整表配置之后。[官方配置参考](https://learn.chatgpt.com/docs/config-file/config-reference)说明逐工具 approval_mode；这不等于给日常连接开放全部操作。

可重复验收脚本 `scripts/codex-acceptance.py` 固定指向 disposable QA；诊断、令牌和证书仅放被忽略的 storage/runtime，不入 Git。脚本要求七个工具成功事件、正确数值/来源及撤销成功同时成立，否则记录 NOT VERIFIED。

## GitHub

项目的数据管理可保存 GitHub 仓库 URL，Run 的代码来源可保存仓库、分支、提交 SHA 和同仓库 Issue/PR 链接。链接只表示已登记来源；是否存在、仓库权限和提交内容由 GitHub 页面核对，不虚构同步状态或科学结果。ResearchHub 开发仓库必须保持私有。
