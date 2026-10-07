# ChatGPT / Codex 与 E2E 的取舍

状态：**DECIDED（推荐 A）/ OPEN QUESTION（用户的可用性与共享选择）**。本轮没有部署 ChatGPT Remote MCP 或网络 tunnel；v0.2 已验收的是本机 Codex MCP。

如果 Relay 无解密密钥，ChatGPT 不能直接从其 ciphertext 理解科研内容。任何远端 AI 阅读都需要受信节点选择、解密并把明确范围的内容交给模型；传给 AI 的这部分内容不再只停留在 E2E 终端。不能一面承诺服务器完全不知内容，一面声称 AI 可全天访问同一密文库。

| 方案 | AI 从何读取 | E2E/可用性取舍 | 建议 |
| --- | --- | --- | --- |
| A：在线 trusted client bridge | 电脑/受信终端解密并通过受限 MCP 返回用户选定数据 | Relay 保持无 key；被选内容进入远端 AI，bridge 离线即不可读 | 默认推荐，scope/项目/时间/工具分别授权 |
| B：selected AI-readable projection | 用户主动把摘要/脱敏字段发到 AI 可读的投影服务 | 可离线访问，但投影服务能解密这份副本，不能仍宣称这份数据全 E2E | 仅单独明确 opt-in，限定保存时间及审计 |
| C：project-specific AI sharing key | AI 端获得一项目受限 key 或重封装副本 | 隔离其他项目，但读取范围广、泄漏与撤销后的已读副本不可收回 | 不作默认；优先字段投影/短期 bridge |
| D：本机模型/用户手动导出 | 终端本地推理，或用户选择片段上传 | 本机推理无远端内容；能力/硬件成本不同；手动上传仍属于共享 | 需要敏感研究时可选，无自动替代效果承诺 |

“AI-readable encrypted projection”只代表存储/传输加密，若云服务持 key 就不是原 E2E 安全域。删除 projection/撤销 token 不能保证模型已读副本被遗忘；正式服务的数据政策必须另行审核。

默认 A future flow：Human 选择项目和可读字段 → trusted bridge 解密当前 accepted/candidate 状态并标明冲突/来源 → 受限工具返回 → AI 写 proposal 到当前 Domain 层 → 业务权限、审计、outbox 同事务 → 常规 Sync。不把整个项目 key 给云，不允许 AI 直接修改 conflict resolver、Human-only accepted 字段、Gate 或 module upgrade。同步后 proposal 仍进入 AIReviewItem，需要人工查看。

OpenAI 官方 [Secure MCP Tunnel](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels) 提供本地 MCP 远程访问的连接机制，可作为后续 A 的连接候选；它不替 Research Hub 设计 E2E/业务权限，也不意味着本项目已经接入或无需暴露选定明文。当前须保持 docs/CONNECTIONS.md 的实际能力边界，未来还需身份、scope、限流、撤销与用户授权验收。

Codex 继续 `Codex → Local MCP → PC Domain service`，无需 Relay 或 ChatGPT 在线。未来在现有服务同一事务增加 outbox，而不是绕过 API 直接写 PG。actor_type=codex/source=mcp 审计延续；Sync 不能把来源改成 Human。当前 v0.2 无这个 outbox，Sprint 0 原型不接入 Codex。

需人工确认：是否接受 A 的“电脑在线才可访问”；哪些项目/字段可以发送远端 AI；是否单独启用 B；内容期限与离线审查方式。ChatGPT 的真实连接、AI 分享 key、投影数据库都 **NOT IMPLEMENTED**。
