# Sync Protocol Kernel Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development，fresh implementer + 规格后质量审查。用户明确继续当前codex/researchhub-v0.3，不创建不同开发线；QA存储独立，未授权生产同步或Sprint2。

**Goal:** 交付跨语言identity、整批科学屏障和真实QA PostgreSQL的六Gate，最后STOP。

**Architecture:** RH-C14N-1业务wire + 不可变DAG/transaction/dependency + 独立accepted projection。QA adapter组合已有service/同Session outbox，生产main和migration不变。

**Tech Stack:** Python/SQLAlchemy/psycopg/pytest/Hypothesis；独立TypeScript纯库与Node测试；新建隔离PostgreSQL17。

## Task 1 — Canonical identity（RH-010）

Files: apps/api/researchhub/sync/{__init__,canonical,protocol}.py；packages/sync-protocol/{canonical,schema,index,test}.*；fixtures/sync/v1；tests/sync_vectors；SYNC_WIRE_FORMAT与ADR011/012。

- [x] 保存原始请求，按WIRE规范建立fixed vectors，先RED：

```python
def test_utf16_order(canonical_bytes):
    assert canonical_bytes({'\ue000':0,'😀':1}) == '{"😀":1,"":0}'.encode()
```

- [x] Python/TS独立encode/strict decode/revision/transaction validate；为malformed/duplicate/unsafe/decimal/calendar/module/父引用结构建立fixture。核心API `canonical_bytes(value)`, `strict_loads(raw)`, `revision(change)`, `transaction_digest(tx)`, `validate_transaction(tx)`。
- [x] pytest tests/sync_vectors；Node TS测试；typecheck；spec→quality修复并复验。核对unsafe integer/Unicode保真、transport改变不改revision。
- [ ] CHANGELOG/RH-010四段中文提交、推送；不要将encoder结果当E2E证明。

## Task 2 — QA revision/transaction kernel（RH-011）

Files: sync/{models,authority,kernel,projection,domain_qa}.py；tests/sync_kernel、tests/sync_pg；scripts/sync-qa.py、sync-benchmark.py；QA requirements；protocol fixtures。

- [ ] RED各CaseE–Z，尤其：

```python
def test_late_fork(kernel, batch_a, batch_b, dependent):
    kernel.apply(batch_a)
    kernel.apply(dependent)
    kernel.apply(batch_b)
    assert kernel.transaction_state(batch_a['transaction_id']) == 'CANDIDATE'
    assert kernel.transaction_state(dependent['transaction_id']) == 'CANDIDATE'
```

- [ ] 不可变SQL表+heads索引+transaction成员/依赖；整批candidate和late invalidation审计；fresh Human grant验证；inbox/outbox/cursor单事务。
- [ ] PostgreSQL按项目行锁串行化同项目apply/resolve（不同项目独立），与当前service项目锁顺序一致；在线exact heads原子检查，离线proposal无final权限但可保留并发候选。
- [ ] 独立新Docker loopback PG数据库/QA角色；同Session调用service.create_record组合Run+6参数+3指标，flush后outbox，异常全部rollback。无个人DB回退/自动migration。
- [ ] pytest真实PG覆盖locking/unique/duplicate/不同对象/同对象/resolution race/late divergence/依赖。六处crash点各自rollback、随机重试用Hypothesis而非自造random harness。
- [ ] 合成artifact metadata/校验receipt无cloudbytes；普通text三方suggestion若实现只返回建议，HumanConclusion禁merge；TagORset暂不实现。
- [ ] benchmark10k revisions/1k objects/100conflicts/100changes，记录实际scope和复杂度观察，不宣称已优化分布式系统。

## Task 3 — Regression/review/report/STOP

- [ ] 重新运行existing backend/MCP/release、frontend/test/type/build、Ruff、Docker API/Web build/隔离Compose，不触及个人数据库。
- [ ] CI加入fixtures/kernel tests与真实PG服务、明确QA开关/URL，不把PG测试skip当通过。
- [ ] 更新协议/数据模型/状态机/冲突/测试/ADR013–015；新增transaction model和23主题SPRINT_1_REPORT；逐Gate给PASS/FAIL及真实证据。
- [ ] 规格→质量完整复审修复；暂存区/凭据/原始数据/稳定tag核对；RH-011提交推送并核对CI。
- [ ] 六Gate皆PASS才输出“Research Hub v0.3 Sprint 1 — Sync Protocol Kernel complete.”；STOP等人工审查，不进入Secure Relay。
