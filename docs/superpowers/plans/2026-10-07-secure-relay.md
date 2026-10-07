# Research Hub Sprint 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox syntax for tracking. One implementation worker at a time; independent specification review then quality/security review before advancing.

**Goal:** 在独立合成 QA 环境交付 Python/TypeScript 加密互通与真实 HTTPS/PostgreSQL Relay，八项安全 gate 有可重跑证据。

**Architecture:** 公共 wire 验证模块与持有密钥的客户端分离；Relay 只验证签名并持久保存密文。客户端认证完整传输页、解密后进入既有 Sync Kernel，transport cursor 与科学水位分别记录。main/v0.2.0、个人服务、生产 migration 和 UI 不变。

**Tech Stack:** Python3.12 cryptography50.0.2、Node24 WebCrypto、@hpke/core1.9.0、SQLite nonce ledger+witness、FastAPI/Uvicorn、隔离 PostgreSQL17、httpx verified TLS、pytest/Hypothesis、Node test。

需求主清单：`docs/sync/SPRINT_2_REQUIREMENTS.txt`；冻结契约：`SPRINT_2_SECURITY_DELTA.md`、`CRYPTO_LIBRARY_REVIEW.md`。不把静态检查/测试替身算作网络或真实数据库验收。固定私钥只限明确公开 TEST ONLY 向量，随机运行时钥匙位于忽略的 storage/runtime。

## Task 0 — 安全设计与库 gate

- [x] 保存完整需求，核对现有 branch/HEAD/远端/CI，读取原 Kernel 与安全文档。
- [x] 写安全增量和官方库比较；npm registry 实查 core latest1.9.0、MIT、依赖common^1.10.0；冻结 lockfile 时记录实际树。
- [ ] 独立安全设计审查，修正具体问题，记录前置 gate SELECTED。
- [ ] 写 ADR016–025；后续协议文档必须与实现一致。

## Task 1 — Crypto / SecureEnvelope / durable nonce

**Create:** `packages/secure_wire/{__init__,envelope}.py` 仅公共 canonical/Ed25519 验证；`apps/api/researchhub/sync/secure/{__init__,crypto,envelope,nonce}.py`；`packages/secure-sync/{package.json,package-lock.json,tsconfig.json,src/{crypto,envelope,nonce}.ts,test/crypto.test.ts}`；`fixtures/sync/secure-v1/` 标记 TEST ONLY；`tests/secure_sync/{conftest,test_crypto,test_nonce,test_properties}.py`；`tests/secure_sync/requirements.txt`。

- [ ] 先建立标准 fixed bytes/signature/HPKE vectors，Python 与 TS 各自独立解码和 primitive 调用。AES-GCM、Ed25519、HPKE 双向、AES-KW；HPKE info 完全一致，Base 的来源由已锚定 authority signature 认证。
- [ ] RED：不存在的 secure API、字段变异、错误 key/tag/signature/info、unknown version/suite、超长与 malformed 全部失败。代表断言：

```python
with pytest.raises(SecureError):
    open_envelope({**sealed, "key_epoch": 2}, key, signer_public, expected)
assert canonical_bytes(open_envelope(sealed, key, signer_public, expected)) == canonical_bytes(tx)
```

- [ ] GREEN：冻结 header、AAD `ResearchHub/AEAD/v1\0`、signature preimage `ResearchHub/SecureEnvelope/v1\0`；ciphertext||tag、canonical unpadded base64url。完整未知字段/安全整数/UUID/hash/长度校验，解密后 canonical/digest/semantic identity 再校验。
- [ ] NonceVault API `reserve(key_fingerprint,prefix)->bytes`：SQLite BEGIN IMMEDIATE/sync FULL → append/fsync witness → commit → return。存储注册身份不可悄悄清零；恢复缺失/回滚 fail closed；overflow fail closed；unique prefix authority 分配。两语言共格式可并行预约；支持范围与全可信材料同时 rollback 限制明确。
- [ ] RED→GREEN：真实子进程并发、重启、crash 各切点、删除 ledger、恢复旧 ledger、witness 损坏、overflow、缓存 exact retry/new wrapper semantic identity；Hypothesis generated schedules 与 ciphertext/header mutations。
- [ ] Run `.venv/Scripts/python -m pytest tests/secure_sync -q`、`npm --prefix packages/secure-sync test`、`npm --prefix packages/secure-sync run typecheck`。首轮仅本任务 tests，不能提前声称 Relay gate。
- [ ] 独立规格审查→修复→复审；独立质量/安全审查→修复→复审。根代理按 RH012 聚焦提交、四段中文正文、CHANGELOG、推送。

## Task 2 — Trusted lifecycle / pairing / recovery / anchors / chunks

**Create:** secure Python `keys.py,pairing.py,checkpoint.py,artifacts.py`；TS 对应 library；`tests/secure_sync/test_{lifecycle,pairing,checkpoint,artifacts}.py` 与 TS interop 扩展；协议文档 `SYNC_SECURE_ENVELOPE,SYNC_KEY_LIFECYCLE,SYNC_PAIRING,SYNC_CHECKPOINTS.md`。

- [ ] RED：PENDING 不得 push/key；签名外部 root 不得接管；epoch 回滚和跳跃无授权拒绝；全 members/prefix 唯一不可复用。
- [ ] GREEN：完整签名 membership transition 绑定 previous digest、authority、current/new epochs；客户端持久 pin owner/recovery root 和 epoch/digest。member role owner/writer/reader 与 ACTIVE/PENDING/REVOKED 明确，替换 key/pubkey 不允许匿名发生。
- [ ] RED→GREEN pairing：5分钟过期、单次、最多5次错误证明、篡改任意 project/recipient/keys/fingerprint/role/session 拒绝；recipient possession proof、human scope/fingerprint/SAS 确认；signed grant 验证先于 HPKE unwrap。
- [ ] RED→GREEN revoke B：membership/key epoch 都提升，fresh key仅给active，旧 envelope 不因timestamp接受，B既无new grant也不能decrypt C的未来消息。所有合法非 revoked 收件人双向独立wrap/unwrap。
- [ ] RED→GREEN recovery：lostphone/PC/密码/new trusted device/kit；密码不等于keys；kit高熵材料与公开 trust anchor；全丢精确 `E2E_DATA_UNRECOVERABLE`。撤销最后owner的授权与recovery scope必须验证，无服务端master。
- [ ] RED→GREEN anchor：持久cursor+chain，older/samecursor不同hash/缺页/伪造签名拒绝；签名加密snapshotmanifest prototype；split-view/transparency明确NOT IMPLEMENTED。
- [ ] RED→GREEN chunks：小合成文件 freshDEK/AESKW inside encrypted manifest；每块≤64KiB、AAD context/index/count/size，bounded iterable/sink；错顺序/缺块/重复/size/hash/epoch/tag拒绝，重试不重复写sink。TS与Python独立 roundtrip。
- [ ] 运行本任务、Task1所有 crypto/property/vector/typecheck；两阶段独立审查后 RH013 聚焦提交推送。

## Task 3 — Actual HTTPS PG Relay / trusted receive / faults

**Create:** `apps/relay/researchhub_relay/{__init__,main,models,service,qa}.py`、`apps/relay/requirements.txt`、`apps/relay/Dockerfile`；`scripts/secure-relay-qa.py`、`infrastructure/secure-relay-qa.compose.yml`；客户端secure `transport.py`；`tests/secure_relay/{conftest,test_network,test_faults,test_privacy,test_authority,test_limits}.py`；`SYNC_RELAY.md`。

- [ ] RED QA guard：无opt-in/个人DB/远程host拒绝；只允许 actual researchhub_secure_relay_qa/researchhub_relay_qa 35434，initialize 核验 current_database/current_user。
- [ ] 启动专用PG与TLS server，随机临时credentials/CA/servercert存在storage忽略目录；127.0.0.1SAN。用httpx CA/hostname verification；wrongCA/hostname/HTTP拒绝。
- [ ] RED→GREEN strict signedrequests，绑定method/path/project/device/currentepoch/body或query/requestID；ratequota/body/page/batch/timeouts/pairing attempts；reader不能write，uuid-onlyGET不能read，SQL/path injection无执行入口。
- [ ] PG project行锁，envelope signature+membership验证；unique messageID/digest与epoch/nonce；同ID同bytes返originalreceipt，异bytes失败。sequence/ciphertext/receipt sync_commit 同事务，commit才ACK。Relay包与image无Domain decoder/AEAD/project/privatekeys、无clientvault mounts。
- [ ] 客户端 validate whole page contiguous chain、envelope/digest/epochs，然后使用本地principal/grant调用Kernel；transport cursor持久化与apply同一个QA Kernel session（额外transport状态只在QA表）。重复wrapper不扩大innercursor；科研candidate可transport ACK但不能scientific ACK；Device签名不能制造Human。
- [ ] 实际 TLS socket 半上传/上传后断开、子进程killbeforecommit/aftercommitbeforeACK、ACK丢失、duplicate POST/GET、partialpage、outoforderretry、Relayrestart和PGrestart。每故障验证PG完整性、retryreceipt、cursor/gap与Kernel幂等。
- [ ] 直接PGdump、Relay persisted files/log scan synthetic research canaries及runtime钥匙多种编码；zero hits；allowlist日志与HTTP稳定errorcode无payload/SQLstack。retain_until_ack仅metadata，无GC。
- [ ] 两阶段独立 review；RH014 聚焦commit/push（未完成gate明确未完成）。

## Task 4 — Complete gates / independent security audit / regression / report / CI

**Modify:** `.github/workflows/ci.yml` 加secure-relay-qa job；`docs/sync/{SYNC_SECURITY_MODEL,SYNC_PROTOCOL,SYNC_STATE_MACHINE,SYNC_FAILURE_RECOVERY,SYNC_TEST_PLAN,SYNC_DECISIONS}.md`；新增 `SPRINT_2_REPORT.md`；`CHANGELOG.md`。

- [ ] 成熟 Hypothesis覆盖crypto roundtrip/signature mutations、nonce concurrent/restart generated schedules、idempotency/retry/invalid envelopes/chunk permutations；property nofake standalone random loop。
- [ ] 实测 encrypt/decrypt/verify、100消息push/pull、小Artifact性能，记录机器/limits/timing/no分布式承诺。
- [ ] 新 CI 真实隔离PG、Node/Python独立库、临时keys/TLS/network/fault/canary、finally destroy，旧frontend/backend/kernel jobs保留green。
- [ ] 独立 securityreview逐项keys/log/DB/nonce/replay/signatureAAD/downgrade/revoke/pair/recover/errors/staged Git。每finding有RED→fix→GREEN，review PASS后跑完整test。
- [ ] 重新运行Sprint0 prototype、Sprint1vectors/TS/实际PG、backend/MCP/release、frontend/typecheck/isolatedbuild、实际v02QA integration/restart/backup；无skip记证据。未运行必须给原因，不抵充验收。
- [ ] Report30主题及A–Z需求映射、IMPLEMENTED/CROSS-LANGUAGE/NETWORK/SECURITY/DESIGNED ONLY/NOT IMPLEMENTED/BLOCKED准确分类；八gate PASS/FAIL逐项命令证据，任何FAIL overallFAIL。
- [ ] 最终 RH015 commit四段正文、暂存差异与secretcheck，推送当前trackingbranch，核对remoteSHA与所有CI job。main/tagfreeze不动。
- [ ] 只有八gatePASS和requiredchecks完成才final complete；之后STOP，等待人工审查，不开始Sprint3。
