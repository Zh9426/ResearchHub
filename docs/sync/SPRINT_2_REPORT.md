# Research Hub v0.3 Sprint 2 — Secure Relay & E2E Transport

状态：Sprint 2 验收完成，八项 Gate 全部 PASS。QA ONLY / SYNTHETIC DATA ONLY / LOCAL LOOPBACK ONLY。已停止，等待人工审查，不开始 Sprint 3。

分支 `codex/researchhub-v0.3`；Sprint1基线334e6c0，冻结main/v0.2.0为4a4db4a。仓库保持用户指定Public，运行时科研内容与凭据不入Git。

## 八项 Gate

以下PASS仅适用于声明的合成QA、支持的进程并发/重启模型与可信锚点边界；不表示生产就绪、完整split-view或硬件故障域保障。最终独立安全审查及补丁复审APPROVED，审查后的本地回归与四job Linux CI均成功。Sprint 2 overall = **PASS**。

| Gate | 结果 | 验收证据 |
|---|---|---|
| Crypto Interoperability | PASS | Python174 / Node48、独立固定canonical/AES/Ed/HPKE/AESKW及lifecycle/chunk双向；本地与Linux实际通过 |
| Relay Confidentiality | PASS | 直接dump/所有bytea原值/文件日志七编码扫描，14真实泄漏正对照；完整两cohort均0 hits |
| Envelope Integrity | PASS | 完整header/AAD/ciphertext/digest/signature负例；HTTP与客户端整页失败不进入Kernel或推进cursor |
| Replay & Epoch Safety | PASS | immutable outbox/原receipt、fresh current authorization、双epoch/nonce拒绝、跨wrapper科学幂等 |
| Device Lifecycle | PASS | pair/grant/PENDING激活/revoke/rotate/recover；独立双端及实际HTTPS完整链，身份替换与事务失败负例 |
| Network Durability | PASS | 真实TLS断流及Relay/PG/入口/client强制退出，PG原子提交、ACK重试与无重复Audit；本地55+75、Linux55+75 |
| Nonce Safety | PASS | 两语言真实并发/重启/四个退出窗口、持久ledger/witness损坏/丢失/回滚和overflow拒绝 |
| Rollback Detection | PASS | 持久signed checkpoint每次验签、双epoch/chain/cursor单调、gap/旧位置/未消费远端位置拒绝 |

## 1. Selected crypto libraries

IMPLEMENTED IN SECURE QA：Python cryptography50.0.2；Node WebCrypto与@hpke/core1.9.0，锁定common1.10.1。详细官方来源、公告与选择边界见CRYPTO_LIBRARY_REVIEW.md。Library gate SELECTED；不声称整个协议获外部密码审计。

## 2. Crypto suite

`RH-v1/AES256GCM/Ed25519/HPKE-X25519-HKDFSHA256-AES256GCM`。标准AES256GCM正文、Ed25519签名、RFC9180 Base HPKE分发Project Key、AESKW包裹Artifact DEK。无自研primitive。

## 3. SecureEnvelope

IMPLEMENTED IN SECURE QA：严格RH-C14N-1、exact字段、UUID/安全整数/编码/版本/大小校验；transaction解密后重验semantic digest及可信project/device/dependencies映射。详见SYNC_SECURE_ENVELOPE.md。

## 4. Signature preimage

`ResearchHub/SecureEnvelope/v1\0 || canonical(envelope_without_signature)`，覆盖完整header、ciphertext及digest。

## 5. AEAD / AAD

`ResearchHub/AEAD/v1\0 || canonical(header)`；ct||16byte tag；严格unpadded base64url。坏tag/错误钥匙/字段替换fail closed，plaintext parser失败统一INVALID_PLAINTEXT。

## 6. Nonce strategy

IMPLEMENTED IN SECURE QA：4byte authority prefix +8byte计数；SQLite FULL/BEGIN IMMEDIATE锁内验证ledger/anchor/witness，fsync witness→commit→return→encrypt。真实六进程120unique与restart121/122；两端四个强制退出窗口、九种损坏/回滚拒绝。全部可信材料同时恶意回滚不能由本地ledger证明，备份恢复必须rotate。网络exact retry必须使用缓存完整bytes。

## 7. Device keys

IMPLEMENTED IN SECURE QA：CSPRNG稳定UUID与独立Ed25519/X25519 seeds，内存与明确UNPROTECTED TEST ONLY SQLite DeviceKeyStore。文件store仅resolved ignored runtime/systemtmp；secret repr/Node JSON隐藏。真实生产vault、hardware key、browser导入保护 NOT IMPLEMENTED。

## 8. Project keys

IMPLEMENTED IN SECURE QA：每project/epoch独立随机32byte key，普通密码不参与KDF；完整authority-signed grant先验scope再标准HPKE unwrap。每Artifact独立DEK，wrapped DEK仅在加密manifest。生产durable key-store transaction尚未实施，QA revoke失败后的孤立epoch key不复用。

## 9. Membership epochs

IMPLEMENTED IN SECURE QA：完整signed manifest、独立pin bootstrap roots与连续history、旧ACTIVE owner授权/CAS精确+1、sameepoch异digest fork、PENDING/ACTIVE/REVOKED和owner/writer/reader边界。历史members/prefix不能删，永久uint32 prefix唯一递增，溢出拒绝；candidate不能自授权。详见SYNC_KEY_LIFECYCLE。

## 10. Key epochs

IMPLEMENTED IN SECURE QA：加入保持key epoch；revoke/recovery双epoch精确+1。实际网络拒绝旧epoch新push；客户端对已存历史消息重新验证已pin完整manifest、签名、AEAD和chain后仅TRANSPORT_QUARANTINED，不送Kernel。未知history或缺历史key失败且cursor不前进。

## 11. Pairing

IMPLEMENTED IN SECURE QA / CROSS-LANGUAGE VERIFIED：5分钟、单session、最多5次持久失败，签名challenge绑定两公钥/fingerprint/SAS/project/role/当前manifest，Ed proof与标准HPKE随机挑战证明X私钥持有。trusted-client同SQLite事务消费challenge、变更membership、保存wrapped grant receipt；第二次consume拒绝，exact lookup独立，撤销后不再发key。Relay公共配对存储、过期/滥用/未认证畸形请求已通过真实TLS验证；QA文本确认不等于真实user presence。

## 12. Revocation

IMPLEMENTED IN SECURE QA：A/B active后撤销B，fresh key仅给仍ACTIVE设备，后加入C获授权futurekey；B旧key不能解新epoch、无新grant，不能凭旧pairingreceipt重新激活。Python/Node独立验证。实际Relay当前权限检查先于缓存读取，撤销设备不能利用旧receipt。已持有的历史plaintext/key不能回收。

## 13. Recovery

IMPLEMENTED IN SECURE QA / CROSS-LANGUAGE VERIFIED：高熵Kit signing/recipient材料与bootstrap pinned root，authority-signed HPKE RecoveryBackup先验当前完整manifest/checkpoint组合再unwrap；recovery保留并撤销旧members，新owner/newprefix、双epochs+1，无server master或password-reset key恢复。

公共Kit metadata journal与latest head同SQLite持久，显式restore仅加载以前本地提交的完整组合并重验根、UUID/project、history、每个signed checkpoint/progress rows/head。真实子进程重开并恢复cp1/backup/recovery已由独立spec验证。seed-only/metadata丢失报RECOVERY_FRESHNESS_UNVERIFIABLE；所有设备私钥+Kit丢失报E2E_DATA_UNRECOVERABLE。manifest/cp/journal/head同事务，commit后更新内存，真实SQLite COMMIT失败也整体rollback。全可信锚点一致恶意回滚仍不可由本地记录自证；生产encrypted Kit export/restore UX尚未实施。

## 14. Relay implementation

IMPLEMENTED / NETWORK VERIFIED IN SYNTHETIC QA：非root Relay、固定TCP入口和独立PostgreSQL已实际运行。Relay仅internal data网；PG/入口仅data及transport两条QA网，发布仅127.0.0.1:35434/38001，精确ID、实际网络成员、mounts、UID/caps/read-only/resource limits全部guard。镜像应用仅公共wire/验签和密文存储，无Domain/client AEAD/vault。Task3A/3B各自spec PASS、quality APPROVED；完整最终安全审查亦APPROVED。详见Task3A/3B QA及SPRINT_2_SECURITY_REVIEW.md。

## 15. Relay DB privacy

NETWORK VERIFIED IN SYNTHETIC QA：v2统一canary/private的raw、hex大小写、base64及base64url有无padding，直接pg_dump加driver解码所有实际BYTEA原值，扫描Relay/入口应用、挂载文件及stdout/stderr。14个真实PG泄漏正对照均必须检出并精确清理；旧v1零命中不作为证据。root最终完整两cohort分别扫描98,143,940/4,733,490 bytes，private inventory289/252，hits均0；Linux完整runner也通过同一审计与完整证据核验。仅TLS server key和专用PG服务口令有明确服务用途例外，无E2E主密钥或私钥例外。

## 16. HTTPS QA

NETWORK VERIFIED IN SYNTHETIC QA：实际正确CA/SAN handshake先成功，再验证wrong CA与hostname导致证书验证异常；明文HTTP不能成功。TLS直达Relay，入口不终止TLS；server key0600/UID10001可读，临时CA private仅签发进程内存。没有verify=False或公网监听。

2026-10-08续跑时Docker Desktop引擎曾停止；使用已安装官方CLI `docker desktop start --detach`恢复。保留原QA容器和卷，严格核验原S1 PG身份/配置后启动；Relay通过`--start`及`--status`确认既定隔离拓扑。未更改Docker全局配置或手工重启/删除个人服务。引擎可用性检查不是HTTPS网络验收。

## 17. Replay handling

Relay侧已真实验证：同messageID同完整bytes返回原durable receipt，异bytes/新ID复用nonce拒绝；current会员/双epoch/签名先于任何cache，第一次GET含EMPTY的响应持久不可变；失效proof不能利用旧receipt绕过撤销，新freshproof可重试同业务消息。独立response cache有8MiB预算，满时执行前拒绝。客户端PG不可变outbox重试不再加密/预约nonce；新wrapper可推进outer sequence，但相同semantic transaction不重复Kernel Audit/revision。

## 18. Durable ACK

Relay完整cipher/seq/chain/quota/原receipt在sync_commit事务内提交后才RELAY_STORED，实际提交前/提交后ACK前SIGKILL验证完整性与重试receipt。客户端预验证整页后，在同一PG Session提交Kernel结果、outer receipt/cursor/chain和签名checkpoint；ACK仅允许已持久receipt，当前客户端发送DEVICE_DECRYPTED，不自动声明SCIENTIFIC_ACCEPTED。Device签名与本地registered principal/mock fresh HumanGrant分别验证。

## 19. Restart recovery

已实际覆盖Relay/PG/入口强制退出与重启、半/全上传后断开、commit前和commit后ACK前kill，核验PG完整保存或整体未写入、samebytes原receipt。客户端Popen子进程也在两个精确barrier被kill：两条交易页提交前全部为0，提交后ACK前全部为2；重试Audit仍为2。三种部分初始化失败均journal精确清理且保留原PG。进程故障证据不等于硬件断电或多故障域耐久性。

## 20. Checkpoint rollback detection

持久旧SIGNED anchor缺真实验签的P2已修复并独立复审关闭：严格公共验证上下文与body/kind同事务，每次读取先验签再核digest，局部损坏无覆盖。两语言各11类spec损坏探针、各22个quality额外负例通过；Task3B另验证PG持久checkpoint的签名、project、双epoch、cursor/chain和历史creator。最终整体安全审查及其后完整回归通过，本Gate在上述有限威胁模型内PASS。

IMPLEMENTED IN SECURE QA：严格signed checkpoint、SQLite及PG monotone anchor，chain=SHAcanonical(previous_digest,sequence,envelope_digest)，cursor0必须zero64，每页<=100。oldercursor、samecursor异chain、缺页、坏签名/context均拒绝；Kit最新组合持久恢复及局部metadata损坏负例通过。远端checkpoint必须等于已验证本地位置，不能用它跳过消息。完整split-view/gossip/key transparency NOT IMPLEMENTED。

## 21. Artifact crypto prototype

IMPLEMENTED IN SECURE QA / CROSS-LANGUAGE VERIFIED：<=1MiB、最多16个1..64KiB chunk，fresh DEK+AESKW位于signed encrypted manifest；filename/category/run_title均加密，chunk AAD绑定project/locator/epoch/index/total/size/manifestidentity。错序/缺块/重复/tag/hash/size/epoch或合法auth下bool schema均abort无READY，exactretry零write。signed encrypted snapshot prototype也独立互通，仅验证manifest/state/module/hash/cursor/creator绑定。生产MinIO/OPFS、10GB/全量bootstrap NOT IMPLEMENTED。

## 22. Cross-language results

CROSS-LANGUAGE VERIFIED：两端固定完整canonical transaction/envelope逐字节一致，AES/Ed/HPKE/AESKW独立双向；另覆盖grants/recoverybackup/snapshot/chunks。最终Python secure174与Node48/typecheck均在Windows本地和真实Linux CI通过，包含PENDING修复；TLS材料单测不冒充网络验收。Sprint1独立wire/科学语义向量及Node7项保持通过。

## 23. Fault injection

Task1 nonce真实process.exit/os._exit证据及Task3A真实Relay/PG/入口SIGKILL、TLS断流、持久限额/receipt故障回归均通过。主机只通过精确owned容器ID与固定marker控制故障，没有远程HTTP fault入口。Task3B增加client真实kill、整页乱序/partial/gap/晚Kernel失败全部回滚、重复页/新wrapper幂等和实际HTTPS Hypothesis schedules；runner/响应流边界单元探针单独标注。

## 24. CI

四job最终实现验收 **completed / success**，对应RH019 `982c6efa02bac9d998d4672da1c2b1b1d206fe99`：[Actions37787853895](https://github.com/Zh9426/ResearchHub/actions/runs/37787853895)。`backend-mcp-migration`、`frontend`、`sync-kernel-qa`、新增`secure-relay-qa`逐项均success，后者always清理步骤也success。

Linux安全job实测：Python **174 passed/12.55s**，Node **48 passed/0 failed/0 skipped**、typecheck通过；严格注入点与DAC sentinel **6 passed/30.20s**；实际初始化QA_READY；Relay **55 passed/170.73s**，client **75 passed/25.16s**。完整runner要求两组JUnit/collection/独立privacy v2证据一致，无skip/deselection/遗漏文件或0测试；CLI exit0后精确owned清理成功。所有科研key均临时随机生成，没有仓库secret作Project Key。

两次失败如实保留：[RH017缺临时父目录](https://github.com/Zh9426/ResearchHub/actions/runs/37785004309)、[RH018 Linux TLS helper权限](https://github.com/Zh9426/ResearchHub/actions/runs/37785421799)。这两次不计通过；经最小修复及独立复审后才取得上述成功。最终文档提交没有行为变更，其精确HEAD远端SHA/CI仍由提交后的只读核验确认，不引用其他提交冒充。

## 25. Performance

Task1实际100×1KiB本地seal均值8.566ms、open1.007ms、verify0.636ms，含SQLite/witness fsync。Python3.12.4/Windows实际10轮128KiB Artifact（2×64KiB）完整本地seal/open：seal均值29.792ms、中位29.780ms；open均值37.635ms、中位37.556ms，每轮重验READY与全部plaintext一致。这是本地测量，不是HTTP/Relay/PG延时。

Task3B最终实现者样本（trial fd0264c6-b98e-40dc-90e5-ce61544a614f）：Windows11 10.0.22631、Intel64 Family6 Model151 Stepping2、Python3.12.4和本机Docker；100条envelope共228800 canonical bytes。100次真实push共2.765s、均值27.653ms、p95 30.218ms；100次真实pull共2.363s、均值23.631ms、p95 27.838ms。随后PG apply 3.907s单列，不混入pull。128KiB（4×32KiB）Artifact seal39.078ms、网络及本地准备350.708ms、open37.903ms；实际manifest push/pull各1，chunk各4。该单机顺序样本不承诺分布式吞吐，也不代表Kernel科学接受或Primary持久化。

root审查后完整trial `522b7359-ae1a-4835-93da-cb87db344c17`再次实际测量：相同100条/228800 bytes，push2.990s（均值29.903ms、p95 34.913ms），pull2.537s（均值25.371ms、p95 30.444ms），之后client PG apply4.302s。128KiB四块Artifact seal38.812ms、网络及本地outbox准备323.012ms、open38.451ms；120 rolling device limit保持不变。独立统计位于ignored secure-client-performance.json及secure-client-artifact-performance.json；仍为单机顺序样本。

## 26. Known limitations

QA ONLY / SYNTHETIC ONLY / LOCAL LOOPBACK ONLY。公开fixed TEST ONLY keys不是运行时身份。真实浏览器vault、hardware-backed keys、real user-presence、全量snapshot/bootstrap、GC/compaction NOT IMPLEMENTED。

## 27. Threats not solved

E2E不能解决trusted endpoint compromise、XSS、malware读取明文、用户主动分享明文、DoS、Relay丢弃所有消息以及撤销设备已持有的历史明文。完整split-view/key transparency NOT IMPLEMENTED。未锚定消息隐藏/所有可信本地状态同时回滚不可从单设备anchor证明。

## 28. Existing Sprint 1 regression

以下均在最终独立安全审查APPROVED后执行，使用当前实现与独立QA服务，不复用旧数量作为当前验收。

| 本地最终回归 | 结果 |
|---|---|
| Sprint0 prototype + Python secure | 208 passed/27.76s，分别34与174；包含真实nonce子进程/跨语言/属性及TLS材料测试 |
| backend/MCP/release | 137 passed/114.34s；4项既有依赖或恶意ZIP测试警告，无失败 |
| Node secure-sync / typecheck | 48 passed / PASS |
| Node sync-protocol / typecheck | 7 passed / PASS |
| frontend / typecheck | 46 passed/14.54s / PASS；Vite配置兼容性提示保留，不影响结果 |
| 隔离Docker production build | PASS，实际重新执行Next编译/类型/静态页，镜像researchhub-s2-final-web:qa；未操作个人运行中的前端 |
| v0.2真实API/PG/MinIO及并发 | 21 passed/16.43s，仅127.0.0.1:38000/35432/39000合成QA |
| Sprint1 Python vectors/kernel/实际PG | 149 passed/23.62s，17固定向量+7纯内核+125实际PG；显式HUB_SYNC_QA=1、仅35433 |
| v0.2实际备份恢复/重启 | 备份恢复1 passed/4.49s，恢复至新QA DB/bucket并校验表计数/Artifact checksum；仅QA四服务重启后1 passed/0.56s |
| Relay部分初始化清理 | root原3 passed/33.64s；Linux修复后最终6 passed/30.20s，额外验证故障到达点与DAC sentinel，精确owned清理 |
| 完整Relay/client两cohort | Relay55 passed/270.91s，client75 passed/41.71s；完整130项无fail/error/skip/deselection、privacy0/0 |

命令与JUnit统计保留于ignored `storage/runtime/s2-final-*.xml`；未上传原始DB、日志、keys或科研数据。backend单元测试中的TestClient不算真实服务验收；真实服务证据独立列出。

上述本地全集在PENDING最终审查后执行。其后仅TLS QA helper及lifecycle证据修复；该补丁再次独立APPROVED后，root补跑非CI部分：Sprint0 **34 passed/4.00s**，v0.2实际服务 **21 passed/17.31s**，备份恢复 **1 passed/3.96s**，四QA服务重启后 **1 passed/0.63s**。其余密码/Node/安全网络/Sprint1/backend/frontend由修复后的四job LinuxCI重新执行；结果见第24节。

本轮完整两cohort的service run=`5ba43eff-44a3-42c4-92d9-dc124cfa687e`、trial=`522b7359-ae1a-4835-93da-cb87db344c17`。root交叉核验实际aggregate/collection/privacy/JUnit：Relay289项私密库存/1908模式/98,143,940 scanned bytes，client252项/1680模式/4,733,490 bytes，hits均0。分别11个bytea列、866/867值、32,632,800/1,495,832 driver-decoded bytes。唯一索引保存在ignored `storage/runtime/secure-relay-suite-result-<run>-<trial>.json`。

实际主命令（PowerShell，仓库根；所有服务先通过隔离guard，不能指向个人环境）：

```powershell
$env:HUB_RELAY_QA='1'
$env:HUB_SYNC_QA='1'
.venv/Scripts/python.exe scripts/secure-relay-qa.py --destroy
.venv/Scripts/python.exe -m pytest tests/secure_relay_lifecycle -q --tb=short --basetemp storage/runtime/s2-final-lifecycle
.venv/Scripts/python.exe scripts/secure-relay-qa.py --init
.venv/Scripts/python.exe scripts/secure-relay-qa.py --test
.venv/Scripts/python.exe -m pytest tests/sync_prototype tests/secure_sync -q --tb=short --basetemp storage/runtime/s2-final-pure
.venv/Scripts/python.exe -m pytest tests/sync_vectors tests/sync_kernel tests/sync_pg -q --tb=short --basetemp storage/runtime/s2-final-s1
.venv/Scripts/python.exe -m pytest tests/backend tests/mcp tests/release -q --tb=short --basetemp storage/runtime/s2-final-backend
npm --prefix packages/secure-sync test
npm --prefix packages/secure-sync run typecheck
npm --prefix packages/sync-protocol test
npm --prefix packages/sync-protocol run typecheck
npm --prefix apps/web test
npm --prefix apps/web run typecheck
docker build -f infrastructure/docker/web.Dockerfile -t researchhub-s2-final-web:qa .
```

v0.2实际测试显式设置HUB_LIVE_URL为`http://127.0.0.1:38000`、HUB_QA_CREDENTIALS_FILE为ignored `storage/runtime/docker-qa-credentials.json`、HUB_COMPOSE_RECOVERY=1；运行`tests/integration/test_live_*.py`与`test_pg_concurrency.py`。备份前仅停止Compose项目`researchhub-v02-qa`的api/web写服务，执行`test_compose_recovery.py`后恢复；重启该项目db/minio/api/web并等待healthy后，以HUB_CHECK_RESTART=1运行`test_persistence.py`。整个过程未读取个人native-env、运行生产migration或操作个人服务。

## 29. Security review findings

最终独立全系统审查及随后PENDING/Linux补丁复审均 **APPROVED**，无未关闭Critical/Important。不是以测试数量代替审查结论；完整证据见[独立安全审查](SPRINT_2_SECURITY_REVIEW.md)。修复后的完整LinuxCI已成功，详见第24节。

| 阶段 | 发现与处理 | 验证/边界 |
|---|---|---|
| 安全设计 | 六项授权/HTTP契约缺口修订，冻结recovery唯一授权例外与严格request proof | 独立设计PASS，见SECURITY_DELTA与ADR016–028 |
| Task1 | 补固定canonical transaction向量，收敛plaintext parser错误信息 | 有效RED→GREEN、双端互操作、spec与quality通过 |
| Task2 | 恢复缺少最新checkpoint组合、Kit锚点丢失可重新初始化、跨项目恢复链、journal/head只在内存、失败后部分提交等 | 持久公共journal/head与事务提交；真实子进程及SQLite COMMIT失败负例；双端独立复审 |
| Task2 | manifest索引与签名历史不一致、checkpoint epoch可回退、持久旧checkpoint未重新验签、bool/genesis schema混同 | 全历史复验、公共验证上下文、每次读真实验签、严格数值；两端各11类spec及22类quality额外探针通过 |
| Task3A | privacy只扩展private编码、pg_dump bytea外层使已编码秘密漏检；chunk/query bool可混同整数 | canary/private统一七种表示，直接dump加driver解码全部实际bytea；14种真实PG泄漏对照；strict type/canonical绑定。三项均独立复现并关闭 |
| Task3B | PYTEST_ADDOPTS筛选可假报完整通过；httpx iter_bytes重聚合延迟body deadline检查 | 子进程清筛选、collection/JUnit/文件集/唯一context交叉核验；iter_raw及EOF检查。原独立探针均GREEN，时间界限如文档所述 |
| 最终审计 | 已登记PENDING设备合法proof后仍走add导致身份冲突 | Python/Node保持完整身份只激活status，保留原子性；原双端探针、Python配对interop26、Node负例/原子性10、实际HTTPS完整链1独立复验通过，见PENDING_PAIRING_QA |
| LinuxCI首次 | 全新checkout无ignored storage/runtime，pytest无法创建basetemp | 真实14 failed/9 passed/151 errors，不计成功；RH018先mkdir -p，静态最小修复经独立复核 |
| LinuxCI再次 | helper仅CHOWN无法读host-owned 0600 key；lifecycle可把早期错误误当稍后注入 | 非秘密Linux sentinel有效RED；仅离线短命helper增加DAC_READ_SEARCH，运行服务无额外cap；注入点与错误码精确验证。独立6 lifecycle/sentinel、初始化QA_READY、实际TLS1通过，见LINUX_TLS_QA |

最终审查另外独立执行55项本地安全测试和21项真实HTTPS/PG定向检查，包含14个泄漏正对照；定向privacy0。修复后PENDING配对独立privacy0及TLS烟测0均仅代表各自样本，不能替代完整两cohort运行时密钥库存扫描。Linux烟测未生成Device/Project钥匙，private inventory=0已经明确记录。

曾出现的两次诊断泄漏也保留为已发生事件：一次Docker inspect输出专用QA PG服务密码，后续已轮换且实际新密码成功/旧密码拒绝；旧无效bootstrap值仍在原PG容器环境，不能声称消除全部历史副本。另一次失败pytest审计回溯显示该轮临时合成Device/Project/Recovery材料列表；已改redacted inventory/固定错误码，清确切QA授权后用新随机材料重跑，验证旧项目行不存在及外部新签名请求401。未涉及个人科研密钥；没有把缩短回溯或旧v1零命中当修复证据，也没有将秘密值写入本报告/Git。详细前因、失败计数和验证在Task3A QA记录中。

仓库检查：各阶段聚焦暂存并做私钥头/token形状扫描，最终审计另检查相对Sprint1的99个文件；root精确扫描三份实际QA服务凭据，均零命中。公开固定向量仅TEST ONLY；CI口令仅明确公开的可销毁测试服务配置，不是科研key。模式扫描有范围限制，不宣称能识别任意秘密。

## 30. Proposed Sprint 3 scope

DESIGNED ONLY：人工审查通过后可另行规划真实client/vault/presence及移动接入；当前不启动Sprint3，不做生产migration、真实科研同步、手机/公网部署或ChatGPT Remote MCP。

## 验收映射与停止点

以下为已通过最终独立安全审查及其后回归的合成QA证据映射，最终计数和Linux证据见第24、28节。

| Case | 验证目标 | 当前证据 / 待办 |
|---|---|---|
| A / B | Python与Node互相加解密 | 固定向量与独立双向interop；最终Python174/Node48通过 |
| C / D | Python与Node互相验签 | 双端独立实现与完整最终回归通过 |
| E / F / G / H | ciphertext、AAD project、semantic digest、signature篡改 | 双端严格负例及Task3实际HTTP/客户端整页拒绝，cursor不前进 |
| I | 错误recipient不能unwrap | 双端HPKE grant负例通过 |
| J / K / L | 正常配对、重放、过期 | Task2可信客户端与Task3 Relay公共转发/配对滥用真实TLS验证 |
| M | 撤销设备不能submit | Task2全历史授权及Task3A真实Relay旧epoch/撤销请求拒绝通过 |
| N | 撤销设备不能解新epoch | 双端fresh key/revoke负例通过 |
| O | 已知历史明文无法收回 | 明确限制，见第12、27节 |
| P | 重加密保留semantic revision | Task1双端wrapper语义及Task3B实际PG Kernel去重，Audit/revision不重复 |
| Q / R | 重复push同receipt、同ID异内容拒绝 | Task3A实际HTTP/PostgreSQL原receipt/碰撞负例通过 |
| S / T / U | commit前kill、ACK丢失、重启持久 | 实际Relay/PG/入口及client事务前后kill、retry原receipt与无重复Audit |
| V | cursor gap检测 | 完整page预验证、partial/gap拒绝；晚Kernel失败全页回滚 |
| W | checkpoint回退检测 | 双端本地与PG持久CP每次验签/双epoch/chain回退负例；远端CP不能越过本地消费位置 |
| X / Y | Relay DB/files/log明文与钥匙0命中 | 最终两cohort完整私密库存扫描0/0，14泄漏对照通过；Linux相同runner通过 |
| Z | Artifact篡改、错序、缺块 | 双端prototype、真实opaque chunk网络属性与128KiB实际TLS roundtrip/独立open |

额外案例：nonce重启/并发/损坏有Task1真实多进程证据；rotation、wrong epoch、unsupported suite、downgrade、malformed、recovery/total loss、snapshot signature有双端回归。实际HTTP oversized/rate/pairing abuse、网络Hypothesis和客户端真实kill均通过。最终独立安全审查、其后回归及四job CI通过；当前停止于Sprint2，等待人工审查。

Research Hub v0.3 Sprint 2 — Secure Relay & E2E Transport complete.
