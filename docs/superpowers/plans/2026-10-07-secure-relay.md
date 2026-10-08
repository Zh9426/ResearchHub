# Research Hub Sprint 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox syntax for tracking. One implementation worker at a time; independent specification review then quality/security review before advancing.

**Goal:** 在独立合成 QA 环境交付 Python/TypeScript 加密互通与真实 HTTPS/PostgreSQL Relay，八项安全 gate 有可重跑证据。

**Architecture:** 公共 wire 验证模块与持有密钥的客户端分离；Relay 只验证签名并持久保存密文。客户端认证完整传输页、解密后进入既有 Sync Kernel，transport cursor 与科学水位分别记录。main/v0.2.0、个人服务、生产 migration 和 UI 不变。

**Tech Stack:** Python3.12 cryptography50.0.2、Node24 WebCrypto、@hpke/core1.9.0、SQLite nonce ledger+witness、FastAPI/Uvicorn、隔离 PostgreSQL17、httpx verified TLS、pytest/Hypothesis、Node test。

需求主清单：`docs/sync/SPRINT_2_REQUIREMENTS.txt`；冻结契约：`SPRINT_2_SECURITY_DELTA.md`、`CRYPTO_LIBRARY_REVIEW.md`。不把静态检查/测试替身算作网络或真实数据库验收。固定私钥只限明确公开 TEST ONLY 向量，随机运行时钥匙位于忽略的 storage/runtime。

## Task 0 — 安全设计与库 gate

- [x] 保存完整需求，核对现有 branch/HEAD/远端/CI，读取原 Kernel 与安全文档。
- [x] 写安全增量和官方库比较；npm registry 实查 core latest1.9.0、MIT、依赖common^1.10.0；冻结 lockfile 时记录实际树。
- [x] 独立安全设计审查PASS；六项状态规则缺口及recovery唯一授权例外修订，记录前置 gate SELECTED。
- [x] 写 ADR016–025；RH012=5aef6e7已推送，后续协议文档必须与实现一致。

## Task 1 — Crypto / SecureEnvelope / durable nonce

**Create:** `packages/secure_wire/{__init__,envelope}.py` 仅公共 canonical/Ed25519 验证；`apps/api/researchhub/sync/secure/{__init__,crypto,envelope,nonce}.py`；`packages/secure-sync/{package.json,package-lock.json,tsconfig.json,src/{crypto,envelope,nonce}.ts,test/crypto.test.ts}`；`fixtures/sync/secure-v1/` 标记 TEST ONLY；`tests/secure_sync/{conftest,test_crypto,test_nonce,test_properties}.py`；`tests/secure_sync/requirements.txt`。

- [x] 先建立标准 fixed bytes/signature/HPKE vectors，Python 与 TS 各自独立解码和 primitive 调用。AES-GCM、Ed25519、HPKE 双向、AES-KW；HPKE info 完全一致，Base 的来源由已锚定 authority signature 认证。
- [x] RED：不存在的 secure API、字段变异、错误 key/tag/signature/info、unknown version/suite、超长与 malformed 全部失败。代表断言：

```python
with pytest.raises(SecureError):
    open_envelope({**sealed, "key_epoch": 2}, key, signer_public, expected)
assert canonical_bytes(open_envelope(sealed, key, signer_public, expected)) == canonical_bytes(tx)
```

- [x] GREEN：冻结 header、AAD `ResearchHub/AEAD/v1\0`、signature preimage `ResearchHub/SecureEnvelope/v1\0`；ciphertext||tag、canonical unpadded base64url。完整未知字段/安全整数/UUID/hash/长度校验，解密后 canonical/digest/semantic identity 再校验。
- [x] NonceVault API `reserve(key_fingerprint,prefix)->bytes`：SQLite BEGIN IMMEDIATE/sync FULL → append/fsync witness → commit → return。存储注册身份不可悄悄清零；恢复缺失/回滚 fail closed；overflow fail closed；unique prefix authority 分配。两语言共格式可并行预约；支持范围与全可信材料同时 rollback 限制明确。
- [x] RED→GREEN：真实子进程并发、重启、crash 各切点、删除 ledger、恢复旧 ledger、witness 损坏、overflow、缓存 exact retry/new wrapper semantic identity；Hypothesis generated schedules 与 ciphertext/header mutations。
- [x] Run `.venv/Scripts/python -m pytest tests/secure_sync -q`、`npm --prefix packages/secure-sync test`、`npm --prefix packages/secure-sync run typecheck`。首轮仅本任务 tests，不能提前声称 Relay gate。
- [x] 独立规格审查→修复→复审；独立质量/安全审查→修复→复审。根代理按 RH013 聚焦提交、四段中文正文、CHANGELOG、推送。RH013=deec29e，远端 SHA 一致；CI37706614320 success（2026-10-08 核对）。

## Task 2 — Trusted lifecycle / pairing / recovery / anchors / chunks

**Create:** secure Python `keys.py,pairing.py,checkpoint.py,artifacts.py`；TS 对应 library；`tests/secure_sync/test_{lifecycle,pairing,checkpoint,artifacts}.py` 与 TS interop 扩展；协议文档 `SYNC_SECURE_ENVELOPE,SYNC_KEY_LIFECYCLE,SYNC_PAIRING,SYNC_CHECKPOINTS.md`。

- [x] RED：PENDING 不得 push/key；签名外部 root 不得接管；epoch 回滚和跳跃无授权拒绝；全 members/prefix 唯一不可复用。
- [x] GREEN：完整签名 membership transition 绑定 previous digest、authority、current/new epochs；客户端持久 pin owner/recovery root 和 epoch/digest。member role owner/writer/reader 与 ACTIVE/PENDING/REVOKED 明确，替换 key/pubkey 不允许匿名发生。
- [x] RED→GREEN pairing：5分钟过期、单次、最多5次错误证明、篡改任意 project/recipient/keys/fingerprint/role/session 拒绝；recipient possession proof、human scope/fingerprint/SAS 确认；signed grant 验证先于 HPKE unwrap。
- [x] RED→GREEN revoke B：membership/key epoch 都提升，fresh key仅给active，旧 envelope 不因timestamp接受，B既无new grant也不能decrypt C的未来消息。所有合法非 revoked 收件人双向独立wrap/unwrap。
- [x] RED→GREEN recovery：lostphone/PC/密码/new trusted device/kit；密码不等于keys；kit高熵材料与公开 trust anchor；全丢精确 `E2E_DATA_UNRECOVERABLE`。补public Kit journal/head持久加载与manifest/checkpoint同事务，真实子进程重建及SQLite COMMIT失败通过；无服务端master。
- [x] RED→GREEN anchor：持久cursor+chain，older/samecursor不同hash/缺页/伪造签名拒绝；签名加密snapshotmanifest prototype；split-view/transparency明确NOT IMPLEMENTED。
- [x] RED→GREEN chunks：小合成文件 freshDEK/AESKW inside encrypted manifest；每块≤64KiB、AAD context/index/count/size，bounded iterable/sink；错顺序/缺块/重复/size/hash/epoch/tag拒绝，重试不重复写sink。TS与Python独立 roundtrip。
- [x] 运行本任务、Task1所有crypto/property/vector/typecheck；root排TLS合并218/Node38/typecheck/Ruff通过；spec PASS、quality/security APPROVED。RH014=31d22df已推送，远端SHA一致，CI37735346855现有三job success；完整可信材料一致回滚等局限保留，未宣称网络或最终Gate通过。

## Task 3 — Actual HTTPS PG Relay / trusted receive / faults

**Create:** `apps/relay/researchhub_relay/{__init__,main,models,service,qa}.py`、`apps/relay/requirements.txt`、`apps/relay/Dockerfile`；`scripts/secure-relay-qa.py`、`infrastructure/secure-relay-qa.compose.yml`；客户端secure `transport.py`；`tests/secure_relay/{conftest,test_network,test_faults,test_privacy,test_authority,test_limits}.py`；`SYNC_RELAY.md`。

2026-10-08 实测 internal-only 已发布端口在当前 Docker Desktop 不可达，采用已独立 DESIGN PASS 的固定目标 TCP 入口：Relay 只连 internal data QA network；入口和 PG 只连 data/transport 两个专用 QA network；仅入口发布127.0.0.1:38001，TLS从客户端直达Relay。实施必须核验实际网络、端口、挂载、权限和成员，不只检查label。PG退出default bridge。入口限连接/缓冲/超时，日志与文件纳入隐私检查。

Task3范围较大，按依赖拆为两个依次实施的子任务，每个均需独立spec→quality/security审查，不并发实施：

1. **Task3A — Relay与隔离网络**：QA guard、固定TCP入口、实际TLS、public-only image、严格signed request、会员/配对public metadata、PG durable receipt、opaque chunk、quota/log/error、真实Relay/PG/入口故障及直接DB隐私检查。完成不等于Network Durability Gate通过，因为可信客户端原子接收尚待Task3B。
2. **Task3B — 可信客户端与完整故障证据**：不可变outbox、完整page预验证、outer cursor/chain与Kernel同事务、历史隔离、double authentication、client真实kill、完整canary与成熟网络property测试、实际网络性能。不得改变Sprint1科研语义。

Task3A当前：实现与两个独立审查已通过。spec首轮P1隐私扫描假阴性和2项P2类型混同均实际RED→GREEN；spec复审55 passed / 284.64s，quality55 passed / 288.64s、lifecycle3、TLS2及12个额外配对负例通过。root提交前网络55 passed / 284.98s、v2隐私98,100,447 bytes零命中、本地依赖220/Node38/typecheck通过；本次RH-015记录Task3A。Task3B尚未开始。

聚焦提交编号依次递增；拆分后Task4编号相应顺延，不固定使用RH016。Task2两个审查均通过后才派发Task3A。

- [ ] RED QA guard：无opt-in/个人DB/远程host拒绝；只允许 actual researchhub_secure_relay_qa/researchhub_relay_qa 35434，initialize 核验 current_database/current_user。
- [ ] 启动专用PG与TLS server，随机临时credentials/CA/servercert存在storage忽略目录；127.0.0.1SAN。用httpx CA/hostname verification；wrongCA/hostname/HTTP拒绝。
- [ ] RED→GREEN strict signedrequests，绑定method/path/project/device/currentepoch/body或query/requestID；ratequota/body/page/batch/timeouts/pairing attempts；reader不能write，uuid-onlyGET不能read，SQL/path injection无执行入口。
- [ ] PG project行锁，envelope signature+membership验证；unique messageID/digest与epoch/nonce；同ID同bytes返originalreceipt，异bytes失败。sequence/ciphertext/receipt sync_commit 同事务，commit才ACK。Relay包与image无Domain decoder/AEAD/project/privatekeys、无clientvault mounts。
- [ ] 客户端 validate whole page contiguous chain、envelope/digest/epochs，然后使用本地principal/grant调用Kernel；transport cursor持久化与apply同一个QA Kernel session（额外transport状态只在QA表）。重复wrapper不扩大innercursor；科研candidate可transport ACK但不能scientific ACK；Device签名不能制造Human。
- [ ] 实际 TLS socket 半上传/上传后断开、子进程killbeforecommit/aftercommitbeforeACK、ACK丢失、duplicate POST/GET、partialpage、outoforderretry、Relayrestart和PGrestart。每故障验证PG完整性、retryreceipt、cursor/gap与Kernel幂等。
- [ ] 直接PGdump、Relay persisted files/log scan synthetic research canaries及runtime钥匙多种编码；zero hits；allowlist日志与HTTP稳定errorcode无payload/SQLstack。retain_until_ack仅metadata，无GC。
- [ ] Task3A/3B分别两阶段独立review与聚焦commit/push，RH015起依次递增；未完成gate明确未完成。

## Task 4 — Complete gates / independent security audit / regression / report / CI

**Modify:** `.github/workflows/ci.yml` 加secure-relay-qa job；`docs/sync/{SYNC_SECURITY_MODEL,SYNC_PROTOCOL,SYNC_STATE_MACHINE,SYNC_FAILURE_RECOVERY,SYNC_TEST_PLAN,SYNC_DECISIONS}.md`；新增 `SPRINT_2_REPORT.md`；`CHANGELOG.md`。

- [ ] 成熟 Hypothesis覆盖crypto roundtrip/signature mutations、nonce concurrent/restart generated schedules、idempotency/retry/invalid envelopes/chunk permutations；property nofake standalone random loop。
- [ ] 实测 encrypt/decrypt/verify、100消息push/pull、小Artifact性能，记录机器/limits/timing/no分布式承诺。
- [ ] 新 CI 真实隔离PG、Node/Python独立库、临时keys/TLS/network/fault/canary、finally destroy，旧frontend/backend/kernel jobs保留green。
- [ ] 独立 securityreview逐项keys/log/DB/nonce/replay/signatureAAD/downgrade/revoke/pair/recover/errors/staged Git。每finding有RED→fix→GREEN，review PASS后跑完整test。
- [ ] 重新运行Sprint0 prototype、Sprint1vectors/TS/实际PG、backend/MCP/release、frontend/typecheck/isolatedbuild、实际v02QA integration/restart/backup；无skip记证据。未运行必须给原因，不抵充验收。
- [ ] Report30主题及A–Z需求映射、IMPLEMENTED/CROSS-LANGUAGE/NETWORK/SECURITY/DESIGNED ONLY/NOT IMPLEMENTED/BLOCKED准确分类；八gate PASS/FAIL逐项命令证据，任何FAIL overallFAIL。
- [ ] 最终使用下一递增RH编号commit四段正文、暂存差异与secretcheck，推送当前trackingbranch，核对remoteSHA与所有CI job。main/tagfreeze不动。
- [ ] 只有八gatePASS和requiredchecks完成才final complete；之后STOP，等待人工审查，不开始Sprint3。
