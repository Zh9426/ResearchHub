# Sync Protocol — Kernel 与 Secure Transport QA

状态：semantic wire v1已冻结，内层Kernel验收见[SPRINT_1_REPORT.md](SPRINT_1_REPORT.md)。Sprint2已实现标准密码、可信生命周期、实际HTTPS Relay及客户端PG原子接收，仅限合成loopback QA；最终整体验收状态见[SPRINT_2_REPORT.md](SPRINT_2_REPORT.md)。尚无生产Relay/同步API。Sprint0原型仅为历史证据，编码不再作为规范入口。

## 协商与消息

架构层Hello拟协商device/membership、protocol/schema、模块snapshot、项目和cursors，以及每项目`COMPATIBLE / READ_ONLY / UPGRADE_REQUIRED / RESNAPSHOT_REQUIRED`；这份完整协商/UI设计尚未全部实现。Sprint2实际HTTP hello字段和返回值以Task3最终[Relay契约](SYNC_RELAY.md)为准，必须验签及当前授权，hello不能自注册或取得Project Key。未知版本/字段/module binding不能静默丢弃或误标成功，解密失败与内层schema判定分开处理。

唯一规范入口为 [SYNC_WIRE_FORMAT.md](SYNC_WIRE_FORMAT.md) 与 `fixtures/sync/v1` 固定样例。semantic transaction不含自己的digest/commit_marker/state；外层为`{transaction,digest,commit_marker:"COMMIT"}`。ChangeSet不包含base_revision别名或嵌入revision，parents本身表达BASE。科研值采用`{"value_type":"decimal","value":"1.600","unit":"MPa"}`，UUID/时间/hash均按wire严格格式，不能照搬Sprint0占位值。

Sprint1明文QA envelope仅是历史内层测试入口。Sprint2使用[SecureEnvelope](SYNC_SECURE_ENVELOPE.md)严格外层：完整签名/AAD、密文与digest，解密后重新验证canonical semantic transaction/digest/project/device/dependencies，不能以外层签名跳过业务权限。算法已双端验证，Task3网络集成证据见两份Task3 QA记录。签名HTTP proof与immutable request response契约见[安全增量](SPRINT_2_SECURITY_DELTA.md)及ADR026。

## 事务与 Push

创建 Run + Parameters + Metrics + Artifact metadata 是**一个** SyncTransaction，内部多个 ChangeSet，不是数个可部分可见的独立提交。文件 bytes 不在这个数据库事务内；v1 元数据先标 pending，文件校验和独立 receipt 后才允许 verified_reference。

以下是Secure Transport与既有Kernel已实现的QA集成契约：

1. 本地先验证业务规则并保存domain/outbox/audit；封装时预约新nonce并缓存完整canonical SecureEnvelope。网络重试使用缓存原bytes，不重新seal；semantic transaction_id/digest不因wrapper变化。
2. Relay只验证严格HTTP proof、公共envelope字段/签名/digest/current membership/epochs/role/prefix及限额；它不解密、解析科研payload或验证Human grant/科学parents，不生成scientific accepted/conflict判定。部分上传不可见。
3. Relay项目行锁内原子保存完整ciphertext、message identity、continuous sequence/chain、original receipt与quota，sync_commit完成后才返回RELAY_STORED。崩溃只可无记录或完整持久记录；当前部署QA仅验证进程/网络故障，不承诺磁盘冗余。
4. 同messageID同完整bytes返回原durable receipt，异bytes拒绝碰撞，新ID重nonce拒绝；fresh current authorization必须先于任何receipt lookup。不同wrapper可携带同semantic transaction，客户端Kernel按原transaction/change identity幂等，异semantic内容的身份碰撞仍拒绝。
5. 客户端预验证整页连续chain、历史manifest、签名、解密及semantic映射后，在同一个QA Kernel Session提交outer receipt/cursor/checkpoint与内层apply。外层stored/received不等于accepted；有效已存旧epoch仅transport quarantine，不送Kernel；无效签名/未知history/gap不推进cursor。
6. 若客户端发现批次任何业务冲突/无权限/版本不兼容，整批转 candidate/quarantine；不能只应用 Run 而遗漏参数。无冲突的其他批次仍可处理。Conflict payload 与对应审计不能丢失。

批次批准是可重新评估的Domain投影。`transaction ↔ revision`成员索引及依赖图支持后到分叉撤回原批次全部accepted projection，递归暂停依赖、保留独立批次。历史/Audit永不因此删除。人工full-batch review须覆盖受影响原批次全部对象；只解决pressure不能批准未审查的其他参数。Sprint0未实现此屏障；Sprint1 QA实测范围见报告和 [SYNC_TRANSACTION_MODEL.md](SYNC_TRANSACTION_MODEL.md)。

Relay的公共签名与路由校验不验证科学parents或Human权限。被攻破的成员伪造Human标签仍由可信客户端和Kernel拒绝；签名、解密、Human权限和字段规则失败不进入accepted业务视图。

## Pull 与本地提交

按当前授权proof及opaque project/cursor请求之后的完整SecureEnvelope；最多100条且response总bytes受限，不能切开单message。每条包含sequence、envelope digest和chain，科学accepted watermark由客户端Kernel维护，不能信任Relay替它判定。校验序列连续，缺页停止，禁止凭响应最大值跨过未处理记录。

客户端先预验证完整page的chain/历史manifest/签名/解密/semantic绑定，再在同一个QA PostgreSQL Session中调用既有Kernel并保存outer receipt/cursor/chain/signed checkpoint。应用中异常/提交前进程退出整体rollback；重拉同wrapper或同semantic transaction不增加Kernel序列/Audit/revision。内层candidate/quarantine完整持久后可记transport已处理，但必须保留科研未决状态，不能称scientific accepted。

外层坏签名/AEAD、未知可信history、错误epoch绑定、canonical损坏或gap全部ERROR，不推进cursor。仅已durable旧epoch且已pin历史manifest/签名/chain完整可验证的记录允许TRANSPORT_QUARANTINED，同事务保存并推进outer cursor而不进入Kernel。内层依赖/权限/schema判定仍遵循Sprint1语义；传输与科学水位分离，不能跳过坏消息显示全绿。

## 恢复、压缩和 Bootstrap

以下完整snapshot建库/切换/tail和compaction为DESIGNED ONLY；Sprint2仅实现签名加密snapshotmanifest及小合成state验证，不实施全量bootstrap或GC。

新设备选择项目、接受受信设备配对密钥，下载 signed encrypted snapshot。snapshot cursor 如 490000；先验证 manifest/完整性/模块/schema，在临时 store 构造完整对象、heads、tombstones、冲突、审计索引，然后原子切换，并重放 490001+。设备自己的未 ACK 变化先导出/保留，不能被 snapshot 替换。blob 延迟下载。

低于 compaction floor 的设备返回 RESNAPSHOT_REQUIRED，旧编辑若历史 BASE 不在快照/保留历史则进入人工 missing-base review，不能自动 rebase 覆盖。快照与 changelog tail 必须有重叠安全窗口/单调锚点；发布快照后才可按 [保留规则](SYNC_ARTIFACT_POLICY.md) 清理旧日志。

解决冲突是人工 domain mutation，包含所有 expected_heads 与理由，生成多父新 revision 和 `resolve_sync_conflict` Audit。若头集合改变返回 conflict；两次离线解决也可能成为新分叉，不能以最后提交的答案覆盖。详细 [状态机](SYNC_STATE_MACHINE.md) 与 [失败矩阵](SYNC_FAILURE_RECOVERY.md)。

## QA authority 与兼容入口

principal由隔离QA受信注册上下文解析，payload actor_type不能升级身份。登录会话与scientific grant分开；final人工结论、参数确认、验证证据、Gate通过、Decision接受与模块升级需要绑定transaction摘要/对象/操作/当前完整heads/设备会话/expiry的fresh Human grant。Codex、ChatGPT、System均不能签发或借用这些权限。

在线resolve在项目行锁内重新比较完整heads，陈旧请求返回CONFLICT_CHANGED。离线resolution仅是proposal，没有final Human权限；两个合法proposal可成为RA/RB新冲突，随后必须fresh人工review。离线final confirmation不支持。

模块hash不匹配或未知schema进入QUARANTINED/UPGRADE_REQUIRED；保存receipt与received cursor不等于accepted watermark。任何candidate、暂停依赖或quarantine都不能显示fully_synced。未知字段不会静默舍弃。

QA只使用`researchhub_sync_kernel_qa`，显式`HUB_SYNC_QA=1`与loopback/数据库/角色校验；不回退产品DATABASE_URL、不新增生产migration，不开启生产HTTP/UI。
