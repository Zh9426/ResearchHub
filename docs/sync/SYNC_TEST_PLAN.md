# Sync Kernel 与 Secure Transport 验收

## Sprint2 当前验收状态

Task1/2已完成本地标准密码和生命周期独立复审。root/spec/quality各自准确排除TLS材料的合并回归218通过，Node38/typecheck通过；详见[Task2 QA](SPRINT_2_TASK2_QA.md)。本地库测试不抵充真实网络/PG/客户端原子集成，最终独立安全审查之后仍须完整重跑。

八Gate的正式结果以[SPRINT_2_REPORT.md](SPRINT_2_REPORT.md)为准，目前全部PENDING：Crypto Interoperability、Relay Confidentiality、Envelope Integrity、Replay & Epoch Safety、Device Lifecycle、Network Durability、Nonce Safety、Rollback Detection。任一FAIL即overall FAIL，PENDING不可宣布complete。

Task3必须实际HTTPS/CA+hostname验证，专用Relay PG和固定TCP入口，真实socket断连、commit前/后kill、ACKloss、Relay/PG/入口/client重启及持久性；直接PGdump、所有Relay/入口files/logs与运行时钥匙/研究canaries多编码0命中。客户端整页验证、outer cursor/checkpoint与Kernel同事务，以及有效设备签名不能伪造Human grant，均需实际QA PG证据。TestClient/Mock/静态导入/材料生成不算网络验收。

成熟Hypothesis覆盖crypto roundtrip/mutations、nonce schedules、grant/epoch/chunk permutations；Task3另有实际HTTP retry/idempotency/invalid-page/chunk schedules及oversize/rate/配对滥用测试。完整CLI按Relay/client两cohort串行运行，各自在结束时完成独立privacy v2扫描；selected/executed/文件集与JUnit、trial/invocation必须一致且没有skip/deselection。Case A–Z、实际命令和缺口逐项映射见Sprint2报告，禁止用局部计数替代整个Gate。

## Sprint1 已冻结验收

当前验收使用专用 PostgreSQL 17.11：`researchhub_sync_kernel_qa` / `researchhub_sync_qa` / loopback 35433。`HUB_SYNC_QA=1` 显式 opt-in，缺配置失败，不回退个人 DATABASE_URL。完整执行结果与 CASE A–Z 对应关系见 [SPRINT_1_REPORT.md](SPRINT_1_REPORT.md)。

## 六项验收门槛

| Gate | 必须满足的真实证据 |
| --- | --- |
| Canonical Identity | 两端独立编解码同一固定 bytes/revision/digest 与错误样例；不互相调用生成 oracle |
| Transaction Atomicity | 真实 v0.2 Domain service 同 Session 创建 12 个对象、Audit 与 Outbox；六故障点全部 rollback，retry 一次提交 |
| Scientific Conflict Safety | pressure BASE 1.400，1.600/1.800 候选与共同祖先全保留，无时间或 Primary winner |
| Whole-batch Barrier | 单成员分叉撤回整批及递归依赖；独立批次保留；完整 review 才可提升 |
| Authority | 注册 principal 与一次性短期精确 grant；拒绝 AI 冒充和修改当前/历史 final，重放须 active principal |
| PostgreSQL Concurrency | 两连接 Barrier、项目行锁等待可观察、不同项目继续、唯一约束、在线/离线 resolution race |

## 执行命令与测试层

```powershell
.\.venv\Scripts\python.exe scripts/sync-qa.py --init
$env:HUB_SYNC_QA='1'
.\.venv\Scripts\python.exe -m pytest tests/sync_vectors tests/sync_kernel tests/sync_pg -q --hypothesis-show-statistics
E:\node\npm.ps1 --prefix packages/sync-protocol test
E:\node\npm.ps1 --prefix packages/sync-protocol run typecheck
.\.venv\Scripts\python.exe scripts/sync-benchmark.py --run
```

`sync_vectors`：26 canonical、59 protocol、3 depth 固定向量，另有 10 kernel 场景共 20 step，Python/TS 共用输入与预期 bytes/hash/error。固定样例作者不调用被测 codec。

`sync_kernel`：Hypothesis 三项 canonical 属性，每项 max_examples=100；QA 入口负向测试禁止 SQLite、远端和个人数据库。

`sync_pg`：真实 DB 行锁/trigger/FK/rollback，Hypothesis 五项属性（每项最多 20，有限 permutations/head-count/chain-depth 自动穷尽）。每个生成案例独立合成项目；无自造 random harness。六故障点为 after_revision_insert、after_conflict_create、after_domain_projection、after_audit_append、before_inbox_commit、before_cursor_advance。

必须区别：TS 验证共享 wire 层，不是 TS PostgreSQL 引擎；fault 为事务内异常，未证明断电 durability；QA Artifact receipt 用合成 bytes，不是 AEAD/MinIO 同步。当前 CI 单独启动 PostgreSQL service 并启用 QA，不接受全部 PG skip 当通过。

最终审查补充负向：调用方 mutable payload 快照、复用 transaction_id 改 Domain 命令、继承类型后的非法科学 document、Gate 内嵌 evidence_ids 的跨项目/缺失/晚到冲突、旧 draft BASE 不得撤回当前 Human final。

## Sprint 0 历史验收边界

状态：**DECIDED** 是规范；**PROTOTYPED** 是合成测试覆盖，不是生产验收。实际计数与命令见 [SPRINT_0_REPORT.md](SPRINT_0_REPORT.md)。

## Formal invariants

定义 E 为已通过身份/业务验证的 accepted 变化，T 为 committed 批次，Apply(D,t) 为设备 D 原子处理 t，Heads(o) 为对象 o 未被后继消费的 revision 集合。ACK 分 transport 与 domain，不含静默内容删除许可。

| 编号 | 不变量 | 检验方式/本轮边界 |
| --- | --- | --- |
| I01 | accepted(c) ⇒ 保留 c 的可恢复 revision/Audit 或经明确批准、可追踪的压缩快照；不得静默丢失 | 批次/恢复原型；跨故障域 durability 尚未证明 |
| I02 | Apply(Apply(D,t),t) = Apply(D,t)，对象、审计、游标相同 | duplicate pull/push 原型 |
| I03 | 同 BASE 的不同科学更新 ⇒ 所有非因果 heads 保留，不能自动单值覆盖 | pressure 1.6/1.8 与人工结论原型 |
| I04 | Audit ID 的内容不可更新/删除；相同 ID 异内容必须拒绝 | Sprint 0 当时只测原型；Sprint 1 已验证真实 QA append-only trigger |
| I05 | verified(bytes) ⇒ sha256/size/manifest 均符合；失败不能 success | Sprint2本地双端AEAD/签名manifest/chunk负例及小Artifact实际HTTPS传输验证；生产MinIO同步未实现 |
| I06 | trash/edit 不自动 restore；purge 不通过普通 ChangeSet | 原型 lifecycle 负向测试；生产 purge 未实现 |
| I07 | project.module_snapshot 不随本地 registry 改变；解释绑定 hash | 设计及将来 module fixture，原型不证明真实模块 UI |
| I08 | Human-only accepted mutation ⇒ 可信 Human grant 绑定该 heads/operation | Sprint1实际QA PG synthetic principal/mock fresh grant通过；真实用户consent未实现，外层Device签名不能替代 |
| I09 | Cloud/AI entry 的有效权限 ≤ 原 Domain AI scope；不得冒充 Human | 设计 + synthetic principal，真实 Remote MCP 未实现 |
| I10 | outcome 不依赖 Primary role 或 wall-clock 选胜者 | head-set 推导/双副本并发测试；没有生产 Primary 服务 |
| I11 | T 的所有 ChangeSet 可见性为全有/全无；无半个 Run/参数视图 | push-half/pull-crash 原型；业务 conflict 全批次待审查策略见实现说明 |
| I12 | cursor advance ⇒ inbox 与结果持久；业务路径包含 Audit，quarantine raw receipt 不解释业务 | Sprint 0 apply rollback 原型；Sprint 1 真实 PG 证据见上文 |
| I13 | 同 transaction/change ID 不同 digest ⇒ reject，不改变历史/seq | 碰撞负向测试 |
| I14 | object UUID、revision 和 parents 绑定同 project/type；跨项目依赖不可用 | 类型/项目负向用例或代码复审，未声称完整生产 referential integrity |
| I15 | bytes dedup 仅 project/key epoch 内；不同 metadata ID/来源均保留 | same SHA/context 测试 |
| I16 | unresolved heads > 1 ⇒ conflict；resolution 消费指定完整 heads，新的解决分叉仍保留 | concurrent resolution 原型 |
| I17 | bootstrap 不覆写未 ACK local changes；log compaction 有验证快照与 tail | 设计；bootstrap/compaction 未实现 |
| I18 | Relay 无 plaintext project key，错误 key/nonce/signature 不能入 Domain | Sprint2密码负例、真实Relay dump/bytea/files/log扫描与14泄漏对照、客户端Kernel认证路径；最终证据见Sprint2报告，不代表所有威胁均已解决 |

## 用户要求的十个核心案例

| CASE | 合成动作 | 必须观察的结果 |
| --- | --- | --- |
| 1 | A offline create Run，再 push，B pull | 同 UUID 的同业务 Run 出现 |
| 2 | A/B 各自离线新建不同 UUID Run | 两个都存活，合法分支不混成冲突 |
| 3 | 共同 pressure=1.4，A→1.6，B→1.8 | 两候选/head 保留，BASE 可查看，无 LWW |
| 4 | 同 transaction 重复 push | 原 receipt/seq，日志无新增 |
| 5 | 同页/批次重复 pull | 无多余对象、Audit 与 cursor 变化 |
| 6 | 多 ChangeSet push 一半故障，再 retry | 半批不可见，重试完整一次提交 |
| 7 | 同项目/epoch 相同 SHA 的两个 Artifact | metadata 分别保留，bytes 一份；其他 project/epoch 独立 |
| 8 | trash 与旧 BASE 离线 edit | 保留 edit candidate、不自动复活 |
| 9 | 同时编辑 Human Conclusion | 不自动文本合并/不选 latest |
| 10 | A/B 各自 Audit 后重复收发 | 两事件均存在、无重复 |

补充负向：identity collision、未知 schema/type、missing/wrong BASE、项目/设备越权、AI 人工字段、purge、checksum、客户端 apply 故障、并发解决、设备/队列重启持久性。测试命名映射实际测试文件，覆盖缺口须写报告；禁止用“18 不变量全部证明”代替逐项边界。

## 执行与 TDD

```powershell
.\.venv\Scripts\python.exe -m pytest tests/sync_prototype -q
.\.venv\Scripts\python.exe -m ruff check prototypes/sync_sprint0 tests/sync_prototype
.\.venv\Scripts\python.exe -m prototypes.sync_sprint0.demo
```

原型只用 tmp_path/TemporaryDirectory、合成标记和标准库 SQLite。先写失败用例、观察 RED 后实现，再运行全部 GREEN；具体失败/通过记录由本次实际工具结果写入报告。SQLite 原子性依据 [官方事务文档](https://www.sqlite.org/lang_transaction.html)，但进程故障注入不等于断电/磁盘故障/多节点耐久性验收。

Sprint 0 不重复将原型结果充当 PostgreSQL、MinIO、PWA、签名或真实账户测试。v0.2 真服务重新验收见 [RELEASE_V0.2.0.md](../RELEASE_V0.2.0.md)；本分支应以 git diff 确认 apps/infrastructure/migrations 不变。既有 GitHub CI 仍测稳定应用，未自动纳入原型测试，需单独报告本地原型命令。

Sprint0当时的STOP已结束；Sprint1经人工授权完成冻结验收，用户现已授权Sprint2继续实施。当前实现限于Secure QA；真实浏览器清理、长期离线/完整bootstrap、移动与生产接入不在本轮范围。只有Sprint2全部八Gate、最终独立安全审查和完整回归通过后才到新的STOP，等待人工审查，不自动开始Sprint3。当前结果以SPRINT_2_REPORT.md为准。
