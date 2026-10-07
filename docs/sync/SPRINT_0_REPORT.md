# Research Hub v0.3 Sync Architecture Sprint 0 Report

日期：2026-10-07（Asia/Shanghai）。迭代：**RH-009**。交付架构文档与合成一致性原型，完成后 **STOP，等待人工架构审查**。

状态语义：**DECIDED** = 本轮推荐、尚待人工批准；**PROTOTYPED** = 隔离合成机制已运行；**OPEN QUESTION** = 待决策/验证；**NOT IMPLEMENTED** = 未加入生产产品。四者不得互相替代。

## 1. v0.2.0 release 状态

**已完成发布**：[GitHub Release v0.2.0](https://github.com/Zh9426/ResearchHub/releases/tag/v0.2.0)，发布于 2026-10-07 14:45:46。稳定 main、v0.2 分支与标签目标均为 `4a4db4a4bd54a598f640d7de99281c15bd46e3b9`；annotated tag object 为 `14fb82e9846be65c98877ab16a1f59b3f9bbb0cc`。未移动标签。

本次重新运行后端/MCP127、Release检查10、前端46、真实服务23项，TypeScript/Ruff/生产构建/Docker/迁移通过；真实 Codex 七工具与审计/撤销通过。个人 PG/MinIO 先备份，保留40表、145条原记录。详情及验收边界见 [RELEASE_V0.2.0.md](../RELEASE_V0.2.0.md)，保留历史 V0.2_REPORT.md。

封版 SHA 三次 CI 全部 success：[v0.2 分支](https://github.com/Zh9426/ResearchHub/actions/runs/37583049258)、[main](https://github.com/Zh9426/ResearchHub/actions/runs/37583296317)、[tag](https://github.com/Zh9426/ResearchHub/actions/runs/37583302714)。仓库遵从用户明确公开决定，不自动改访问状态；个人原数据/凭据不入 Git。

## 2. v0.3 branch

**已创建**：`codex/researchhub-v0.3` 从 `v0.2.0` 创建。RH-009 仅修改 docs/sync、prototype、原型 tests、README、CHANGELOG 与执行计划；无生产 apps、migration、部署或真实数据修改。稳定 main/tag 不追加 v0.3 设计。提交与 GitHub 同步按本轮提交/远端核对结果登记。

## 3. Recommended sync architecture

**DECIDED**：Windows Full Node（PG/MinIO/Codex）+ 手机/平板 Local Store + 无内容 key 的 Encrypted Sync Relay。离线记录，metadata eager/binary lazy；拒绝 DB 文件/Git state 同步和科研 LWW。见 [架构](SYNC_ARCHITECTURE.md)。

## 4. Revision model

**DECIDED / PROTOTYPED**：比较 integer/Lamport/vector/HLC/serverseq 后推荐对象 immutable DAG 与内容摘要；UUID 离线创建，parents 判因果，seq 只作 cursor。多头保留 BASE/所有候选，不按 clock/Primary 选值。生产 JCS/签名互通 **NOT IMPLEMENTED**，原型 Python 排序 JSON 不是 RFC8785 实现。见 [数据模型](SYNC_DATA_MODEL.md)。

## 5. ChangeSet model

**DECIDED / 部分 PROTOTYPED**：业务 UUID/type/operation/base/payload/device/actor/schema/encryption，不传 row dump/secret。设计有 transaction_id/module_snapshot_hash；原型 transaction_id 只在 batch envelope、revision 未绑定它，真实模块/权限未实现。原型仅 ResearchRun、Parameter、Metric、Note、HumanConclusion、Artifact，不是全部生产 wire decoder。

## 6. Sync transaction model

**DECIDED / 部分 PROTOTYPED**：多对象动作一个批次，commit marker/digest/幂等 ID；SQLite revision/audit/blob/inbox/cursor 一次 commit/rollback。**跨对象科学冲突的整批业务批准屏障 NOT IMPLEMENTED**：原型同批其他无冲突对象可显示，正式设计必须整批 candidate，避免半个业务动作。helper 每次变更一个 outbox batch，多对象通过 Relay API 验证，未适配现有服务。

## 7. Push protocol

**DECIDED / 部分 PROTOTYPED**：相同 ID/content 返回 receipt，异内容拒绝；缺 base 阻塞重试；分叉存候选。生产密文签名/配额未实现。原型 ACK=transport-durable，不代表科学认可。见 [协议](SYNC_PROTOCOL.md)。

## 8. Pull protocol

**DECIDED / PROTOTYPED（SQLite）**：每项目有序完整批次、cursor、幂等 inbox、原子 apply；异常 rollback 重拉。缺 base/前缀原型 quarantine 且 cursor 不前进，比设计的独立 applied watermark 保守。无 HTTP、bootstrap/mobile store。

## 9. Conflict policy

**DECIDED / 部分 PROTOTYPED**：完整矩阵覆盖 Project/Run/Parameter/Metric/Artifact/Note/Task/Evidence/Claim/Decision/Gate/GateCriterion/Tag/Activity/Audit/module/lifecycle。科学值无 LWW，Human Conclusion 不 merge；exact heads resolution 可再分叉。三方文本/OR-set 与真实 Human confirmation 尚未实现。见 [冲突策略](SYNC_CONFLICT_POLICY.md)。

## 10. Artifact strategy

**DECIDED / 部分 PROTOTYPED**：local_only / metadata_only / encrypted_sync / on_demand；7.8 GB MAT 默认 PC bytes，其他端仅 metadata/availability。metadata 独立 ID，合成 bytes 同项目/epoch/SHA 去重校验；生产 keyed locator/AEAD chunks/retention/refcount 未实现。见 [文件政策](SYNC_ARTIFACT_POLICY.md)。

## 11. Device strategy

**DECIDED / 部分 PROTOTYPED**：持久 UUID，不用 hostname；项目选择/cursors/pending/cache state。原型 UUID/outbox/receipt/inbox/cursor 重启保留。trusted pairing、epoch、撤销、完整设备统计 UI 未实现。Primary 不提高冲突优先级。

## 12. Mobile local storage

**DECIDED / NOT IMPLEMENTED**：IndexedDB 元数据/队列同事务，OPFS 加密 cache，CacheStorage app shell，device-local filters。配额/驱逐/清除可丢未同步内容，persistent request 不保证批准，需停写/导出/恢复 UX 与实机验证。无需移植 PG 或手机打包部署。见 [设备模型](SYNC_DEVICE_MODEL.md)。

## 13. Encryption

**DECIDED / OPEN QUESTION / NOT IMPLEMENTED**：随机 master/project/artifact keys、设备封装/签名 keys、成熟 AEAD/HPKE/Ed25519、trusted QR pairing、epoch/revocation/recovery kit。库、nonce 崩溃策略、vault、人机 user-presence 与独立安全审核待确认；无真实加密部署。见 [安全模型](SYNC_SECURITY_MODEL.md)。

## 14. Relay responsibilities

**DECIDED / SQLite simulator PROTOTYPED**：密文暂存、opaque parents、receipt、项目 cursors、允许的密文 bytes。默认 retain_until_ack，7/30天受唯一副本/ACK条件限制，signed snapshot + tail 才压缩。真实 Relay/E2E/compaction/snapshot 未实现，durable ACK 故障域待定。

## 15. Primary PC responsibilities

**DECIDED**：完整对象/bytes、长期备份、Codex/研究执行、快照来源。继续 PG/MinIO，不改变冲突规则。未来 purge 需 Primary+Human+所有相关状态检查，30-day retention 不自动授权删除。v0.2 本机产品保留，本轮不写生产库。

## 16. ChatGPT access model

**DECIDED / OPEN QUESTION / NOT IMPLEMENTED**：推荐 A trusted client bridge，电脑在线且显式选择数据/权限。B 云可读投影、C 项目 AI key、D 本地模型已比较。A 保留 Relay 无 key，但交给 AI 的选定明文属于远端共享；bridge 离线不可读。Codex 本机 MCP 保持 Human/AI 权限。见 [ChatGPT 模型](SYNC_CHATGPT_MODEL.md)。

## 17. Prototype results

**PROTOTYPED**：质量修复后本机重新运行 `python -m pytest tests/sync_prototype -q -p no:cacheprovider`：**34 passed in 2.21s**；Ruff All checks passed；demo 退出0，replicas_agree=true、BASE pressure=1.4、候选1.6/1.8、Audit=4。全部 tmp_path/TemporaryDirectory 合成数据；无应用 imports、个人服务/凭据或网络监听。

TDD 实际 RED26 failed → GREEN26；额外类型/引用及 caller payload 快照断言 RED3 failed/29 passed → GREEN32。质量审查发现actor与注册principal不一致可能使已ACK记录无法重放，新增回归 RED2 failed/32 passed，提交前一致性拒绝后 GREEN34。规格审查PASS，质量复审独立合成复现确认修复后PASS，无剩余阻塞。sandbox临时目录权限错误不计RED。CASE1–10全覆盖，补碰撞/cursor rollback/checksum/schema/type/purge/AI actor伪造/并发resolution/依赖乱序/重启/context dedup/严格JSON。命令范围见 [测试计划](SYNC_TEST_PLAN.md) 与 [原型 README](../../prototypes/sync_sprint0/README.md)。

原型只注入 Python 事务异常，不证明断电/磁盘/多进程/跨节点容错；不证明整批科学批准屏障、真实 Human 权限、模块、E2E 或生产 migration。全部设计不变量没有被 synthetic tests 全部证明。

## 18. Failure analysis

**DECIDED / 部分 PROTOTYPED**：[失败矩阵](SYNC_FAILURE_RECOVERY.md) 覆盖至少20类要求故障的 Detection/Recovery/Data-loss risk/UI，并含配额/cursor gap。[18个正式不变量](SYNC_TEST_PLAN.md) 逐项标明设计/测试/未实现，包括accepted不丢、幂等、科学不覆盖、append-only审计、checksum、lifecycle/module/Human/AI/Primary边界。

## 19. Open questions

**OPEN QUESTION**：安全库/nonce/vault/recovery；真实离线 Human grant；首批实体浏览器；整批科学 promotion/跨对象依赖；精确数值/cross-language编码；snapshot/ACK lease/故障域；参数业务唯一键；safe merge UX；Relay隐藏撤销/分叉的检测。

## 20. Risks

**OPEN QUESTION**：浏览器清理丢未 ACK 内容，PC-only文件无备份磁盘丢失，受信终端/XSS读内容，keys全丢不可恢复，撤销不能收回副本，Relay关联/流量泄漏，AI明文共享改变E2E边界。处理方向已记录，尚未验收。

## 21. Decisions requiring user approval

人工审查 [ADR-001–010](SYNC_DECISIONS.md) 关键项：

1. Local-first + 无key Relay + Primary非胜者。
2. immutable DAG、保守科学冲突和整批候选屏障；文本建议也先人工确认。
3. 大文件metadata_only、四政策；小文件/流量/云/缓存预算。
4. trusted pairing、recovery kit与密码重置不能解密；暂不开放离线final Human confirmation。
5. retain-until-ack、7/30天不硬删唯一数据、snapshot/lease/备份策略。
6. IndexedDB/OPFS风险、首批平台和前台手动sync。
7. ChatGPT默认A需电脑在线，明确可共享项目/字段与B是否另行opt-in。

这些是供审查的推荐，不是已收到批准。

## 22. Proposed Sprint 1 scope

**NOT IMPLEMENTED，未启动**：批准后先做 wire fixtures/encoding/negative tests、QA Domain transaction+Outbox+Inbox、整批科学批准屏障和权限适配。Relay/E2E/mobile另分阶段与安全评审；本轮无生产migration、Sync API、部署、ChatGPT Remote MCP、Artifact云迁移或MATLAB/COMSOL Agent。

## 需求覆盖索引

| 用户章节 | 交付位置 |
| --- | --- |
| A1–A4 | RELEASE_V0.2.0.md、Release/main/tag、报告1–2 |
| B1–B2、B22、B29 | ARCHITECTURE、DEVICE、CHATGPT |
| B3、B25–B27 | ARTIFACT_POLICY、PROTOCOL bootstrap |
| B4–B5、B21、B24 | DEVICE、DATA_MODEL、SECURITY |
| B6–B10 | DATA_MODEL比较、PROTOCOL、STATE_MACHINE |
| B11–B15、B18–B20 | CONFLICT_POLICY全矩阵、DATA_MODEL、PROTOCOL |
| B16–B17 | DATA_MODEL Audit/Activity、CONFLICT、DEVICE preferences |
| B23 | SECURITY_MODEL、报告13/19/20 |
| B28、B30 | CHATGPT_MODEL、DATA_MODEL Review |
| B31–B33 | FAILURE_RECOVERY、TEST_PLAN、prototype/tests |
| B34–B35 | 12份SYNC文档 + ER + 10份ADR |
| B36–B39 | 状态边界、报告21–22、STOP、原型README |

实际审查与同步结果在RH-009提交正文和最终交付消息登记。**Research Hub v0.3 Sync Architecture Sprint 0 complete.** 完成本轮交付后停止，等待人工架构审查。
