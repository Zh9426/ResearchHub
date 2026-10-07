# Sync Protocol 草案 0

状态：**DECIDED**，未提供 HTTP Sync API。生产 wire format/签名与限额仍需 Sprint 1 后评审；原型直接函数调用、明文合成数据。

## 协商与消息

Hello 提交 device UUID、membership_epoch、支持 protocol/schema 范围、模块 snapshot hash、项目选择及 cursors。返回每项目 `COMPATIBLE / READ_ONLY / UPGRADE_REQUIRED / RESNAPSHOT_REQUIRED`。可解码旧 schema 用显式版本适配；不能处理新字段、事件或 module binding 就停止该项目写入。协议不支持时不拉取并误标成功。解密失败与 schema 失败分别报告。

```json
{
  "protocol_version": 1,
  "transaction_id": "UUID",
  "idempotency_key": "same-as-transaction-id",
  "device_id": "UUID",
  "project_id": "UUID",
  "schema_version": 1,
  "changes": [
    {
      "change_id": "UUID", "object_type": "Parameter", "object_id": "UUID",
      "operation": "update", "base_revision": "sha256:BASE",
      "parents": ["sha256:BASE"], "payload": {"value": 1.6, "unit": "MPa"},
      "actor_type": "human", "created_at": "ISO-8601",
      "module_snapshot_hash": "sha256:FROZEN"
    }
  ],
  "change_count": 1,
  "digest": "sha256:CANONICAL-SEMANTIC-BATCH",
  "commit_marker": "COMMIT"
}
```

该例展示**加密前业务含义**，不能原样发给真实 Relay。真实外层 Envelope 只包含必要路由/因果引用、密文与签名；actor、科学值、Audit before/after 等在密文内。Relay 知道关联、流量大小和时间，不知道参数内容。

## 事务与 Push

创建 Run + Parameters + Metrics + 三份 Artifact metadata 是**一个** SyncTransaction，内部多个 ChangeSet，不是数个可部分可见的独立提交。文件 bytes 不在这个数据库事务内；元数据先标 pending/unavailable，文件校验和独立 receipt 后才切换 verified_available。

1. 本地先验证业务规则，原子保存 domain/outbox/audit；保留唯一 transaction_id 和 digest，重试不得产生新 ID。
2. Relay 以 staging 收完整个签名批次，验证数量、顺序、digest、成员资格、schema 与 commit marker。超过限额拒绝；部分 staging 无法被 Pull 看见。
3. 在一个持久事务内检查去重键和父引用，提交日志、head index、receipt 及新项目 seq。崩溃重启后只可能无记录或完整 COMMITTED；staging 超时清理不影响已提交批次。
4. 同 transaction/change ID 且同内容返回原 receipt；同 ID 异内容返回 `IDENTITY_COLLISION`，禁止 UPDATE 原记录。未知 base 返回 `DEPENDENCY_REQUIRED`，保留本地队列、请求依赖并按拓扑重试。
5. 已知 base 是唯一 head 时返回 `STORED`。base 已有后继/其他 head 返回 `CONFLICT_STORED` 并**保存分叉候选**，不覆写旧版本；与用户例中的“conflict”语义一致。密文 ACK 只说明 Relay 保管，客户端业务验证后才能说 accepted。
6. 若客户端发现批次任何业务冲突/无权限/版本不兼容，整批转 candidate/quarantine；不能只应用 Run 而遗漏参数。无冲突的其他批次仍可处理。Conflict payload 与对应审计不能丢失。

批次批准是可重新评估的 Domain 投影，不是删除不可变历史。需要 `transaction ↔ revision` 成员索引及批次依赖图：后到分叉若使先前已显示的某成员冲突，同一原批次的全部成员一起转“待审查”，以同一数据库事务撤回其 accepted 投影；所有记录/候选/Audit 仍保留，新建 Run 也不能留下半个已批准视图。依赖受影响科研状态的后续批次一起暂停，独立批次继续。显示共同基线与完整候选，不把这种可见性调整冒充删除已保存数据。人工解决/批准须绑定当前所有相关 heads 和候选批次，原子选择完整业务组合并记录审计；部分字段选择不能偷偷批准余下未检查成员。该全批次科学批准/依赖屏障是**正式实现的必需机制，本原型尚未实现或验证**。

Relay 对 opaque parents 的校验不是科学语义验证。被攻破的成员伪造 Human 标签仍应被各客户端拒绝；签名、解密、Human 权限和字段规则失败不进入业务视图。

## Pull 与本地提交

按 `(project_id, relay_seq)` 请求 cursor 之后的**完整已提交批次**；分页以批次为边界，page limit 不可切一半 transaction，超大批次单独拒绝/下载，不能假装完成。响应包含 next_cursor、watermark、batch digest/receipt；校验序列单调连续，缺页请求缺段，禁止凭响应最大值跨过未处理批次。

每个批次在一个本地数据库事务内：验证 envelope/权限/schema/parents → 幂等 inbox insert → 保存所有 revision/candidate → 更新 domain 或 conflict/quarantine → append audit → cursor advance。应用中崩溃整体 rollback；重拉同 seq/ID 不改变对象、审计及游标。冲突已完整、持久保存后可前移 transport cursor，但单独记录 pending conflicts，不能称 domain 全部 applied。

对于依赖不全或不能解密的批次，原始密文可持久放入 quarantine inbox；只有在 inbox 与 quarantine 记录同事务完成时才允许前移 transport cursor。另有 applied watermark/未解决队列；若原型直接拒绝并保持 cursor，则明确是较保守的实现。绝不能“跳过坏消息后显示全绿”。

## 恢复、压缩和 Bootstrap

新设备选择项目、接受受信设备配对密钥，下载 signed encrypted snapshot。snapshot cursor 如 490000；先验证 manifest/完整性/模块/schema，在临时 store 构造完整对象、heads、tombstones、冲突、审计索引，然后原子切换，并重放 490001+。设备自己的未 ACK 变化先导出/保留，不能被 snapshot 替换。blob 延迟下载。

低于 compaction floor 的设备返回 RESNAPSHOT_REQUIRED，旧编辑若历史 BASE 不在快照/保留历史则进入人工 missing-base review，不能自动 rebase 覆盖。快照与 changelog tail 必须有重叠安全窗口/单调锚点；发布快照后才可按 [保留规则](SYNC_ARTIFACT_POLICY.md) 清理旧日志。

解决冲突是人工 domain mutation，包含所有 expected_heads 与理由，生成多父新 revision 和 `resolve_sync_conflict` Audit。若头集合改变返回 conflict；两次离线解决也可能成为新分叉，不能以最后提交的答案覆盖。详细 [状态机](SYNC_STATE_MACHINE.md) 与 [失败矩阵](SYNC_FAILURE_RECOVERY.md)。
