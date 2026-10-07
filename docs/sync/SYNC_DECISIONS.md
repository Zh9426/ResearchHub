# Sprint 0 Architecture Decision Records

共同状态：**DECIDED = 本轮推荐、待人工批准**，不是生产已实现或用户已批准。原型只验证部分机制；未决项需要在进入正式实现前回答。

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
