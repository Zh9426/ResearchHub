# Research Hub v0.3 Sprint 1 — Sync Protocol Kernel

日期：2026-10-07。开发分支：`codex/researchhub-v0.3`。RH-010 冻结 wire；RH-011 交付 QA Kernel、真实数据库验收、基准与本报告。稳定 main 和 v0.2.0 指向 `4a4db4a4bd54a598f640d7de99281c15bd46e3b9`，生产入口与 migration 未改。

本轮交付的是独立 QA Kernel，不代表多端同步已实现。所有 PostgreSQL 验证使用独立 loopback 容器、专用库/角色和合成科研数据；个人原生部署未接入此 Kernel。

## 六项 Gate 结果

| Gate | 结果 | 证据 |
| --- | --- | --- |
| 1 Canonical Identity | PASS | 两端独立实现；26 canonical、59 protocol、3 depth 固定向量及 10 场景/20 step 共用 bytes/hash/error |
| 2 Transaction Atomicity | PASS | 实际 Domain service 的 Run+6 Parameter+3 Metric+2 metadata、12 Domain Audit、12 Kernel Audit、Inbox/Outbox/projection 同 Session；六处 crash 全回滚 |
| 3 Scientific Conflict Safety | PASS | BASE 1.400 与 1.600/1.800 全保留；N-head、共同祖先、revision 类型/精度校验，不选时间 winner |
| 4 Whole-batch Barrier | PASS | 一 Parameter 分叉撤回 12 成员批次；晚到冲突与递归依赖暂停；独立事务保留；partial review 拒绝，完整 review 新批次提升 |
| 5 Human/AI Authority | PASS | 注册 principal、五分钟内一次性精确 grant；拒绝自称 Human、final mutation、旧 draft 撤回 final 与越权 module 操作；沿用 v0.2 authority |
| 6 PostgreSQL Concurrency | PASS | 独立 backend PID、Barrier、可观察行锁、跨项目继续、unique/FK/trigger、在线解决一胜一拒、离线 RA/RB 保留新分叉 |

规格复审 PASS，质量复审 APPROVED。审查发现的 Domain 命令重放、物化类型和内嵌 Evidence 依赖问题均先建立失败用例，再修复并独立复验。

## 1. Canonical wire format

**IMPLEMENTED IN KERNEL**：RH-C14N-1 UTF-8、UTF-16 key 顺序、无 Unicode normalization、严格 duplicate key/非法 Unicode/数字 lexeme 拒绝，嵌套最大 64。字段精确白名单；change/transaction 绑定项目、对象、actor、module、parents、schema 与完整语义。transport envelope 不进入业务 identity。[规范](SYNC_WIRE_FORMAT.md) 是唯一字段定义，不将 Sprint 0 示例继续视为 v1。

## 2. Numeric representation

**IMPLEMENTED IN KERNEL / TESTED ON QA POSTGRESQL**：native 仅 safe integer；精确数字为 tagged decimal/integer 字符串。`1.600` 保留尾零，exact scientific equality 不改变 wire identity、不自动合并。Parameter QA 映射使用原有 object JSON 载体，Metric 使用原始字符串；无 float roundtrip。物化后再次校验 inherited value_type 与 value，非法单父/多父 patch 均拒绝。生产数值 schema/UI 迁移 **NOT IMPLEMENTED**。

## 3. Cross-language revision

Python 与 TypeScript 独立 codec/revision/digest；固定预期 bytes 来自人工字段顺序与独立 SHA 锚点，作者工具不调用被测 codec。7 项 TS、17 项 Python vector tests 均通过。共享 10 个 Kernel 场景的 wire 层两端一致，额外 PG transcript 验证实际状态；TS 数据库引擎 **NOT IMPLEMENTED**，不将 wire 测试称浏览器同步。

## 4. Revision DAG

**IMPLEMENTED IN KERNEL / TESTED ON QA POSTGRESQL**：不可变 revision、parent declaration、复合 scope FK、heads 索引、共同祖先/N-head。已存在父必须同 project/object/type；缺失 BASE 不伪造。不可变声明 trigger 拒绝自环与后加父边，应用按拓扑插入；Run lineage 循环拒绝。历史查询保留 semantic、materialized document 和来源。

## 5. SyncTransaction

**IMPLEMENTED IN KERNEL**：单项目 ordered changes、idempotency/digest/COMMIT、成员与依赖；一个科研操作为一个批次。调用方数据在 apply 前 deepcopy，避免校验后变更身份。same ID/same content 安全重放；same ID/different content 拒绝。Domain 原始操作另以 immutable action_digest 绑定，覆盖 Run/Parameters/Metrics/Artifacts。

## 6. Whole-batch barrier

**TESTED ON QA POSTGRESQL**：任一成员冲突或未批准依赖，使整批 CANDIDATE、全部科学 projection 不可见。真实 12 成员 Domain batch 单参数碰撞可撤回整批；只解决 pressure 不会暗中批准其他成员。完整人工 review 为所有受影响成员创建新 revision，来源候选变为 SUPERSEDED。

## 7. Late conflict invalidation

**TESTED ON QA POSTGRESQL**：先接受 A，后到同 BASE 的 B 会撤回 A 全批与递归后续 projection，追加 invalidate Audit；原 revision/Audit/来源 Domain 行保持。重放 A 返回当前 CANDIDATE 与原 receipt_state，不继续显示旧 accepted。水位可退回，fully_synced=false。

## 8. Transaction dependencies

**IMPLEMENTED IN KERNEL**：显式 transaction、parent revision、Run 所属/lineage、Evidence/Artifact 关系推导；Gate criteria 内 evidence_ids 同样验证 endpoint、同项目与依赖。后到 Evidence 分叉暂停原 passed Gate。独立事务保持 accepted；解决原冲突不自动追认旧派生结果。任意 source_id、Tag 或跨领域完整关系图 **NOT IMPLEMENTED**。

## 9. Accepted projection

**IMPLEMENTED IN KERNEL / TESTED ON QA POSTGRESQL**：history 与 accepted 科研视图分开；冲突视图显示 BASE/N candidates/lifecycle。原 v0.2 行是本地来源历史，不是同步 winner。生产 API/UI 查询 hook **NOT IMPLEMENTED**，因此不能把 QA 视图安全性扩展宣称到已部署产品。

## 10. Conflict resolution

**TESTED ON QA POSTGRESQL**：在线 lock 内核验完整当前 heads，fresh grant 绑定同 transaction/object/operation；heads 变化拒绝并 rollback，grant 未消费。两在线解决一项接受、一项 CONFLICT_CHANGED。两个离线 proposal 形成 RA/RB 新分叉且都 candidate，之后 full review 可接受。文本三方建议与 Tag OR-set **NOT IMPLEMENTED**，保守保留分叉。

## 11. Outbox

**TESTED ON QA POSTGRESQL**：Domain+Audit+immutable Outbox 同 Session，LOCAL_COMMITTED 含完整 envelope 和 action_digest；重复动作不产生新行，改动作拒绝。网络 PUSHING/ACK/re-encryption 为 **DESIGNED ONLY**。重加密测试仅变更 mock nonce/key_epoch，验证业务 digest 不变，不是 E2E。

## 12. Inbox

**TESTED ON QA POSTGRESQL**：项目连续 sequence、immutable receipt，只有整个事务提交才推进 received_cursor。QUARANTINED 保存 raw 且阻止 accepted 水位；重复不额外推进。accepted_watermark 是连续已完成判定（ACCEPTED/SUPERSEDED）水位；CANDIDATE/QUARANTINED 和未决依赖阻止 fully_synced。真实 Relay cursor **NOT IMPLEMENTED**。

## 13. Human/AI authority

**IMPLEMENTED IN KERNEL / TESTED ON QA POSTGRESQL**：可信注册 principal 身份绑定，不相信 wire actor_type；active 检查含 duplicate replay。沿用 service.scientific_authority，加 full document/parent/current protected heads 检查。AI/Codex/ChatGPT/system 不可 final、confirmed、validated/reproduced、Gate passed、Decision accepted、Claim supported 或 module mutation。fresh mock grant 单次、最长五分钟，绑定 user/device/session/project/object/operation/heads/transaction digest；离线 final 禁止。真实 user-presence、设备签名、OAuth/撤销传播 **NOT IMPLEMENTED**。

## 14. Lifecycle

**TESTED ON QA POSTGRESQL**：archive/trash/restore 显式操作；trash vs 旧 edit 保留候选且不复活，关闭 Run 的新科研子记录暂停。restore 需 fresh Human；普通 purge 拒绝。永久 purge、设备 ACK、保留期回收 **DESIGNED ONLY**，未删除个人文件或历史。

## 15. Artifact metadata

**IMPLEMENTED IN KERNEL / TESTED ON QA POSTGRESQL**：四政策元数据枚举，pending 不宣称文件已到达；相同 bytes 的不同 metadata UUID 均保留。合成 verified reference 按 project/key_epoch/checksum/size 验证，跨 context/错误 checksum 不 ready。MinIO bytes 同步、AEAD、OPFS、GC **NOT IMPLEMENTED**；v0.2 MinIO 回归仅验证现有文件系统。

## 16. Audit

**TESTED ON QA POSTGRESQL**：相同 audit ID/内容安全去重，异内容整批拒绝；revision/Audit/Inbox/Outbox/member/dependency UPDATE/DELETE 由数据库 trigger 拒绝。QA Domain Audit 同样 append-only。resolve/invalidate 新追加、不改过去。生产 Audit migration **NOT IMPLEMENTED**。

## 17. PostgreSQL concurrency

专用 `researchhub-sync-s1-pg`，PostgreSQL 17.11 Docker、127.0.0.1:35433，DB/role 强校验。每项目 row lock，Kernel Project → v0.2 Project → Run/Resource 同一锁顺序；没有 Python global mutex。7 项并发方法覆盖重复、不同对象、same BASE、在线/离线解决、后到分叉与依赖 apply 竞赛、可观察等待与独立项目继续。数据库 unique/FK/trigger 另有实际负向。多进程/多主部署压力 **NOT IMPLEMENTED**。

## 18. Crash injection

六点事务内异常：revision/conflict/projection/audit 后、Inbox/cursor 前。Domain 与 incoming 两路径 rollback/retry 均通过，游标不提前，Audit 不重复。Hypothesis 是实际框架：三个编码属性共 300 passing；五个 PostgreSQL 属性共 53 passing（20 retry、20 same BASE、6 permutations、3 head sets、4 lineage depths），0 failing；无自造 random harness。断电、磁盘故障、跨节点 durability **NOT IMPLEMENTED**。

## 19. Existing v0.2 regression tests

本轮实际运行：后端/MCP/Release **137 passed**；前端 **46 passed**、typecheck 通过；真实独立 v0.2 Compose **23 passed**（21 online/MCP/权限并发 +1 写入暂停后的 PG/MinIO 备份恢复 +1 QA 四服务重启后记录/文件/Audit 持久性）。API 与 Web Docker 生产构建通过，QA API/Web 可启动。

原生 Next build **BLOCKED**：正在运行的个人 Node server 锁定 `.next/standalone` 目录，触发 EBUSY。保留原服务，以隔离 Docker Web build 完成生产构建验证；未将此写成原生 build 成功。实体设备、生产迁移与新 UI 不在本轮 scope，未运行。

Sprint 1 最终 Python **149 passed / 0 skipped**（17 vectors、7 pure kernel/boundary、125 actual PG），TypeScript **7 passed / 0 skipped**、strict typecheck 与新增范围 Ruff 通过。CI 新增专用 PG job，推送后结果在交付消息核对；未预先声称远端通过。

## 20. Performance observations

修复后的 Kernel 经实际 apply 创建 1000 Parameter、10000 immutable revisions（100 个批次，每批 100），再形成 100 open conflicts，追加 100 independent Notes；最终 10200 revisions/1100 objects。Docker loopback、本机 Windows/Python3.12/Node24，一次 synthetic workload；原始结果保留在被忽略 storage/runtime/sync-s1-benchmark.json。

| 测量 | 结果 | 样本与范围 |
| --- | --- | --- |
| 10000 revision 装载 | 139.277 s | 全路径 100 次事务 |
| 100-change 常规 apply | mean 1373.367 ms / p95 1545.244 ms | 100 批 |
| heads lookup | mean 0.782 ms / p95 1.009 ms | 1000 次索引查询 |
| 100-conflict batch apply | 4474.197 ms | 一批；含 DAG/common-base/屏障/Audit/DB，不是单独算法时间 |
| 100-change independent apply | 1172.904 ms | 一批 |
| 100-change digest | mean 11.380 ms / p95 12.132 ms | 100 次 |

heads 使用 scope 索引；祖先遍历限相关 DAG，依赖通过索引递归。实测没有全库逐对象两两比较路径，但一轮 workload 不能证明所有规模无二次复杂度；深 DAG、多头与全项目 watermark 查询仍有成本。每 change flush/SQL 往返可优化，暂未以批量写绕开原子/审计验证。没有用 10k bulk 插入替代真实 apply。

## 21. Remaining risks

生产 accepted query hook、实际 user-presence 与安全密钥层尚缺；QA gate PASS 不意味着网络同步安全可部署。未知版本只做原消息隔离，没有迁移/重新解释器。Source/Tag 等关系不完整，需新 schema 与 review。PostgreSQL 历史无限增长，快照、压缩、GC 未实现；project serialization 与多 SQL roundtrip 在较大 workload 下可能成为瓶颈。合成 Artifact registry 不能代替 bytes durability。

## 22. Open questions

人工需审查 granularity（完整批次重新批准 UX）、旧依赖 rebase 操作、生产数值载体和 accepted 查询迁移；真实 consent/设备身份与恢复、跨设备 schema 升级、key epoch 生命周期仍需独立决策。QA schema review/备份/撤回说明见 [事务模型](SYNC_TRANSACTION_MODEL.md)：仅独立 metadata 初始化，生产 Alembic 0001–0005 未变，未部署 production sync schema。

## 23. Proposed Sprint 2 scope

**DESIGNED ONLY**：在人工批准后先进行 Secure Relay 的 threat model、签名/AEAD/key lifecycle 方案与独立验证计划，再选择最小传输实现。不要直接上线此明文 QA Kernel；生产 DB migration、浏览器/PWA 与 ChatGPT bridge 各自另设验收。当前 **STOP**，不进入 Sprint 2。

## CASE A–Z 对照

| CASE | 证据文件/方法范围 | 结果 |
| --- | --- | --- |
| A/B/C/D | sync_vectors/test_wire.py + TS wire.test.ts：bytes/revision/decimal/Unicode | PASS |
| E/F | test_kernel.py duplicate/collision；test_domain_outbox.py changed_action | PASS |
| G/H | test_domain_outbox.py 12-member real Domain、single Parameter collision | PASS |
| I/J/K | test_scientific.py late divergence/dependency/independent；test_materialized.py nested Gate | PASS |
| L | test_concurrency.py online/offline resolutions；test_scientific.py N-head review | PASS |
| M/N | test_authority.py spoof/final/protected；test_materialized.py old draft | PASS |
| O | test_integrity.py module mismatch raw quarantine | PASS |
| P | test_scientific.py trash/old edit/explicit restore/closed Run | PASS |
| Q/R | test_integrity.py append_audit duplicate/collision + SQL immutable | PASS |
| S/T | test_kernel.py + test_domain_outbox.py 六 crash points；PG Hypothesis retry | PASS |
| U | test_concurrency.py 7 方法与真实 pg_stat_activity Lock | PASS |
| V/W | test_integrity.py parent/lineage cycles + cross-scope；PG generated chains | PASS |
| X/Y | test_integrity.py separate metadata/context/checksum/not-ready | PASS |
| Z | test_integrity.py schema/protocol quarantine、cursor/watermark | PASS |

**PROTOTYPED** 专指 Sprint 0 SQLite/合成 Relay 历史，不作为本次 PG gate 证据。上述 IMPLEMENTED/TESTED 范围均仅 QA Kernel；网络、配对、撤销、E2E、移动存储、bootstrap/retention 与云服务均 **NOT IMPLEMENTED** 或 **DESIGNED ONLY**。
