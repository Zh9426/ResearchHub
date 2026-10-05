# 证据与来源边界

证据状态支持 unknown、hypothesis、assumed、synthetic、simulated、measured、calibrated、validated、reproduced、rejected。Parameter/Source 的 source_kind 支持 unknown、synthetic、assumed、literature、manufacturer、measured、calibrated、derived。

AI Analysis 不会自动成为 Evidence 或 Human Conclusion。Claim 通过关系表关联多个 Evidence、Run、Artifact、Source；Evidence 可追溯到具体运行、文件或文献，并保存 limitations。用户可以记录 rejected 证据与阴性结果。

Passed Criterion 必须关联同项目证据；unknown/hypothesis/assumed/rejected 不足以通过。Passed Gate 必须每一条 Criterion 均 passed，且 Gate 自身关联证据。Blocked Gate 必须说明原因。Synthetic/Simulated 证据的边界仍需用户在描述及 limitations 中明示；系统不把模拟门槛通过解释成临床或现实实验验证。ICE 动物前判断另须专业团队和机构程序。

所有关键数据写入与 AuditLog 在同一事务内；before/after 保存变化。审计包括 actor、actor_type、action、resource、source、timestamp、request_id。Web actor 为 human；可信 API Token 的签发属性决定 MCP actor 为 codex/chatgpt，客户端请求头不能覆盖。Token secret 与密码从不写入审计。

删除记录通过数据库外键 CASCADE/SET NULL 清理关联；AuditLog 保留历史快照。审计中已删除资源仅表示过去写入，不表示当前证据仍存在。使用 PostgreSQL 与对象备份一起保全科研数据。
