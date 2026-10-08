# Sprint 0 Architecture Decision Records

共同状态：**DECIDED = 本轮推荐、待人工批准**，不是生产已实现或用户已批准。原型只验证部分机制；未决项需要在进入正式实现前回答。

2026-10-07 Sprint 1 增量：用户已明确授权实现QA Kernel；不等于批准生产Relay/E2E/手机同步。ADR-003/006 的JCS候选部分 **AMENDED**：保留其Unicode/排序原则，新增ADR-011/012冻结受限数值wire；旧Sprint0证据不改写。实现与运行证据见SPRINT_1_REPORT（完成后交付）。

## ADR-001 — Why Local-first

**Context**：个人电脑、手机和平板会离线，记录 Run/Note/Task 不能依赖主电脑常在线。

**Options**：always-online 中央业务 DB；单机+手工导出；每端本地状态+异步加密 Relay。

**Decision**：推荐第三种。离线编辑允许的业务对象，待同步状态明确；Primary 负责完整存储。

**Consequences**：需要 outbox、revision/conflict、设备密钥与恢复，复杂度增加；网络不再是查看/草稿保存的唯一条件。

**Open Questions**：离线最终 Human 确认能力、浏览器配额下的 rescue UX、支持的首批实体设备。

## ADR-002 — Domain changes, not database replication

**Context**：现有 PG/MinIO 有 Human/AI 校验、项目冻结模块、Run 谱系和生命周期；原始 SQL 行没有这些命令边界。

**Options**：PG 数据库文件/Git 同步；SQL row replication；Domain ChangeSet + 同事务 outbox。

**Decision**：业务事件和 SyncTransaction；PC 保留现有存储，所有 API/Codex 路径走同一 Domain service。

**Consequences**：要显式维护 decoder、schema 与事件，不能绕过授权；MinIO/OPFS bytes 用 staged receipt，不伪装 PG 同事务。

**Open Questions**：现有每个 service 的事务入口与回滚边界、可选 outbox worker 排程和迁移验收计划。

## ADR-003 — Revision model

**Context**：共同 pressure=1.4 的离线修改必须检测并发，seq/time 无法区分因果。

**Options**：integer、Lamport、vector、HLC、serverseq、immutable DAG/content digest；完整比较见 SYNC_DATA_MODEL。

**Decision**：不可变每对象 DAG + 内容摘要 revision，UUID 离线对象/change ID；parents 判断因果，Relay seq 只作项目 cursor。

**Consequences**：保留 heads/祖先、缺父依赖隔离、解决事件多父；历史压缩需 signed snapshot；AI 与 Human 相同因果规则。

**Open Questions**：JCS Python/JS test vectors、精确 decimal schema、历史保留上限、反分叉 checkpoint 与字节成本。

## ADR-004 — Conservative scientific conflict policy

**Context**：参数、指标、Human Conclusion、Evidence/Decision/Gate/module upgrade 自动覆盖会破坏科研依据。

**Options**：LWW；通用 CRDT；科学字段人工冲突 + 明确安全集合合并白名单。

**Decision**：第三种，禁止科学 LWW。独立 Child Run/Artifact additions/Audit 可共存；文本三方只提供建议，人工结论始终需 Human。

**Consequences**：UI 需展示 BASE/候选/来源；exact head resolution 可再次分叉；prototype 只做保守冲突，不实现文本/OR-set 或整批科学 promotion barrier。

**Open Questions**：首版 safe union 字段、参数业务键、文本建议是否默认总需确认、冲突批次批准 UX。

## ADR-005 — Artifact policy

**Context**：7.8 GB MAT 和原始场不应因手机同步自动进云，小图/config 可选择共享。

**Options**：全文件复制；只存云；local_only / metadata_only / encrypted_sync / on_demand 四政策。

**Decision**：四政策，metadata eager/binary lazy；大原始文件默认 metadata_only。同项目/epoch dedup bytes，保留独立 metadata/来源。

**Consequences**：移动端知道文件位置但不保证在线；需要校验、预算、refcount 与轮换策略；公开 raw SHA 会泄漏，生产路由用 keyed locator。

**Open Questions**：小文件阈值、移动流量、敏感分类默认、长期 blob/backup 冗余及加密 dedup 工程。

## ADR-006 — Encryption and trusted device pairing

**Context**：不受信 Relay 不得默认拥有科研明文或 keys；账号密码不应自动授权全部终端。

**Options**：仅 TLS/云持 key；用户密码直接加密；客户端随机 master/project/artifact keys + 独立设备 keys + trusted pairing。

**Decision**：第三种，采用审核过的 AEAD/HPKE/Ed25519 库，具体 suite/nonce/vault 设计见 SYNC_SECURITY_MODEL。无自研弱密码算法。

**Consequences**：需 user recovery kit、撤销/rotation 和可信终端；所有 keys 丢失无法恢复；旧设备已读副本不能收回。

**Open Questions**：库维护、nonce counter 崩溃方案、vault/browser user-presence、恢复介质、撤销/透明日志与独立安全评审。

## ADR-007 — Primary PC role

**Context**：电脑现有完整 PG/MinIO、备份与 Codex；手机不应复制大数据或运行研究仿真。

**Options**：Primary 永远获胜；完全无 Full Node；Primary 只负责完整存储/备份/执行。

**Decision**：第三种。Primary 不拥有冲突额外权重，永久 purge 仍需 Human+相关状态检查。

**Consequences**：电脑离线时 metadata 工作可继续，但 PC-only bytes/AI bridge 不可用；需灾难恢复与长期备份。

**Open Questions**：是否允许第二 Full Node、备份磁盘/周期、Primary 替换及离线 ACK 参与节点。

## ADR-008 — Relay retention and bootstrap

**Context**：Relay 是暂存，不能清理未 ACK 唯一副本，也不能让新设备 replay 500000 事件。

**Options**：永久全日志；7/30 天硬删；retain-until-ack + encrypted snapshot/tail +可配置期限。

**Decision**：第三种；期限是受 durability 条件约束的目标。压缩前验证快照/tail，月离线设备先保留 pending 再重建。

**Consequences**：metadata/审计与 bytes 生命周期分离；新设备按项目选择，blob lazy；缺 BASE 的编辑需人工候选。

**Open Questions**：ACK 成员、device lease、快照周期、最小日志窗口、云费用与 durability 故障域。

## ADR-009 — Mobile local storage

**Context**：浏览器事务、文件缓存和静态 app shell 需求不同，配额/清除可丢唯一未同步数据。

**Options**：localStorage 全部存；移植 PG；IndexedDB 元数据/outbox + OPFS 加密 cache + CacheStorage app shell。

**Decision**：第三种，device-local UI preferences；请求 persistent storage 但不保证。首版前台手动 sync，不依赖后台唤醒。

**Consequences**：IDB 和 OPFS 无跨库事务，需 staged files；quota 停写和 rescue export；实机兼容/keys 要独立测试。

**Open Questions**：iOS/Android/平板目标版本，OPFS/CryptoKey 生命周期、缓存预算、离线用户确认 UX。

## ADR-010 — ChatGPT trade-off

**Context**：ChatGPT 远端需要可理解内容，不能直接从无 key 的 E2E Relay 读取科研密文。

**Options**：A trusted online bridge；B selected AI-readable projection；C 项目 AI key；D 本地模型/手工片段。

**Decision**：推荐 A；保持 Relay 无 key，用户显式选择字段/项目/scope，Codex 本机路径不变。B/C 只可另行 opt-in，不能隐瞒这份共享内容可被云读取。

**Consequences**：电脑在线才能供 ChatGPT 读取；远端 AI 接收的选定明文不再只在 E2E 终端，仍需服务数据政策审查；AI proposal 不获 Human 权限。

**Open Questions**：用户是否接受在线 bridge、哪些研究字段可共享、未来 Tunnel/OAuth/限流/撤销、是否需要 B 的离线可用性。

## ADR-011 — Canonical Wire Format（Sprint 1）

**Context**：Sprint0排序JSON不能证明Python/JS一致，原revision未绑定transaction和module；完整binary64序列化不是科研精度合适默认。

**Options**：继续json.dumps；完整JCS binary64；RH-C14N-1严格JCS值子集+typed数字字符串。

**Decision**：RH-C14N-1，UTF-16 key排序、UTF-8、无normalization、拒绝duplicate keys/非法Unicode；原生数字只safe integer，raw numeric float/exponent/-0拒绝。revision绑定全部语义identity/module/actor/parents/time；transport/envelope不入hash。见SYNC_WIRE_FORMAT。

**Consequences**：Python/TS各自独立strict decoder/encoder与固定bytes/hash fixtures；不宣称支持所有JCS binary64。必须在decode阶段保留并检查numeric lexeme，否则JSON.parse会掩盖1.00精度。未知字段/版本隔离或拒绝。质量审查发现语言递归栈不同，明确统一root depth0、值嵌套最多64，新增64有效/65与600拒绝固定边界；不截断内容。

**Open Questions**：未来其他语言codec，协议版本演进与更大资源配额；真实签名/密钥互通另做安全Sprint。

## ADR-012 — Scientific Numeric Representation（Sprint 1）

**Context**：数值相等和wire identity不同，尾零/指数可能表达用户精度，不可隐式float或舍弃。

**Options**：binary64；normalize decimal并丢原表达；preserved tagged decimal/integer strings且另提供exact scientific equality。

**Decision**：保留raw字符串。1/1.0/1.00/1e0作为decimal可数值相等，但不同bytes/revision；1.60/1.600也不同。exact coefficient/exponent比较不改变原wire，不触发科研自动merge。

**Consequences**：hash保留精度与格式，单位/来源仍需独立语义验证；native unsafe整数拒绝，用tagged integer。QA映射旧Domain时须采用可保真JSON载体或拒绝输入，不偷偷float-roundtrip；生产数值migration未实施。

**Open Questions**：若未来需要测量有效数字/uncertainty的结构化模型，需新schema/ADR；不得复用数值相等规则默默消除科学分叉。

## ADR-013 — Whole-batch Promotion Barrier（Sprint 1）

**Context**：Sprint0只保证物理批次原子写入，尚未阻止一个科研成员冲突时其他成员继续显示accepted。迟到分叉还会破坏已批准Run的证据基础。

**Options**：逐字段保留accepted；按对象暂停；以SyncTransaction为科研可见性单位并递归暂停依赖。

**Decision**：采用整批屏障。任何成员出现多head/未批准依赖，整个transaction成为CANDIDATE；此前accepted批次迟到分叉时撤回其整批投影，并沿dependency graph暂停后续批次。独立批次继续。人工review必须覆盖被审批次全部成员，不能只批准pressure后隐式批准其他字段。

**Consequences**：增加membership/dependency索引和失效Audit。历史、候选和BASE保留；UI未来须表达待审，不能把transport ACK当科研批准。项目级行锁下检测、状态转换和投影撤回同事务。

**Implementation evidence**：真实 QA PostgreSQL 的整批撤回、递归暂停、独立批次、partial review 拒绝与 full review 通过；依赖覆盖 parent、显式 transaction、Run 与 Evidence/Artifact 引用，包括 Gate criteria 内 evidence_ids。

**Open Questions**：后续复杂科研关系自动推导、跨批次重新批准界面与批次大小；source_id/Tag/任意领域关系不冒充完整语义图。

## ADR-014 — Human Grant Boundary（Sprint 1）

**Context**：登录、设备身份和payload actor_type都不能证明某次科研确认来自人工，更不能让离线解决候选获得最终权限。

**Options**：相信payload；签名即Human；受信principal加短期、精确绑定的人工grant。

**Decision**：注册principal绑定user/device/session/project/actor；人工科研final操作另需fresh grant绑定transaction摘要、object、operation、exact expected_heads和expiry。离线final Human confirmation不支持。QA mock只模拟受信服务签发和消费，不称真实认证或密码学实现。

**Consequences**：AI/system不能final人工结论、确认参数、升级验证证据、通过Gate、接受Decision或确认模块升级。在线resolution必须锁内重读完整heads；离线resolution只保存proposal，可与另一proposal形成新冲突，不代表人工批准。

**Implementation evidence**：QA 注册与 mock grant 已运行验证；重放必须保持 principal active，grant 最长五分钟且单次消费。权限同时核验 patch、继承 document 与当前 heads；AI 不能借旧 draft BASE 撤回当前 final。沿用现有 service.scientific_authority，不把 mock 视为真实 user-presence。

**Open Questions**：生产签发、撤销、设备签名、跨设备consent UX和重认证；全部留待后续人工批准的安全开发。

## ADR-015 — Accepted Projection vs Immutable History（Sprint 1）

**Context**：新head或新receipt不一定可成为科研当前值。若直接把最新history写成Domain值，将掩盖冲突和迟到失效。

**Options**：单表last-write-wins；删除冲突历史；不可变history和独立accepted projection。

**Decision**：第三种。revision/Audit只追加；accepted projection仅来自已通过整批屏障的transaction。candidate仍可查询BASE、N heads及原批次。received_cursor与accepted watermark分开，conflict/quarantine/暂停依赖时fully_synced=false。

**Consequences**：更多状态与查询，但能保留可审核科研来源。失效只撤回投影，不删除revision或改旧Audit；需要显式resolution Audit和整批重审。QA表独立于生产Domain，真实生产查询hook未开启。

**Implementation evidence**：数据库 append-only trigger、复合父引用 FK/声明 trigger 已实测；immutable Outbox.action_digest 绑定本地来源命令，拒绝同 ID 改动作。received cursor 与当前事务状态分离，已完整审查的旧批次 SUPERSEDED 可通过判定水位，旧派生依赖不会自动追认。

**Open Questions**：快照压缩、历史保留与生产projection迁移；Sprint1不部署这些机制。

## ADR-016 — Production Crypto Suite（Sprint 2选型，Secure QA实现范围）

**Context**：两语言互操作须采用维护的标准实现，不能自行编写曲线/KDF/AEAD。
**Options**：原生cryptography+WebCrypto/hpke-js；PyHPKE；libsodium匿名sealed-box。
**Decision**：cryptography50.0.2 / NodeWebCrypto / @hpke/core精确1.9.0，AES256GCM正文、Ed25519签名、RFC9180 Base X25519/HKDFSHA256/AES256GCM wrap；Base来源另由trusted authority签名绑定。Artifact DEK使用AESKW。来源与历史公告见CRYPTO_LIBRARY_REVIEW。
**Consequences**：两端独立vectors/wrap/unwrap，lockfile审查；不宣称整体外部审计或生产部署。旧core并发nonce公告要求patched version且fresh one-shot context。
**Open Questions**：实体browser支持、hardware-backed keys与真实endpoint安全留待另审。

## ADR-017 — Secure Envelope

**Context**：Relay不能读研究payload或替换metadata，transport rewrap不可改变revision identity。
**Decision**：严格版本/字段的完整envelope，canonical header作为AEAD AAD，去signature的整个envelope作为domain-separated Ed签名preimage。ciphertext digest、project/device/epochs/message/dependencies/nonce/checkpoint全部绑定；解密后canonical与semantic digest/identity再验证。
**Consequences**：metadata关联/size/time仍泄漏；新wrapper ID/nonce不变更semantictransaction。unknown/malformed/downgrade fail closed，无plaintext fallback。
**Open Questions**：未来协议演进须新version，而非放宽v1。

## ADR-018 — Nonce Uniqueness Strategy

**Context**：共享project key、多设备并发/重启不能重复AESGCM nonce。
**Decision**：authority签名不复用uint32 prefix + uint64 counter（wire上限safeint）；SQLite BEGIN IMMEDIATE/FULL与独立fsync witness，reserve→witness fsync→commit→encrypt。首次explicit newkey注册，全部状态不一致fail closed并要求rotate。
**Consequences**：crash可以产生gap或停止旧key写入；Python/Node共享ledger实际并行测试，合法retry缓存原envelope。支持正常crash/单ledger回滚检测，不支持恶意同时回滚全部trusted材料；备份恢复须rotate。
**Open Questions**：生产安全vault/monotonic hardware尚未实现。

## ADR-019 — Membership Epoch

**Context**：签名本身不证明当前权限；候选manifest不能自授权。
**Decision**：本地pin完整manifest/root/history；transition由previous ACTIVE owner验证，previousdigest CAS，membershipepoch精确+1；公钥不悄悄替换，revoked/prefix历史不可删除，同epoch异digest报fork。
**Consequences**：PENDING无keys、reader无mutation、writer无membership变更；Relay publicregistry不能赋予Human权限。新push只current，已stored旧epoch transport quarantine且不入Kernel。
**Open Questions**：完整key transparency/gossip为NOT IMPLEMENTED。

## ADR-020 — Key Epoch Rotation

**Context**：撤销后的futureciphertext不得被持有旧key的设备读取。
**Decision**：revocation/recovery同时membership+1/key+1，fresh随机projectkey只HPKE wrap给仍ACTIVE收件人，authority签名绑定recipient/context/wrappedbytes。
**Consequences**：旧设备过去明文/旧key不能回收；created_at不恢复权限，合法re-encryption新nonce但原semanticidentity。
**Open Questions**：保留旧keys的用户政策与完整长期存储预算待审。

## ADR-021 — Trusted Pairing

**Context**：登录不能自动得到E2E projectkey，新root不能从hostile Relay取得。
**Decision**：5分钟单次challenge绑定session/project/recipient两公钥/fingerprint/SAS/role，recipient possession proof与明确人工scope确认；trustedclient同事务消费challenge/保存transition/grant，exactretry返originalreceipt、changedretry拒绝，撤销后不再返receipt。
**Consequences**：QA文本QR/SAS是真签名密钥协议测试，不冒充实体相机或真实user-presence；科研审批grant仍是Sprint1mock。
**Open Questions**：跨设备实际UX留待Sprint3人工批准。

## ADR-022 — Relay Durability

**Context**：HTTP200不等于科研accepted，ACK前crash不能遗留半消息。
**Decision**：独立QA PG原子保存完整密文/metadata/seq/receipt，synccommit后RelayStored ACK。同ID同bytes返原receipt、异bytes拒绝；client outerreceipt/cursor/chain和Kernel apply_in_session同事务，innerseq自动分配。
**Consequences**：RelayStored/DeviceReceived/Decrypted/KernelApplied/ScientificAccepted/ArtifactPrimaryDurable分开；retain_until_ack仅metadata，无GC；实际HTTPS/socket/process/PGrestart故障测试才算network evidence。
**Open Questions**：跨故障域备份/productionops未验收。

## ADR-023 — Checkpoint and Rollback

**Context**：有合法签名的旧数据仍可能是Relay回滚。
**Decision**：client持久cursor/chain与trusteddevice签名checkpoint；oldercursor、samecursor异chain、缺页/伪造签名拒绝。manifest/snapshot含project/cursor/modulehash/keyepoch/statedigest/creator并签名加密。
**Consequences**：检测明显回滚，不靠wallclock；新device依赖trustedpair提供anchor，单设备无法证明未锚定消息未隐藏。split-view/gossip/transparency NOT IMPLEMENTED；无fullbootstrap。
**Open Questions**：长期透明日志设计另审。

## ADR-024 — Recovery Model

**Context**：passwordreset不能重建E2E钥匙，recoverysecret不能证明最新state。
**Decision**：高熵kit私钥+bootstrap pre-pinned recovery authority+持久最新manifest/checkpointanchor；验证连续链再授权newdevice/rotate。仅operation=recovery允许由已锚定recovery signing key替代旧ACTIVE owner，parent/CAS和两epoch精确+1，显式新recipient为owner/ACTIVE、全部旧成员REVOKED并保留prefix历史，候选manifest/Relay不得新增root。可信anchor缺失 RECOVERY_FRESHNESS_UNVERIFIABLE；全部keys丢失 E2E_DATA_UNRECOVERABLE，无servermaster。
**Consequences**：需保持kit可信状态新鲜，旧kit/全部trustedstate同时回滚有明确局限；已知明文不可遗忘。
**Open Questions**：真实用户kit备份/恢复UX尚未实施。

## ADR-025 — Artifact Crypto Frame

**Context**：文件内容和filename不应泄漏到Relay，未来10GB不能全读进RAM。
**Decision**：每artifact独立DEK、≤64KiB AESGCM chunks与context/index/count/size AAD；DEK由AESKW wrap位于签名加密manifest，filename/category/run/title、总size/hash在manifest内。
**Consequences**：bounded iterable/sink prototype验证错序/缺块/重复/tag/hash/size/epoch/retry；无生产MinIO/OPFS/10GB实测，不把明文checksum去重称无关联泄漏。
**Open Questions**：大文件cache/primarydurability集成留待另审。

## ADR-026 — QA Relay Ingress and Request Replay Boundary

**Context / old decision**：ADR-019/021/022/023规定当前授权、trusted pairing、durable ACK和checkpoint，但一般signed-request描述未精确限定GET proof重放与receipt权限；internal-only发布端口在当前Docker Desktop实际不可达。

**New evidence**：2026-10-08合成TCP探针host连接失败并已清理；独立网络设计PASS附作用域/实际拓扑/TLS/入口资源验收条件。独立HTTP设计补审发现4项P1、2项P2，尚未执行网络验收。

**Decision (AMENDS, does not supersede scientific semantics)**：采用固定目标窄TCP入口，Relay只接internal data网；PG/入口只接两专用QA网，唯一Relay入口127.0.0.1:38001，TLS client直达Relay。精确request proof绑定audience/method/path/query/bodydigest/project/device/currentmanifest/双epoch/requestUUID/issued_at；60秒过去及5秒未来窗口。GET原响应持久不可变，当前授权优先于任何receipt lookup；网络proof UUID与业务message/session identity分离。bootstrap本地可信pin、recovery独立profile、pairing possession仍trustedclient事务，不让Relay自授authority。详细exact schema、endpoint权限、资源字节/rate/cache预算与错误契约以SPRINT_2_SECURITY_DELTA的HTTP冻结补充为准。

**Consequences**：捕获请求不能不断查询未来tail或以旧receipt绕过撤销；长时retry重签网络proof但复用原sealed bytes。新增TCP入口和request cache均须fault/privacy/限额测试，实际属性guard不能只验label。此ADR不授权公网、真实科研同步、生产migration或Sprint3，DESIGNED ONLY直到Task3真实验收。

**Open Questions**：生产origin/audience、时钟运维、真实presence/配对UX及跨设备透明日志仍需后续专门审查。
