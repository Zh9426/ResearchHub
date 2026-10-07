# Sprint 2 Secure Relay & E2E Transport 设计增量

状态：安全实现前设计，QA ONLY / SYNTHETIC DATA ONLY / LOOPBACK ONLY。Sprint0/1已获用户人工批准，本轮按请求继续当前codex/researchhub-v0.3；baseline334e6c0与远端/CI success核对一致，main/v0.2.0 commit4a4db4a未移动。需求见SPRINT_2_REQUIREMENTS.txt。

## Threat model 与 trust boundaries

Relay被视为hostile：可读自己的PG、ciphertext files/logs，复制、重放、隐藏、删除、重排、回滚和split-view。保护研究payload、文件名、HumanConclusion/Audit及项目/设备/recovery私钥。可泄漏opaque项目/设备、epoch、消息/摘要/依赖关联、大小与活动时间。E2E不保证availability、消除流量分析或让已知明文被遗忘。

四层分开：纯公共wire/signature验证模块 → 独立Relay（无Domain decoder/解密key）→ trusted secure client（验签、解密、digest）→ 原Sync Kernel（principal/grant与科研屏障）。不修改生产main、MCP contract、UI、个人PG/MinIO或Alembic。

Relay容器只安装服务、公钥验证与pure canonical依赖，不挂载客户端vault、fixtures、tests、runtime研究数据。TLS server key仅传输身份，不是Device/Project key。当前Node仅合成测试；不以语言permission flag作为恶意进程的秘密隔离措施。

## Library selection 与 primitive suite

采用CRYPTO_LIBRARY_REVIEW.md的SELECTED标准方案：cryptography50.0.2 / NodeWebCrypto / @hpke/core1.9.0（实际锁定并确认≥1.7.5）。AES-256-GCM正文、Ed25519签名、RFC9180 Base X25519/HKDF-SHA256/AES256GCM recipient wrap；单次HPKE info绑定context、aad空。Base不认证sender，membership grant签名层认证authority。Artifact DEK由AES-KW包裹；没有自研primitive。

比较过PyHPKE（新增依赖不必要）与libsodium方案（不能把匿名sealed-box称authenticated HPKE）。上游core并发nonce公告要求修复版本，且本实现始终fresh one-shot context。没有宣称整体协议已外部审计。

## Key hierarchy 与 TEST ONLY vault

每设备独立UUID、Ed25519 signing key、X25519 recipient key；每project/epoch独立随机32-byte content key；每Artifact独立随机DEK。Account master/recovery随机材料与密码分离。客户端KeyVault/DeviceKeyStore接口承载内存或忽略临时加密材料；不把钥匙写Relay、Audit、普通日志或Git。固定公开deterministic TEST ONLY vectors按需求66明确标记；运行时私钥不入Git。

项目bootstrap的authority/recovery公钥通过可信本地创建/配对fingerprint锚定，客户端不相信Relay返回的新root。membership manifest是完整、签名的项目成员状态，含epochs、设备两公钥/fingerprint、role/status、granted/revoked时间、authority与previous digest；不接受Relay自行授予成员。PENDING→ACTIVE→REVOKED。role为owner/writer/reader，writer不能改变membership，reader不能推mutation。

## Nonce construction 与 crash policy

AES-GCM nonce为4-byte writer prefix +8-byte big-endian counter。每项目authority为设备分配不重用的uint32 prefix（全成员含已撤销设备保留），grant签名绑定；多个设备共享同epoch key但nonce空间不重叠。counter上限9007199254740991，保持RH-C14N-1，不使用timestamp/随机96-bit nonce/内存counter。

TEST ONLY NonceVault使用SQLite BEGIN IMMEDIATE、synchronous=FULL与独立fsync witness，按key fingerprint/prefix分配。预约counter→fsync witness→DB commit→才允许加密。未完成commit不得返回nonce；crash造成gap或ledger<witness时fail closed，不能清零。重启/并行Python与Node共享同格式ledger；key丢失、counter丢失、rollback或overflow要求新key epoch/新prefix。支持模型为正常进程/DB恢复和可检测单ledger回滚；同时恶意回滚所有可信本地材料不在支持范围，恢复备份须rotate后再写。

合法retry重发已缓存完整envelope，不再次加密；合法re-encryption使用新message_id、新预约nonce，semantic revision/digest不变。HPKE内部nonce由标准one-shot API管理，fresh ephemeral context不复用；Artifact独立DEK沿用同预约规则。反对以确定性测试向量充当运行时nonce安全证明。

## SecureEnvelope v1、AAD 与 signature scope

冻结纯header：envelope_version=1、crypto_suite、protocol_version=1、schema_version=1、record_type（transaction/snapshot/artifact_manifest）、opaque_project_id、sender_device_id、membership_epoch、key_epoch、message_id、semantic_transaction_digest、dependencies（排序UUID）、nonce（lowerhex12bytes）、checkpoint_sequence（safe int）。外加ciphertext（canonical base64url无padding）、ciphertext_digest（lowerhexSHA256）、signature（base64url64bytes）。严格exact字段、safe整数、版本/suite、UUID/长度/编码；未知拒绝。

AAD=`ResearchHub/AEAD/v1\0 || canonical(header)`。签名preimage=`ResearchHub/SecureEnvelope/v1\0 || canonical(envelope_without_signature)`；签名覆盖全部header、ciphertext/hash，防project/device/epoch/message/deps/nonce/downgrade替换。plaintext为Sprint1 canonical transaction；decrypt后重新验证digest、project映射、device、protocol/schema/dependencies，才传Kernel。snapshot record另解码manifest，不进入Domain mutation。Plaintext byte canonical一致才接受。

pure公共wire模块仅依赖canonical与Ed25519公钥验证，不导入Domain decoder或私钥/AEAD；Relay不解密。注册public key必须从已验签manifest取得，nonce prefix必须匹配设备，old epoch/unknown suite fail closed。合法设备不等于Human：Kernel context从本地可信principal/grant来源取得，不从签名header制造Human权限。

## Pairing 与 project key distribution

新设备自己生成keys。trusted owner创建5分钟内一次性challenge，绑定session、recipient UUID/two public keys/fingerprints、selected opaque project、role与当前manifest digest。双方人工确认fingerprint/SAS、project、role；QA文本representation，不实现摄像头或browser presence。

挑战由trusted client保存状态、expiry/consumed/attempt计数；Relay只转存公开签名挑战。recipient证明私钥持有，owner验证并一次性消费，生成签名membership manifest/grant与HPKE wrapped project key（info绑定project/recipient/epoch/keys/session）。接收先核验锚定authority签名、challenge/session和自己的recipient，再unwrap；用户名密码不提供key。fresh-grant仍是原QA mock科研授权，配对确认不批准科学final。

## Membership epoch、revocation 与 recovery

成员变化提升membership_epoch；撤销同时提升key_epoch、产生全新随机project key，仅给仍active的获准recipient wrap。旧成员不能push、旧epoch消息拒绝/隔离，不根据created_at倒推权限；旧设备不能解密新key epoch，过去明文/旧key无法回收。

Recovery kit是高熵独立authority/recipient材料，项目为它保存标准wrapped keys和签名授权锚点。丢phone可由另一owner撤销/换key；丢primary可用kit证明持有来授权新设备/换epochs，非密码重置。丢密码但keys仍有只改变登录，不能通过Relay自动恢复key。所有设备私钥+kit全丢明确E2E_DATA_UNRECOVERABLE，不设server master key。recover路径同样绑定project、完整manifest、recipient、新epoch并签名，不允许旧状态覆盖当前epoch。

## Relay PG、API 与 durable ACK

独立researchhub_secure_relay_qa/researchhub_relay_qa、loopback35434，新专用容器。初始化要求HUB_RELAY_QA=1及实际DB/role/host核验，不回退产品URL。保存public membership/challenge、完整ciphertext envelope、wrapped keys、message id/digest/sequence/receipt、ciphertext blob、ack stages、checkpoint与retain_until_ack；不存研究明文、project key或private key。

API最小POST hello/messages/ack、GET messages、POST pairing/membership/checkpoints与必要opaque blob接口。签名request proof绑定endpoint、method、project、device、epoch、body/query与request ID，nonce/challenge重放状态受约束；GET不能只凭device UUID读。mutation存储按项目PG行锁，receipt仅在sync_commit commit后返回，same ID/same完整bytes返原receipt、异bytes拒绝。重加密新wrapper可以多次transport stored，Kernel仍按semantic tx幂等。

Pull完整envelope页，连续seq、page不切消息，客户端先验证完整page/gaps/chain，持久transport cursor与Kernel scientific水位分开；partial/bad page不前进。ACK模型区分RELAY_STORED、DEVICE_RECEIVED、DEVICE_DECRYPTED、KERNEL_APPLIED、SCIENTIFIC_ACCEPTED、ARTIFACT_PRIMARY_DURABLE，后几层是设备声明不是Relay科学裁决；不统一synced=true。未证明安全副本不删ciphertext，本轮只保留retention metadata不GC。

## Checkpoint / rollback 与 snapshot

chain hash绑定previous/seq/envelope hash。可信设备签名checkpoint包含opaque project、membership/key epoch、cursor与chain digest；客户端持久记住最后锚点，回到更旧cursor/checkpoint或同seq异chain即ROLLBACK_DETECTED，不靠wall clock。验证tail须从已锚定chain延续；新设备没有独立锚点时只能信配对authority提供的snapshot/checkpoint。

签名加密snapshot manifest包含project、snapshot cursor、module snapshot hash、state digest、key epoch、creator与签名；只prototype，不做500k bootstrap。完整transparency/gossip/key transparency **NOT IMPLEMENTED**，单设备不能证明Relay未向另一设备split-view或隐藏尚未锚定消息。

## Artifact chunk model

小合成文件分块AES-GCM，每块≤64KiB；AAD绑定project/artifact opaque locator/key epoch/index/total/size与manifest identity。DEK新生成，wrapped DEK及filename/category/run title、总size/SHA在签名且加密manifest内部；Relay只看locator/count/size等必要泄漏。顺序/缺块/重复/坏tag/错总size/digest/epoch全部拒绝，不跳坏块或全文件一次读入。未来10GB使用bounded stream/sink，不接生产MinIO/OPFS。

## TLS、quotas、logging 与 failure behavior

HTTPS-only；临时QA CA和server证书绑定127.0.0.1，client验证CA/hostname，不用verify=False。Relay仅loopback容器端口。QA限额：envelope256KiB、request512KiB、page≤100、chunk64KiB、项目pending ciphertext≤16MiB、pair attempts≤5、请求窗口120/min（scope明确定义）。strict schema、timeout、batch cap；无任意SQL/path/query。

日志仅request ID、opaque scope、status/size/timing/error code，无body/ciphertext/wrapped key/secret。外部错误只稳定code，不泄漏SQL/私钥/原始payload。signature/AEAD/epoch/version失败全部fail closed，无plaintext fallback。

Fault验收使用真实TLS socket、Relay子进程/容器与专用PG：请求半上传/上传后断开、commit前/commit后ACK前kill、ACK丢失、duplicate POST/GET、partial page、乱序retry、Relay/DB实际restart。直接dump PG/持久文件/log搜索全部合成canary与运行时key表示，零命中才能通过隐私gate。

## 前置设计自检与实施序列

### 独立审查后的冻结状态规则

1. Membership transition 以本地已锚定 previous manifest 为授权来源：普通 operation signer 必须是旧状态 ACTIVE owner，不能候选状态自授权。唯一例外 operation=recovery 仅由 bootstrap 时本地已锚定 recovery signing key 授权（不能从候选状态或Relay新增root），同样验证 parent/CAS、membership/key epoch 精确+1；显式绑定新 recipient owner，两公钥/新prefix，新owner ACTIVE、所有旧成员 REVOKED，保留旧成员/prefix历史。previous_digest 必须等于 pinned digest，普通 membership_epoch 精确+1；普通加入 key_epoch 不变，撤销精确+1。公钥不可悄悄替换。并发更新以 expected digest CAS；同 epoch 异 digest 拒绝并报告 MEMBERSHIP_FORK。
2. Recovery kit 除高熵私钥还持久记录可信最新 manifest digest/epochs/checkpoint，并在已验证 transition 后更新。恢复从 kit anchor 验证连续链；最新可信 anchor 丢失时报 RECOVERY_FRESHNESS_UNVERIFIABLE，不用 Relay 交回的“最新”声明替代。全部 key 丢失仍为 E2E_DATA_UNRECOVERABLE。Kit 备份陈旧或全部可信状态回滚不能证明全局 freshness；完整 split-view 仍未解决。
3. 新 push 仅当前 ACTIVE/current epoch；已 durable 存储的历史 epoch envelope 按本地已锚定历史 manifest 验签、链连续后可持久 TRANSPORT_QUARANTINED 并推进外层 cursor，绝不将旧 mutation 送 Kernel。未知历史 authority、坏签名、缺页、坏链不得前进；不能靠 created_at 授权。
4. 客户端整页预验证后，outer receipts/cursor/chain anchor 与 apply_in_session(..., relay_seq=None) 在同一个客户端 QA PG Session/事务提交。任何错误整页 rollback；duplicate wrapper 不消耗 Kernel inner sequence。测客户端 commit 前/后 kill。签名 checkpoint 到达时同时核验本地 cursor/chain，不能覆写未验证 page。
5. Nonce witness/ledger 全部核验和预约在同一 BEGIN IMMEDIATE 锁内。初次仅 explicit new-key registration；已注册 key/prefix 不得被当作首次创建。文件丢失、torn/malformed witness、row丢失或DB/witness任何不一致 fail closed，不忽略坏尾部/清零修复。witness fsync 后 DB commit 前 kill 必须拒绝继续该 key。
6. trusted pairing 的 challenge消费、membership transition、signed grant/wrapped receipt 在同一 trusted-client持久事务内完成；exact retry 返回原 grant，changed recipient/session/role/project 拒绝。撤销后不再提供原 pairing receipt，不重新激活或发新epoch key。Relay保管公开receipt不能代替trusted state事务。

审查 finding：4项P1、2项P2，均在实现前补充；实现与故障测试须逐项验证，不把设计修订当作测试通过。

不改变RH-C14N-1/DAG/科研屏障/权限规则；crypto层与Relay公钥层分开，Base wrapping不冒称Auth，nonce与退回状态明确fail closed，checkpoint局限不夸大。规范与库review先独立复审，再按计划分块TDD：crypto/envelope/nonce → membership/pair/recover/checkpoint/artifact → actualRelay/TLS/fault/privacy → full regression/security review/report。最终八Gate全部PASS才complete，之后STOP；无Sprint3、真实手机、云/VPS/DNS/tunnel或真实科研传输。
