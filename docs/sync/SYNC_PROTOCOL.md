# Sync Protocol — Sprint 1 QA Kernel

状态：wire v1已冻结，QA实现与验收证据见 [SPRINT_1_REPORT.md](SPRINT_1_REPORT.md)。未提供HTTP Sync API、生产Relay或真实签名。Sprint0原型仍为历史证据，其示例编码不再作为规范入口。

## 协商与消息

Hello 提交 device UUID、membership_epoch、支持 protocol/schema 范围、模块 snapshot hash、项目选择及 cursors。返回每项目 `COMPATIBLE / READ_ONLY / UPGRADE_REQUIRED / RESNAPSHOT_REQUIRED`。可解码旧 schema 用显式版本适配；不能处理新字段、事件或 module binding 就停止该项目写入。协议不支持时不拉取并误标成功。解密失败与 schema 失败分别报告。

唯一规范入口为 [SYNC_WIRE_FORMAT.md](SYNC_WIRE_FORMAT.md) 与 `fixtures/sync/v1` 固定样例。semantic transaction不含自己的digest/commit_marker/state；外层为`{transaction,digest,commit_marker:"COMMIT"}`。ChangeSet不包含base_revision别名或嵌入revision，parents本身表达BASE。科研值采用`{"value_type":"decimal","value":"1.600","unit":"MPa"}`，UUID/时间/hash均按wire严格格式，不能照搬Sprint0占位值。

QA envelope可以携带合成signature/key_epoch/nonce/ciphertext metadata，但没有实现加密认证。未来真实外层Envelope只包含必要路由、密文和签名；该设计尚未部署。

## 事务与 Push

创建 Run + Parameters + Metrics + Artifact metadata 是**一个** SyncTransaction，内部多个 ChangeSet，不是数个可部分可见的独立提交。文件 bytes 不在这个数据库事务内；v1 元数据先标 pending，文件校验和独立 receipt 后才允许 verified_reference。

1. 本地先验证业务规则，原子保存 domain/outbox/audit；保留唯一 transaction_id 和 digest，重试不得产生新 ID。
2. Relay 以 staging 收完整个签名批次，验证数量、顺序、digest、成员资格、schema 与 commit marker。超过限额拒绝；部分 staging 无法被 Pull 看见。
3. 在一个持久事务内检查去重键和父引用，提交日志、head index、receipt 及新项目 seq。崩溃重启后只可能无记录或完整 COMMITTED；staging 超时清理不影响已提交批次。
4. 同 transaction/change ID 且同内容返回原 receipt；同 ID 异内容返回 `IDENTITY_COLLISION`，禁止 UPDATE 原记录。未知 base 返回 `DEPENDENCY_REQUIRED`，保留本地队列、请求依赖并按拓扑重试。
5. 已知 base 是唯一 head 时返回 `STORED`。base 已有后继/其他 head 返回 `CONFLICT_STORED` 并**保存分叉候选**，不覆写旧版本；与用户例中的“conflict”语义一致。密文 ACK 只说明 Relay 保管，客户端业务验证后才能说 accepted。
6. 若客户端发现批次任何业务冲突/无权限/版本不兼容，整批转 candidate/quarantine；不能只应用 Run 而遗漏参数。无冲突的其他批次仍可处理。Conflict payload 与对应审计不能丢失。

批次批准是可重新评估的Domain投影。`transaction ↔ revision`成员索引及依赖图支持后到分叉撤回原批次全部accepted projection，递归暂停依赖、保留独立批次。历史/Audit永不因此删除。人工full-batch review须覆盖受影响原批次全部对象；只解决pressure不能批准未审查的其他参数。Sprint0未实现此屏障；Sprint1 QA实测范围见报告和 [SYNC_TRANSACTION_MODEL.md](SYNC_TRANSACTION_MODEL.md)。

Relay 对 opaque parents 的校验不是科学语义验证。被攻破的成员伪造 Human 标签仍应被各客户端拒绝；签名、解密、Human 权限和字段规则失败不进入业务视图。

## Pull 与本地提交

按 `(project_id, relay_seq)` 请求 cursor 之后的**完整已提交批次**；分页以批次为边界，page limit 不可切一半 transaction，超大批次单独拒绝/下载，不能假装完成。响应包含 next_cursor、watermark、batch digest/receipt；校验序列单调连续，缺页请求缺段，禁止凭响应最大值跨过未处理批次。

每个批次在一个本地数据库事务内：验证 envelope/权限/schema/parents → 幂等 inbox insert → 保存所有 revision/candidate → 更新 domain 或 conflict/quarantine → append audit → cursor advance。应用中崩溃整体 rollback；重拉同 seq/ID 不改变对象、审计及游标。冲突已完整、持久保存后可前移 transport cursor，但单独记录 pending conflicts，不能称 domain 全部 applied。

对于依赖不全或不能解密的批次，原始密文可持久放入 quarantine inbox；只有在 inbox 与 quarantine 记录同事务完成时才允许前移 transport cursor。另有 applied watermark/未解决队列；若原型直接拒绝并保持 cursor，则明确是较保守的实现。绝不能“跳过坏消息后显示全绿”。

## 恢复、压缩和 Bootstrap

新设备选择项目、接受受信设备配对密钥，下载 signed encrypted snapshot。snapshot cursor 如 490000；先验证 manifest/完整性/模块/schema，在临时 store 构造完整对象、heads、tombstones、冲突、审计索引，然后原子切换，并重放 490001+。设备自己的未 ACK 变化先导出/保留，不能被 snapshot 替换。blob 延迟下载。

低于 compaction floor 的设备返回 RESNAPSHOT_REQUIRED，旧编辑若历史 BASE 不在快照/保留历史则进入人工 missing-base review，不能自动 rebase 覆盖。快照与 changelog tail 必须有重叠安全窗口/单调锚点；发布快照后才可按 [保留规则](SYNC_ARTIFACT_POLICY.md) 清理旧日志。

解决冲突是人工 domain mutation，包含所有 expected_heads 与理由，生成多父新 revision 和 `resolve_sync_conflict` Audit。若头集合改变返回 conflict；两次离线解决也可能成为新分叉，不能以最后提交的答案覆盖。详细 [状态机](SYNC_STATE_MACHINE.md) 与 [失败矩阵](SYNC_FAILURE_RECOVERY.md)。

## QA authority 与兼容入口

principal由隔离QA受信注册上下文解析，payload actor_type不能升级身份。登录会话与scientific grant分开；final人工结论、参数确认、验证证据、Gate通过、Decision接受与模块升级需要绑定transaction摘要/对象/操作/当前完整heads/设备会话/expiry的fresh Human grant。Codex、ChatGPT、System均不能签发或借用这些权限。

在线resolve在项目行锁内重新比较完整heads，陈旧请求返回CONFLICT_CHANGED。离线resolution仅是proposal，没有final Human权限；两个合法proposal可成为RA/RB新冲突，随后必须fresh人工review。离线final confirmation不支持。

模块hash不匹配或未知schema进入QUARANTINED/UPGRADE_REQUIRED；保存receipt与received cursor不等于accepted watermark。任何candidate、暂停依赖或quarantine都不能显示fully_synced。未知字段不会静默舍弃。

QA只使用`researchhub_sync_kernel_qa`，显式`HUB_SYNC_QA=1`与loopback/数据库/角色校验；不回退产品DATABASE_URL、不新增生产migration，不开启生产HTTP/UI。
