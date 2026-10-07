# Sync Sprint 0 合成原型

仅验证两台设备与 Relay simulator 的一致性机制。所有示例为合成数据，SQLite 文件只使用测试的 `tmp_path` 或演示的 `TemporaryDirectory`。不导入 Research Hub 应用、不读取配置/凭据、不连接 PostgreSQL/MinIO、不监听网络。

从仓库根目录运行：

```powershell
.venv\Scripts\python.exe -m pytest tests/sync_prototype -q
.venv\Scripts\ruff.exe check prototypes/sync_sprint0 tests/sync_prototype
.venv\Scripts\python.exe -m prototypes.sync_sprint0.demo
```

`model.py` 定义业务 ChangeSet、严格 JSON、内容 hash 和不可变 revision DAG；`relay.py` 原子提交 batch、保存项目内 sequence 和幂等 receipt；`replica.py` 持久保存设备 UUID、本地 outbox，以及 inbox/domain/audit/cursor 的原子 apply。`state()` 返回公共祖先 `projection`、所有 `heads`/`candidates` 和 `conflict`，不会根据接收顺序选科研值。

Relay 必须预注册合成 `device_id → human/ai` principal。`push()` 的调用上下文决定权限，ChangeSet 的 actor claim 必须与注册 principal 一致；不一致在提交前拒绝，不能提升权限或产生无法 replay 的已 ACK 批次。此上下文由测试直接提供，**不是真实认证、设备签名或离线人工确认**。Pull 信任 simulator 提供的 principal；hash 只能检测内容不一致，不能认证来源。

34 个参数化用例包含要求的 CASE 1–10，以及身份碰撞、apply rollback、损坏字节、未知 schema/type、purge、AI 伪造 actor claim、principal/actor 不一致的原子拒绝、并发解决、缺失依赖、乱序重试、重启、分项目/key epoch 去重和严格数字/字段校验。

原型保证与限制：

- Batch 的 revision/audit/blob 写入全部提交或全部回滚；未 commit 的内容不可 Pull。ACK 仅表示传输持久化，冲突候选会保留。单个对象的冲突 projection 停在公共祖先。尚未实现跨对象批次的科学批准屏障：同一 batch 中其他无冲突对象可正常显示。
- Replica 的普通 helper 每次 mutation 产生一个持久 outbox batch；多对象事务通过 `Relay.push([changes...], transaction_id, device_id)` 演示，尚未实现应用层事务适配器。
- 缺失 base 或游标前缀时整批 quarantine，cursor 不前进，依赖到达后需显式重试。未知版本/类型直接拒绝，未实现兼容迁移。
- 并发编辑与并发解决都形成分叉。解决必须消费本地精确 head 集合；Relay 允许基于共同旧 head 集合的并发解决，继续显示冲突。Trash/edit 保留冲突且保持 trashed；解决后恢复仍需显式 restore；purge 被禁止。
- Artifact metadata UUID 独立；合成明文字节按 `(project_id, key_epoch, SHA-256)` 去重并校验。无跨项目去重，无真实加密，也无大型文件/分块/缓存/上传协议。
- `plaintext-simulator` 仅占位；无网络、真实账户、E2E、签名、撤销、配对、密钥管理、bootstrap、retention、移动存储或生产 resolver。Python 排序 JSON 并非跨语言 JCS/RFC 8785。
- 故障测试注入事务内 Python 异常，不证明断电/文件系统/多进程并发容错；DAG 查询未针对长历史优化。本原型不是生产服务验收。

关联设计：[Sync architecture](../../docs/sync/SYNC_ARCHITECTURE.md)、[protocol](../../docs/sync/SYNC_PROTOCOL.md)、[test plan](../../docs/sync/SYNC_TEST_PLAN.md)。Sprint 0 之后停止，等待人工架构审查。
