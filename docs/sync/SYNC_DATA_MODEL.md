# 业务同步数据模型

状态：**DECIDED** 是拟冻结设计；**PROTOTYPED** 仅覆盖 Python 合成模型。以下均为概念实体，不是生产 migration。

## Revision 方案比较

| 方案 | 离线/跨设备与冲突 | 恢复、审计及 AI 写入 | 成本与结论 |
| --- | --- | --- | --- |
| 单对象 integer | 离线双方都可生成 19，单值不足以识别来源 | 需要中央分配及额外历史 | 简单，但不能独自表达离线分叉 |
| Lamport logical clock | 表达偏序的兼容排序，单值无法充分判断并发 | 可排序事件，不能把较大值当胜者 | 低成本，可作诊断而非冲突依据 |
| vector clock | 能检测因果/并发；需维护设备维度 | 离线设备撤销及向量压缩复杂 | 正确可行；个人系统不是首选 |
| Hybrid logical clock | 改善排序和时间展示，仍需父版本检测并发 | 时钟偏差可诊断，不能证明因果或 Human 权限 | 可作为展示字段，不作科研合并规则 |
| Relay server sequence | 有序传输、分页简单，离线不能预分配 | 好用的恢复游标；收到顺序不能解释谁修改谁 | 只用作每项目传输游标 |
| 不可变 revision DAG + 内容摘要 | 父引用表达因果；多 head 明确并发，UUID 离线创建 | 审计、重试、AI proposal 可追溯；保留历史便于恢复 | 推荐；成本是历史、缺失父版本和压缩处理 |

**推荐**：`revision = sha256(canonical_change)`，每对象不可变 DAG；一般变化 `parents=[base_revision]`，create 为 `[]`，解决冲突为全部 `expected_heads`。revision 摘要绑定 change_id、transaction_id、project/object/type、设备/actor、operation、parents、payload、schema 与时间等语义字段，排除 Relay seq、传输重加密 nonce。签名/密文封装独立绑定摘要，防重加密造成业务重复。正文中 `base_revision` 必须等于普通单父引用；解决事件使用多父集合，不伪装普通 update。

revision 摘要不是密码学授权，created_at/updated_at 只展示，Human/AI 都服从同一分叉检测。收到相同 object_id 的两个不同 create 也是冲突，不能因 UUID 碰撞极低就覆盖。无父版本则隔离并请求依赖；找不到历史不得拿当前状态补成 BASE。多头时保存共同祖先和所有候选，正常 Domain 视图不擅自选其中之一。

## 概念实体与约束

| 实体 | 必需字段与关键约束 |
| --- | --- |
| Device | UUID、名称、角色、签名/封装公钥、membership_epoch、状态；名称不是身份 |
| DeviceProjectState | device_id/project_id、cursor、last_successful_sync、pending_change_count、selection、snapshot_anchor；每项目独立 |
| ChangeSet | change_id、transaction_id、device_id、project_id、object_type/object_id、operation、base_revision/parents、payload、actor/actor_type、created_at、schema_version、module_snapshot_hash、revision |
| SyncTransaction | transaction_id/idempotency_key、设备、项目、ordered change_ids/count/digest、protocol_version、schema、commit_marker、状态；禁止跨项目批次 |
| Envelope | project_id、key_epoch、sender membership、revision/parents、algorithm、nonce、ciphertext、signature；受签名保护的 opaque 路由字段仍会泄漏关联性 |
| ObjectRevision | object_id/type/project_id、revision、parents、materialized candidate、transaction_id、lifecycle、module binding；不可变 |
| SyncConflict | conflict_id、object_id、head_set、common_base、reason、candidate transactions、status、resolution_revision；不能只存一份 latest payload |
| AIReviewItem | review_id、proposal_revision、source_actor、review_scope/status、human review audit；独立于 SyncConflict |
| AuditLog | audit_id、change/transaction_id、device_id、actor、actor_type、timestamp、object_id、action、before/after、source；append-only，相同 ID 不同内容报错 |
| ArtifactMetadata | artifact_id、run_id、文件名/类别、size、sha256、sync_policy、origin_device、availability、key_epoch、blob locator；每份上下文元数据独立 |
| Blob/ArtifactCache | project_id/key_epoch/content locator、校验摘要/size、cache state、receipt；不以原始 SHA 作跨项目公开键 |
| Project/Module binding | module_version、冻结 module_snapshot 内容及 hash、project revision；升级是独立人工事件 |
| Snapshot | project_id、cursor anchor、manifest hash/signature、schema/key_epoch、完整对象 revision/head、冲突、Audit 去重 ID、tombstone、module snapshots |

Conceptual ReviewInbox、Device 与同步表尚未加入现有数据库。Activity 从已验证 Audit/Domain events 派生；hide_before 与 filters 推荐设备本地，未来显式账户偏好实体才可同步，不删除 Audit。

## 业务 payload 与编码

create 带允许的业务初值；update 带具体变更字段与明确 null，不上传 user/password/token/数据库内部行。Parameter 包含值、单位及来源；Metric 包含计算来源及人工确认状态；关系用 link/unlink 及 endpoint UUID、项目/类型约束。archive/trash/restore 是显式生命周期命令；purge 从普通协议拒绝。字段白名单、类型、同项目、模块与权限全部由 Domain decoder 校验。

生产候选采用 [RFC 8785 JCS](https://www.rfc-editor.org/rfc/rfc8785) 的规范编码与 SHA-256；精确科研十进制可在版本化 schema 中用 decimal 字符串，禁止 NaN/Infinity、重复 JSON key、非法 Unicode，零和 null 含义不同。Python 原型的排序 JSON **不是 JCS 的跨语言实现**，不得据此声称浏览器签名互通；正式实现需要 Python/JS 编码向量及 schema fixture。未知字段不能默默丢弃。
