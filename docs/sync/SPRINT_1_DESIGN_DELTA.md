# Sprint 1 Design Delta

基线：`c0852b6`，分支 `codex/researchhub-v0.3`。用户本轮明确授权按冻结架构开发 QA Protocol Kernel。原始请求见 SPRINT_1_REQUIREMENTS.txt；不启用生产同步，不进入 Sprint 2。

## 保留与补齐

保留 Local-first、UUID、immutable DAG、业务变化/单项目批次、Primary 非胜者、科学无 LWW、Human/AI 与冻结 module snapshot。Sprint 0 原型保留为历史证据，不把它改成生产引擎。

补齐：独立 Python/TypeScript 严格 wire 编码与固定 vectors；revision 绑定 transaction/actor/module；QA SQLAlchemy Revision/Transaction/Heads/Dependencies/Projection/Conflict/Audit/Outbox/Inbox；整批科学批准与后到冲突重新评估；fresh Human grant；真实独立 PostgreSQL 原子性/并发/恢复。

## ADR 增量

ADR-003/006 AMENDED：Sprint 0 JCS 是候选。Kernel v1 使用 **RH-C14N-1（受限 JCS 数据子集）**：UTF-16 key 顺序、UTF-8、无 Unicode normalization；原生数字仅 safe integer，科学 decimal/大 integer 用 tagged string。不是支持所有 binary64 的完整 JCS 库。precision/raw representation 属于业务含义，1.60 与1.600 科学数值可相等但 revision 不同。

ADR-004/015：whole-batch 屏障不再仅设计。每个 revision 记录 transaction membership；显式/派生依赖形成 DAG。某对象多头使涉及批次整体 CANDIDATE，递归暂停其依赖批次；历史/Audit保留，accepted投影原子重建。独立批次继续。人工 full-batch review 需覆盖受影响原批次的全部对象，不能只解决压力并自动批准其他字段。

ADR-014：Human session grant 与 scientific consent 分开。QA 注册principal包含user/device/session/project/actor；final操作/解决冲突/生命周期恢复需要fresh grant，绑定transaction+objects+operation+exact heads+expiry。离线final不支持；Codex/ChatGPT/System不能自称Human。grant发行/签名仅QA mock，不是实际认证或E2E。

## Resolution 的两个入口

在线 Human resolve：事务锁下比较提交的 expected_heads 与当前完整 heads，不符拒绝 CONFLICT_CHANGED。离线 resolution proposal：保存此前本机已观察的完整 head set 与候选结果；进入 received history 时允许两个合法独立 proposal 分叉，但不会自动获得 final Human权限。在线 fresh-grant review 再消费当前全部 heads。不得用“允许并发解决”绕过在线 exact-head 检查。

## QA 与现有产品

Kernel模块不导入 main、不增加HTTP/UI，不修改生产Base或自动migration。独立新建 loopback Docker PostgreSQL、专门数据库 `researchhub_sync_kernel_qa`；环境必须显式QA开关、数据库名/角色校验。测试模型单独metadata，禁止回退DATABASE_URL。

QA Domain adapter 使用现有 service.create_record/scientific_authority/project_for/audit 与同一个 Session；组合Run/Parameters/Metrics并在同事务写outbox/kernel receipt。现有service只有flush无commit，故无需重写service/main。导入 adapter 不激活它。涉及 accepted projection 的远端 apply 只写QA projection表，不直接把候选写入个人 v0.2 records；这是可映射的Domain边界而非部署。

## 文件边界

Python：apps/api/researchhub/sync（canonical/protocol/authority/models/kernel/projection/domain_qa）；TS：packages/sync-protocol（纯库及测试）；共享 fixtures/sync/v1；测试tests/sync_kernel、tests/sync_vectors、tests/sync_pg。scripts/sync-qa.py负责隔离运行，scripts/sync-benchmark.py负责合成规模观察；requirements仅QA测试依赖。正式migration、移动/云/E2E均不实现。
