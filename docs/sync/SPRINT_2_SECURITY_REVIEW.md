# Sprint 2 最终独立安全审查

审查日期：2026-10-08。初审基线为 Sprint 1 `334e6c0` 至 RH016 `ada2d8caa9293373b9db2972fc3551ccf746dd6f`，同时检查工作区待提交的 CI 与协议/报告修改。审查者独立阅读需求第0–72节、冻结设计增量和密码库调查，并检查实际实现；不以 Task1/2/3 的既有批准代替本次审查。

**最终独立安全审查结论：APPROVED。未关闭 Critical：无；未关闭 Important：无。** 初审发现1项 Important/P2，经有效 RED、最小修复和本审查者独立复验后关闭。批准范围包括 RH016 及本轮冻结的 PENDING 配对修复、待提交 CI/协议文档。批准时最终全量回归和新 Linux CI 尚未运行；其后 CI 首次失败与最小修复的只读复核见下节。本记录不宣称八项 Gate 或 Sprint 完成。

## RH018 — 首次 Linux CI 失败后的最小修复复核

root 对首次真实 Linux CI 的原始首个调用栈核对结果：全新 checkout 尚无被忽略的 `storage/runtime`，pytest 创建指定 basetemp 时 `Path.mkdir` 不递归建立父目录，触发 `FileNotFoundError`；该轮为14 failed、9 passed、151 errors，尚未进入 Relay 网络测试。这是实际失败，不能记作 crypto 或网络 Gate 成功。本审查者本次读取了 RH018 提交与 workflow 差异，未重复获取远端原始日志；上述首次执行统计由 root 的原始证据核验提供。

独立只读确认 `a1810a1b766489d2fe32f5c06423868c1556547d` 仅修改 workflow 与 CHANGELOG；唯一执行行为变化是在密码/属性测试前增加 `mkdir -p storage/runtime`。路径固定于 checkout 内已有忽略规则覆盖的运行时目录；未增加权限、secrets、网络目标、端口、服务、挂载或访问范围，也未改变密码原语、授权、验签、nonce、测试选择或失败判定。因此该最小修复不改变已批准安全契约，**安全复核 APPROVED**。

该次复核未运行网络或重复整体审计。在该次复核时，修复后的远端 Linux CI 正在重跑，root 的审计后本地完整回归仍在进行；未宣称 RH018 远端 GREEN。其后新增失败与定向复审见下节。

## Linux TLS helper 与 lifecycle 到达点补充审查（已关闭）

RH018 的实际 Linux CI run `37785421799` 随后在 `--init` 阶段报 `QA_DOCKER_START_FAILED`，尚未进入 TLS 网络测试；此前 crypto174/Node48 通过不抵充初始化成功。root/修复者提供的诊断为 Linux UID0 在 cap-drop ALL、仅 CHOWN 时不能读取 host UID 所有的0600 TLS源文件。本审查者随后独立重跑 Docker Linux volume 的非秘密 sentinel 对照，直接验证了该权限边界。

另一个验收缺口是旧 `test_partial_init.py` 只接受通用 `QA_DOCKER_`，较早 helper 故障会使 ingress_create/ingress_connect 案例假通过。修复者记录了有效 RED：两项 earlier-helper 测试 `DID NOT RAISE AssertionError`，见 `SPRINT_2_LINUX_TLS_QA.md`。旧三项通过计数不能单独证明曾到达后两个注入点。本次将初始化可用性及故障证据缺口按 Important/P2 处理；定向修复与独立复验后均关闭。

冻结补丁范围为 runner、partial-init tests、新 Linux sentinel test 与 QA记录。独立只读复核 **ADR-028 APPROVED**：仅短命 TLS复制helper 使用精确 `CHOWN,DAC_READ_SEARCH`；无 DAC_OVERRIDE，仍 network=none、readonly rootfs、no-new-privileges，源仅只读挂载本次TLS server目录、目标仅确切owned TLS卷。cap guard规范化 `CAP_` 前缀后精确比较，缺少或额外cap均拒绝。运行中的Relay和入口保持无CapAdd/cap-drop ALL。实际源只读是权限边界的一部分；不把 sentinel 的“直接写入被拒”夸大成 CHOWN+可写挂载下任何操作都无法改写文件。

本审查者取得独占QA锁后，先用现有guard核对并destroy旧owned Relay/入口/TLS资源，保留原专用PG；随后独立执行：

- `HUB_RELAY_QA=1 pytest tests/secure_relay_lifecycle -q --tb=short -p no:cacheprovider --basetemp storage/runtime/s2-independent-linux-lifecycle`：**6 passed / 59.09s**。三处真实故障要求精确到达点及 START/CREATE/NETWORK 错误；两处更早helper失败负例确认不会假通过。实际Linux volume的 UID1000/0600 sentinel：CHOWN-only读取拒绝，精确双cap读取成功；直接写入拒绝且内容/owner/mode保持，精确卷清理。缺/多cap测试属于inspect公开字段副本的guard检查，未冒称真实容器权限变化。
- `HUB_RELAY_QA=1 python scripts/secure-relay-qa.py --init`：**QA_READY TLS:127.0.0.1:38001 PG:127.0.0.1:35434**。
- `HUB_RELAY_QA=1 pytest tests/secure_relay/test_network.py::test_real_https_ca_hostname_and_plaintext_rejection -q --tb=short -p no:cacheprovider --basetemp storage/runtime/s2-independent-linux-tls`：**1 passed / 8.20s**。
- 只读取 allowlist Docker字段和文件stat，实际确认Relay/入口均 `CapAdd=null, CapDrop=[ALL], User=10001:10001`；`/tls/server.key` mode0600、uid/gid10001。未读取key内容或输出Env。

本次TLS烟测终点privacy v2为0 hits、124,676 bytes、48个模式、1个bytea值；该烟测未生成Device/Project私钥，private inventory为0，因此不拿它替代此前生命周期和完整套件的钥匙保密验证。无秘密统计另存 ignored `storage/runtime/s2-independent-linux-tls-privacy.json`；service run=`5c80b273-1d00-4344-876d-bc53d8774f9a`，trial=`718a2b0c-a079-4a63-826c-b765d30ecd9e`，invocation=`13037bbc-d32a-493a-8586-7978f3348e9a`。

**补充安全复审 APPROVED；未关闭 Critical/Important：无。** QA服务已恢复READY，网络锁已释放。未重复不变的全部密码/内核回归或130项套件；第三次真实Linux完整CI仍待root推送后验证，本机Docker Linux DAC证据不冒称GitHub runner已经GREEN。

## S2-FINAL-01 — PENDING 配对无法完成（Important / P2，已关闭）

位置：`apps/api/researchhub/sync/secure/pairing.py` 的 `consume`，RH016第139行；`packages/secure-sync/src/pairing.ts` 的 `consume`，RH016第98行。

前提：受信 owner 已把设备以 PENDING 加入当前签名 manifest，随后为同一设备、相同 keys/role/prefix 发起正式 pairing challenge。冻结 ADR-026 明确 pairing 例外覆盖未入册及 PENDING recipient，设备生命周期应允许其完成所确认的授权。

缺陷：两种语言一律调用 `transition(..., add=recipient)`，即使 UUID 已在当前 manifest 中。合法 challenge、人工确认和双私钥 possession proof 都通过后，仍因重复 UUID/prefix 报 `PREFIX_OR_DEVICE_COLLISION`，未激活或发出 grant。现有 `test_pending_pairing_exception_is_own_session_only` 只走到 GET/submit，漏掉 trusted consume、Relay complete、recipient unwrap 和 retry。

独立最小复现：随机生成 owner、recipient、kit；bootstrap 并 pin；签名加入 PENDING recipient；用该条目仅把 status 改为 ACTIVE 创建 challenge；recipient 正确 answer；owner consume。Python 和 Node 各自实测均返回 `PREFIX_OR_DEVICE_COLLISION`，Python另核对持久成员仍 PENDING。探针只在 ignored 临时目录运行，未输出随机钥匙。

修复要求：在已验证、同事务锁定的当前 manifest 中区分新设备与已有 PENDING；PENDING 必须完整匹配所确认身份、keys、role、prefix 和历史字段后使用 activation，ACTIVE/REVOKED 或任何不匹配均拒绝。保持 challenge 消费、membership、grant/receipt 同事务；添加两语言与真实 HTTPS 完整路径及篡改/重放/故障负例。不得通过放松唯一性或重新分配既有身份解决。

独立关闭证据：审查冻结补丁确认只在既有同一事务内增加 exact PENDING 身份匹配与 `activate` 分支；新成员仍使用 add，原签名/epoch/唯一性检查未放宽。Python 使用完整 validated member 比较，Node 使用 canonical digest 比较；所有可变数值字段此前已经严格验证，不能用 bool 混同绕过。

本审查者在修复后重新执行原来的随机 Python 和 Node 最小探针，两端均成功完成 reader 激活、独立 HPKE unwrap 与重开存储 exact receipt retry，输出 `PYTHON_ORIGINAL_PENDING_PROBE_GREEN` / `NODE_ORIGINAL_PENDING_PROBE_GREEN`。另独立运行：

- `pytest tests/secure_sync/test_pairing.py tests/secure_sync/test_lifecycle_interop.py -q --tb=short --basetemp storage/runtime/s2-independent-pending-recheck`：**26 passed / 2.64s**。
- 在 `packages/secure-sync` 运行 `node --test --test-isolation=none --test-name-pattern='Node PENDING pairing' test/lifecycle.test.ts`：**10 passed / 610.16ms**。两端覆盖 ACTIVE/REVOKED、role/prefix/两公钥/granted_at 合法签名替换拒绝、before/after commit 异常边界、真实 SQLite INSERT/receipt UPDATE trigger 失败整体回滚；这些是本地事务故障测试，不冒充进程 kill。
- 重新取得独占网络锁，运行 `HUB_RELAY_QA=1 pytest tests/secure_relay/test_security.py::test_pending_pairing_exception_is_own_session_only -q --tb=short -p no:cacheprovider --basetemp storage/runtime/s2-independent-pending-network`：**1 passed / 8.28s**。完整真实 HTTPS challenge→submit→trusted consume→complete→receipt/grant→客户端 unwrap；reader 激活前不能 pull、之后可 pull，但不能 push 或修改 membership。

修复复验终点实际 privacy v2 **0 hits**：9项私密库存、105个编码模式、169,295 bytes、19个 bytea 值。仅统计备份 `storage/runtime/s2-independent-pending-privacy.json`；trial=`b0fecc24-814e-49d2-987d-4944174dd20e`，invocation=`69be0210-3e29-4b21-93e9-b5b8124899c9`。与原独立审计样本分别保留，不混用。Finding 已关闭，无新增 Critical/Important；网络独占锁在复验后释放。

## 独立检查与实际证据

| 范围 | 本次检查 / 结果 |
|---|---|
| Crypto / wire | 检查两端库调用、HPKE fresh one-shot、固定套件/版本、exact schema、canonical 编码、签名和完整 AAD、decrypt 后语义 digest/project/device/dependency 绑定。无额外 Critical/Important。 |
| Nonce | 检查 Python/Node 同格式 SQLite BEGIN IMMEDIATE、witness fsync 在 commit 前、完整 witness/ledger 一致性、prefix 历史、溢出拒绝与完整可信材料共同回滚限制。实际测试含六个跨语言进程120次预约及四个真实进程退出窗口。 |
| Lifecycle / anchors | 检查 bootstrap roots、全 manifest 历史和索引绑定、grant 验签先于 unwrap、revoke 双 epoch、recovery kit journal/head 与 checkpoint 同事务、持久旧 checkpoint 重新验签；发现上述 PENDING 完成缺口。 |
| Relay / replay / errors | 检查实际项目行锁、current auth 在 cache 前、固定原 GET response、缓存预算预留、同消息 exact retry、nonce unique、sync_commit 后 ACK、signed public metadata、rate/size/page/quota、错误 allowlist 与日志不反射内容。 |
| Trusted receive | 检查固定 verified TLS、immutable outbox、整页预验证、current trust 行锁、历史隔离、Kernel 与 outer receipt/cursor/checkpoint 同 Session、principal/有限 HumanGrant 双认证、无 scientific ACK 推断。审查真实 client kill 测试与生成 schedules。 |
| Artifact | 检查双端 fresh DEK、AES-KW 内层签名加密 manifest、chunk AAD/context、strict sizes/order/count/hash/epoch、staging abort、exact retry 不重复写入；1MiB 合成 prototype 边界明确。 |
| QA 隔离 / CI | 检查显式 opt-in、35434 Relay/35433 client 的专用 DB/role、实际服务器 identity、容器/network/ports/mounts/privileges 与确切 ID 清理、public-only image、TLS passthrough 固定目标。CI 静态包含4 jobs、临时隔离服务、两语言测试、实际 Relay runner、always destroy；真实 Linux 执行仍待完成。 |
| 仓库秘密 | 对99个相对 Sprint1 变更文件做私钥头/常见 token 形状扫描，0命中；公开 fixed 向量明确 TEST ONLY，runtime/storage/env 忽略规则与 Docker context 排除规则已检查。此为有边界的模式检查，不是任意秘密检测保证；最终暂存区须由 root 另核对。 |

实际独立本地命令：

```text
.venv/Scripts/python -m pytest tests/secure_sync/test_nonce.py tests/secure_sync/test_properties.py tests/secure_sync/test_recovery_anchors.py tests/secure_sync/test_pairing.py tests/secure_sync/test_history_integrity.py -q --tb=short --basetemp storage/runtime/s2-security-independent-elevated
```

结果：**55 passed / 11.31s**。此前受限进程的临时目录 ACL 导致 PermissionError，属于环境失败；在允许的提升权限下重跑才取得以上结果，不把失败算作产品 RED。

经 root 授予独占网络锁后，实际运行以下针对性审计（结束后已释放锁）：

```text
HUB_RELAY_QA=1
.venv/Scripts/python -m pytest tests/secure_relay/test_review_regressions.py tests/secure_relay/test_security.py::test_every_proof_field_is_bound tests/secure_relay/test_security.py::test_expired_revoked_epoch_requests_rejected_before_cache tests/secure_relay/test_security.py::test_recovery_is_pinned_profile_and_cannot_read_messages tests/secure_relay/test_security.py::test_unauthenticated_malformed_pairing_body_has_no_existence_oracle -q --tb=short -p no:cacheprovider --basetemp storage/runtime/s2-independent-network-review
```

结果：**21 passed / 65.25s**。其中真实专用 PG bytea 阳性对照覆盖 canary/随机32-byte sentinel 的 raw、hex大小写、标准base64有/无padding、URL base64有/无padding，共14种表示；均实际触发扫描拒绝，逐项精确清理。签名 query bool/整数和 chunk numeric 类型负例核对无 receipt/quota 变更。

终点 privacy v2 的直接 pg_dump、driver 解码实际 bytea、Relay/入口文件和日志检查为 **0 hits**：114项 private inventory、8项 canary、809个编码模式、288,738 bytes、11个 bytea 列、73个值、53,020个解码 bytea bytes。仅无秘密聚合统计备份为 ignored `storage/runtime/s2-independent-security-privacy.json`；service run=`24804e63-c77e-41fa-b34c-68b0809031a0`，trial=`85ae4cb0-7385-4a6c-9e2d-8c0ccdb83c7e`，invocation=`f47e342d-83c2-4e6a-8432-4a62948a1dc3`。这些是本次定向样本，不能冒称完整130项网络套件或最终所有 gate 回归。

## 边界

全程 QA ONLY / SYNTHETIC / LOCAL LOOPBACK；未触碰个人 native-env、生产数据库/MinIO、真实研究数据、UI、部署、main/tag 或仓库可见性。审查未修改行为代码或 Git，只写本审查记录及 ignored 合成测试证据。

完整可信本地材料一致回滚、恶意可信 endpoint、历史已知明文回收、可用性/隐藏未锚定更新、完整 split-view/key transparency、生产 keystore、真实浏览器 vault/user-presence 均不由本次审查解决。最终 gate 需在 finding 关闭并独立批准后，由 root 重跑要求的完整回归及真实新 CI。
