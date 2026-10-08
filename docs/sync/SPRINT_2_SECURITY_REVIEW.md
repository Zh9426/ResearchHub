# Sprint 2 最终独立安全审查

审查日期：2026-10-08。初审基线为 Sprint 1 `334e6c0` 至 RH016 `ada2d8caa9293373b9db2972fc3551ccf746dd6f`，同时检查工作区待提交的 CI 与协议/报告修改。审查者独立阅读需求第0–72节、冻结设计增量和密码库调查，并检查实际实现；不以 Task1/2/3 的既有批准代替本次审查。

**最终独立安全审查结论：APPROVED。未关闭 Critical：无；未关闭 Important：无。** 初审发现1项 Important/P2，经有效 RED、最小修复和本审查者独立复验后关闭。批准范围包括 RH016 及本轮冻结的 PENDING 配对修复、待提交 CI/协议文档。最终全量回归和新 Linux CI 尚未运行，本记录不宣称八项 Gate 或 Sprint 完成。

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
