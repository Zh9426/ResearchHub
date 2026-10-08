# Sprint 2 Task 2 — Lifecycle / Pairing / Checkpoint / Small Artifact QA

状态：实现工人交接独立 specification review；不能据此标记 Sprint 2 complete 或八项 Gate 全 PASS。2026-10-08，LOCAL / SYNTHETIC / TEST ONLY。

## 实际实现边界

纯公共 Python `packages/secure_wire/membership.py` / `checkpoint.py` 不导入 client、Domain、private-key 或 AEAD。trusted-client Python/独立 Node 实现 device/project keys、pinned full signed membership、grant、dual-key possession pairing、fresh-key revocation、anchored HPKE recovery backup、kit recovery、新旧 envelope authority分类、monotone checkpoint、signed encrypted snapshot，以及最大1MiB多chunk Artifact staging。

详细 exact schema / signature domain / API /诚实限制见 `SYNC_KEY_LIFECYCLE.md`、`SYNC_PAIRING.md`、`SYNC_CHECKPOINTS.md`。本任务没有 Relay HTTP API、TLS socket、PG网络测试、Kernel页同事务adapter、真实process kill、production keystore、真实human presence、MinIO/OPFS、全量snapshot bootstrap或Sprint3实现。

## RED / GREEN 证据

最初 API 缺失由 assertion 触发 RED，不是收集/语法/import错误：

- lifecycle/pairing：8 failed，`trusted lifecycle API not implemented`。
- checkpoint/artifact：11 failed，缺失对应API。
- Node lifecycle：3 failed，`trusted lifecycle not implemented`。
- independent interop：1 failed，`cross-language lifecycle helper missing`。

新增安全回归先实际失败后修复：

| 行为 | 实际 RED | 最终修复 |
| --- | --- | --- |
| PENDING持久→ACTIVE | `INVALID_GRANT_TRANSITION` | signed grant operation允许新PENDING；activation仅PENDING→ACTIVE，identity不变 |
| 实际kit恢复旧Project Key | `recovery key backup not implemented` | 标准HPKE RecoveryBackup；先验签和最新anchor/context，再unwrap |
| 稳定设备UUID与fresh-key revoke | helper缺失assertion | TEST ONLY file device store + `revoke_and_rotate` |
| 禁止vault写入Git目录 | `DID NOT RAISE` | resolved ignored runtime/systemtmp路径边界 |
| 有效AEAD的bool chunk index | `DID NOT RAISE` | strict int/schema，不依靠tag碰巧拒绝malformed合法签发内容 |
| 有效签名的bool checkpoint epoch | 两参数均`DID NOT RAISE` | membership/keyepoch strict safe_int |
| 已pin历史Envelope | helper缺失assertion | 认证历史签名/prefix/epoch后只返回QUARANTINED |
| pairing写入后错误 | 写入manifest后注入failure，旧manifest断言失败 | proof失败仅存attempts；persistence错误逸出transaction完整rollback |
| Node rotation JSON raw key | `rotation result must redact raw key` | #private raw key + getter，不枚举/序列化secret |

可重跑的回归命令：

```powershell
.venv/Scripts/python.exe -m pytest tests/secure_sync/test_pairing.py::test_pairing_persistence_failure_after_manifest_write_rolls_back -q --basetemp=storage/runtime/s2-lifecycle-tmp
.venv/Scripts/python.exe -m pytest tests/secure_sync/test_checkpoint.py::test_validly_signed_checkpoint_rejects_boolean_epoch -q --basetemp=storage/runtime/s2-lifecycle-tmp
.venv/Scripts/python.exe -m pytest tests/secure_sync/test_artifacts.py::test_artifact_valid_tag_with_boolean_index_is_strictly_rejected -q --basetemp=storage/runtime/s2-lifecycle-tmp
```

上述 tests 保留为修复后的 GREEN，不放宽signature/AAD/epoch规则。`crash_point` 是异常注入，不是实际终止process。

## 实际验证

```powershell
.venv/Scripts/python.exe -m pytest tests/secure_sync -q --basetemp=storage/runtime/s2-lifecycle-tmp
```

结果：**87 passed in 12.17s**，Task1已有39 + 本任务新增46 + root独立TLS材料2。Windows sandbox默认访问pytest临时目录报WinError5；相同限定synthetic命令经自动approval允许后运行，没有改测试语义或个人数据边界。

追加旧 Sprint0/1 全部纯协议原型/Kernel/向量回归：`pytest tests/sync_prototype tests/sync_kernel tests/sync_vectors tests/secure_sync -q --basetemp=storage/runtime/s2-lifecycle-tmp`，**145 passed in 17.28s**（本命令实际旧58 + secure87）；不接PG，真实网络/PG验收仍由Task3完成。

在 `packages/secure-sync`：

```powershell
E:/node/node.exe --test --test-isolation=none test/crypto.test.ts test/lifecycle.test.ts
E:/node/node.exe ../../apps/web/node_modules/typescript/bin/tsc -p tsconfig.json
```

结果：**13 Node tests passed**（Task1旧6 + 本任务新7），typecheck PASS。CI使用PATH上的node；interop Python通过`NODE_BIN`覆盖，Windows E:/node存在时采用，否则回落node。

新增Python文件的 `ruff check` / `ruff format` PASS；`git diff --check` PASS（root计划文件既有CRLF转换warning不影响内容）。独立跨语言测试在两个方向真正open HPKE grant/backup、snapshot/chunks、签名manifest；Node独立实现，不调用Python primitive。随机运行时钥匙不进入fixture/输出。deterministic interop inputs是公开TEST ONLY bytes-range seeds，只经本地subprocess pipe传递，输出只有public signed objects/ciphertext/digests。

Hypothesis覆盖generated grant/confirmation scope、epoch add/revoke schedules、chunk permutations；已运行的负例包括signature/context/role/epoch/历史删除/nonce prefix重用/自授owner/fork、pairing expiry/5 attempts/replay/immutable receipt/revoke后retry、wrong kit/anchor/backup epoch、artifact order/missing/duplicate/tag/size/epoch、snapshot hash/signature binding，以及checkpoint rollback/fork/gap。

## 本任务文件归属

仅以下文件由本实现工人修改，Git commit/push由root处理；不纳入root TLS/CI/Relay infra未审查文件：

- `packages/secure_wire/{membership,checkpoint}.py`
- `apps/api/researchhub/sync/secure/{keys,pairing,checkpoint,artifacts}.py`
- `packages/secure-sync/src/{membership,keys,pairing,checkpoint,artifacts}.ts`
- `packages/secure-sync/test/{lifecycle.test,lifecycle_interop}.ts`
- `packages/secure-sync/package.json`（test script包含新Node suite）
- `tests/secure_sync/test_{lifecycle,pairing,checkpoint,artifacts,lifecycle_interop}.py`
- `docs/sync/SYNC_KEY_LIFECYCLE.md`, `SYNC_PAIRING.md`, `SYNC_CHECKPOINTS.md`, 本交接记录。

现有Task1语义suite、公开固定fixture、nonce实现和primitive未修改。未提交/推送，未调整仓库可见性。

## 独立 specification review 修复（2026-10-08）

首次独立 spec review 找到三项未覆盖阻塞，不能以原87/13全绿代替修复。新增实际行为 RED 命令：

```powershell
.venv/Scripts/python.exe -m pytest tests/secure_sync/test_recovery_anchors.py tests/secure_sync/test_checkpoint.py::test_all_genesis_chain_entry_points_require_zero_digest tests/secure_sync/test_artifacts.py::test_artifact_valid_inner_outer_and_chunk_auth_rejects_boolean_inner -q --basetemp=storage/runtime/s2-lifecycle-tmp
```

修复前 **11 failed**：manifest-only kit 仍 recover/unwrap、恶意/错误 signed cp组合、无local store/monotone、非零genesis，以及完整 valid inner+outer+chunk auth 的 bool artifact key_epoch/nonce_prefix 均被接受。Node 新cp/genesis行为2 failed。修复没有放宽冻结要求：

1. kit必须有 manifest+checkpoint trusted组合，更新必须指定本地 TrustedStore；从 pinned bootstrap roots 验证完整stored manifest chain。signed cp strict context/signature/chain验证，初次cursor0仅zero64，初次非零只能来自已验证本地CheckpointStore；后续以完整rows作verify_advance，拒绝rollback/fork。missing/untrusted cp/store/history均FRESHNESS错误。recover提交后newowner签新epoch、原cursor/chain cp并更新组合anchor。
2. Artifact所有inner整数/UUID补齐strict验证，包括key_epoch和nonce_prefix；有效重新签名/封装/tag也必须拒绝bool。对应Node同schema，不依靠AEAD偶然拒绝。
3. 三个genesis入口 `extend_chain` / `verify_checkpoint` / `CheckpointStore.pin` 在Python/Node都强制cursor0→zero64；合法签名不能绕过。

增加可信初次非零本地 checkpoint 路径正例后，最终 `pytest tests/secure_sync` **99 passed in12.24s**（旧Task1 39 + Task2新58 + root TLS2）；Node **16 passed**（旧6 +新10），typecheck PASS；全部secure Python Ruff check/format-check PASS，diff-check PASS。独立双向interop setup同步为签名checkpoint+localstore组合，仍不暴露keys。完整旧协议合并命令 `pytest tests/sync_prototype tests/sync_kernel tests/sync_vectors tests/secure_sync -q --basetemp=storage/runtime/s2-lifecycle-tmp` **157 passed in17.58s**。本节结果取代前文首次交接数量，供同spec复审。

本次新增归属文件：`tests/secure_sync/test_recovery_anchors.py`。仍未做Task3或Git提交/推送。

## 同 specification 复审第二轮修复

再次复审暴露2项实际行为缺口，原99/16全绿不代表验收。新增 `pytest tests/secure_sync/test_recovery_anchors.py ...` 实际 **4 failed**：清空已有Kit nullable anchors可重新cp0初始化、raw旧私钥import可cp0初始化、valid signed foreign chain，以及`[own valid, foreign valid]`可提交其他project。Node新增对应2 tests实际RED。

Kit现在保留不依赖nullable fields的内部checkpoint digest与一次性初始化能力。仅本地 `generate()` 的新随机Kit具此能力，首次成功即消耗；已有anchor清空不复位。raw-seed构造默认imported、无bootstrap能力，即使cp0合法或另有checkpoint-store也不能冒充fresh creation。公开fixed vectors只用显式且限定公开known bytes的TEST ONLY factory。完整trusted Kit export/import仍未实现，原型恢复正例要求仍有完整可信组合anchor。`recover` 在任何写入前全量检查chain project必须等于kit.project；全valid own+foreign也拒绝，A/B和Kit anchors保持不变。

最新 actual `pytest tests/secure_sync` **103 passed in12.36s**（Task1旧39 + Task2新62 +root TLS2），Node **18 passed**（旧6 +新12），typecheck/Ruff/diff-check PASS。完整旧协议+secure命令本轮 **161 passed in17.86s**，不能引用前一轮157代替。文件归属未扩大，仅修改已有keys、anchor tests、Node tests、TEST ONLY interop factory及生命周期/本记录文档。仍未Git提交/推送，未做Task3。

## 同 specification 复审第三轮：Kit 公共组合持久化

冻结规则2还要求跨实例恢复可信最新组合，旧103/18正例只依赖存活内存 Kit，未覆盖此要求。本轮实际 RED：

```powershell
.venv/Scripts/python.exe -m pytest tests/secure_sync/test_kit_persistence.py -q --basetemp storage/runtime/s2-anchor-persist-red2
$env:PATH='E:\node;'+$env:PATH
npm --prefix packages/secure-sync test
```

Python **12 failed**（restore API 缺失 assertion；checkpoint 签名失败后 membership 已被提交），Node **18 passed / 2 failed**（同两项）。sandbox 首跑出现 pytest 临时目录 WinError5，该次是环境失败、不算 RED；限定合成 runtime 命令经自动审批后得到了上述有效 RED。

追加选择性 journal 尾部丢失、完整旧 cp 替换时，Python `-k 'tail_loss or complete_old_cp' --basetemp storage/runtime/s2-anchor-persist-head-red` **2 failed**；Node **20 passed / 1 failed**。因此新增同事务 `kit_anchor_heads` latest revision/record digest，而非仅扫描 journal 最后一行。追加初次 anchor 未验证 rows 拒绝时，Python `-k initial_anchor --basetemp storage/runtime/s2-anchor-persist-rows-red` **1 failed**、Node **22 passed / 1 failed**，修复为初次 rows 必须为空，不把任意 caller JSON 写入公共 metadata。

最终实现和 public API 详见 `SYNC_KEY_LIFECYCLE.md` 的「TEST ONLY Kit 公共 metadata 保存与重建」。`update_anchor/updateAnchor` 是保存入口；`RecoveryKit.restore_from_trusted_store/restoreFromTrustedStore` 只加载此前已提交本地完整组合，不接受 caller checkpoint。两语言均重新导出 seed 公钥、绑定 Kit UUID/project、独立 pinned membership chain、strict cp signature/epochs、连续 journal/rows、head digest及本地当前 manifest。recover 的 chain/newmanifest/newcp/journal/head 在同一个 SQLite 事务内完成，commit 后才更新内存。

真实 SQLite trigger 注入分别覆盖 journal INSERT 前、head INSERT 前、head UPDATE 后，且 recovery 先处理一条 valid own transition：任何失败均 rollback 全部 manifest/journal/head，Kit 内存不变，新 TrustedStore+新 Kit 仍读到原 cp1 完整组合。updateAnchor 持久失败也验证相同内存/公共记录边界。cp0→cp1 正例重建 TrustedStore、CheckpointStore 与 Kit，再 unwrap backup/recover，二次重建确认新 epochs/cursor。缺失/部分metadata、坏cp、oldcp、尾部丢失、wrong signing/recipient roots、wrong UUID/project、丢membership history/pinned root错误、bool metadata epoch均拒绝。原 seeds-only + 合法旧cp0 + 新CheckpointStore拒绝及此前五项 finding 回归保留。

最终实际 GREEN 命令与结果：

```powershell
.venv/Scripts/python.exe -m pytest tests/secure_sync -q --basetemp storage/runtime/s2-anchor-persist-final
.venv/Scripts/python.exe -m pytest tests/sync_prototype tests/sync_kernel tests/sync_vectors tests/secure_sync -q --basetemp storage/runtime/s2-anchor-persist-combined
.venv/Scripts/python.exe -m pytest tests/secure_sync/test_lifecycle_interop.py -q --basetemp storage/runtime/s2-anchor-persist-interop
npm --prefix packages/secure-sync test
npm --prefix packages/secure-sync run typecheck
```

- secure suite：**127 passed in14.68s**（Task1旧39 + Task2 86 + root TLS材料2）。本轮新 `test_kit_persistence.py` 共24项。
- 旧协议/Kernel/向量+secure合并：**185 passed in21.72s**。
- 独立 Python↔Node 双方向真实 grant/backup HPKE、membership、snapshot/chunks：**1 passed in0.63s**；没有改为调用另一语言 primitive。
- Node：**23 passed**（Task1旧6 + Task2 17）；typecheck PASS。
- 本轮两个 Python 文件 Ruff check/format-check PASS；`git diff --check` 及六个本轮修复文件（含 untracked）的 `git -c core.safecrlf=false diff --no-index --check -- NUL <file>` 无 whitespace 诊断（no-index 的差异退出码1按差异处理；命令级配置未改仓库/全局配置）。

本修复实际只改 Python/Node keys、Node lifecycle tests、新 `tests/secure_sync/test_kit_persistence.py`、生命周期文档与本记录。无Git提交/推送，无Task3/network/production/个人服务操作。journal+head属于可信本地公共组合，非独立fsync witness；同时一致恶意回滚 journal/head/相关可信history/checkpoint不能证明全局 freshness，split-view、未锚定消息隐藏、生产encrypted vault/Kit export UX仍未实现。此修复只交接独立 specification/quality review，不宣称 Sprint2 或网络 Gate PASS。

## Quality/security 复审修复：SQL history integrity 与 checkpoint 双 epoch

独立 specification PASS 后，quality/security 实际 probe 找到两项 Important/P2：SQL 索引列未和 signed body 交叉验证可漏读撤销；signed checkpoint 只约束 cursor/chain，仍可退双 epoch。原127/23全绿不能替代此轮修复。

新增实际行为 RED 命令：

```powershell
.venv/Scripts/python.exe -m pytest tests/secure_sync/test_history_integrity.py tests/secure_sync/test_checkpoint.py -q --basetemp storage/runtime/s2-quality-red
$env:PATH='E:\node;'+$env:PATH
npm --prefix packages/secure-sync test
```

结果 Python **11 failed / 6 passed**，Node **23 passed / 3 failed**。SQL `epoch/digest/project` 单独改动、SQL未来epoch中重复 bootstrap、matching SQL digest 的坏 body signature，以及 same/growing cursor 的旧 signed cp 双 epoch 回退、删epoch/signature/退化三字段/bool epoch，都先观察到拒绝断言失败。

修复路径：

- SQL所有公共 manifest 行先核 `project/digest/epoch` 与 strict body、canonical digest、连续 `1..N` 和 parent；全表 metadata 扫描防 project 列被改走后遗漏撤销行。Python所有读重验所选项目完整 pinned-root签名链。Node同步 `current/history` 明确仅结构读，所有异步权威入口使用 `verifiedCurrent` 完整验签，写入/分类复用持有 connection。合法 current exact retry不追加记录；另有直接 bootstrap1 → SQLepoch2/body bootstrap1 的拒绝回归。
- public `verify_advance/verifyAdvance` 默认完整 signed anchor，strict字段/types/签名编码；membership/key epoch各自非下降，same/growing cursor皆适用。三字段 pin anchor必须显式 bootstrap 参数。CheckpointStore持久独立 kind，首次advance原子改SIGNED，之后删字段不能重新解释为BOOTSTRAP；旧无kind库fail closed，不自动推断迁移。两语言实现独立；未增加自研crypto。

继续检查权威读时发现配对入口也必须全链验证，root授权扩展原Task2 pairing文件。追加匹配SQLdigest的坏本地signature回归：Node challenge/consume/receipt三个独立测试 **26 passed / 3 failed**，实际分别漏拒challenge、错误消耗attempt、漏拒receipt；Python **1 failed / 2 passed**，consume错误消耗attempt。已将本地完整history验证移到proof计数前，存储/信任错误整事务rollback；真正proof失败仍计五次限制，原storage失败rollback语义保留。Node `retryReceipt` 改async，所有仓内caller更新await，文档声明此QA API变化；没有复制同步Ed25519实现。

本轮最终实际验证：

```powershell
.venv/Scripts/python.exe -m pytest tests/secure_sync -q --basetemp storage/runtime/s2-quality-full
.venv/Scripts/python.exe -m pytest tests/sync_prototype tests/sync_kernel tests/sync_vectors tests/secure_sync -q --basetemp storage/runtime/s2-quality-combined
.venv/Scripts/python.exe -m pytest tests/secure_sync/test_lifecycle_interop.py -q --basetemp storage/runtime/s2-quality-interop
npm --prefix packages/secure-sync test
npm --prefix packages/secure-sync run typecheck
```

- secure：**147 passed in17.22s**（旧127 + history integrity10 + checkpoint10）。包含root独立TLS材料2；不把这些材料单测称网络验收。
- 旧协议/Kernel/向量+secure：**205 passed in21.38s**。
- 双向独立interop：**1 passed in0.68s**。
- Node：**30 passed**；typecheck PASS。
- 六个本轮Python文件 Ruff check/format-check PASS；14个本轮修复文件逐个 `git -c core.safecrlf=false diff --no-index --check -- NUL <file>` 无whitespace诊断（退出码1仅内容差异，未改Git配置）。

新增 `tests/secure_sync/test_history_integrity.py`；其余修改局限于原Task2 Python/Node keys/checkpoint/pairing、pure公共checkpoint、checkpoint/Node lifecycle tests及四份Task2协议/QA文档。无Git提交/推送，无Task3/网络/生产/个人服务操作；完整trusted材料一致恶意回滚与split-view局限不变。交接后冻结，等独立spec与quality复审，不能宣称Sprint2完成。

## Specification 复审修复：持久 SIGNED checkpoint 真实验签

独立复审实际发现，持久 SIGNED 行只有 shape 校验：只翻转 signature 一字节，或只把 cp1 body 的 cursor/chain 改为0/zero64，重开 `get` 仍返回对象，`advance` 还能覆写为新 cp2 或旧 cp0。公共 `verify_checkpoint` 本来能拒绝该签名；147/30全绿没有覆盖 Store 读取边界。

先加入两语言独立行为测试，再改实现。Python 执行 `test_checkpoint.py -k persisted_signed_checkpoint --basetemp storage/runtime/s2-cp-auth-red2`（当时仅 get/advance 两入口）实际 **4 failed**；Node `npm --prefix packages/secure-sync test` 实际 **30 passed / 4 failed**，均为预期拒绝没有发生，非环境失败。覆盖 signature bit 与 cursor0 body 损坏，且先断言公共 verifier 拒绝，随后断言 Store 拒绝并保持完整 SQL 行不变。

修复在认证 candidate 时保存最小7字段公共 context：`version, opaque_project_id, membership_epoch, key_epoch, creator_device_id, signing_public_key, checkpoint_digest`。不保存无法交叉验证且未使用的 manifest digest，也不存 private seeds/project key。每次 SIGNED `get/advance` 先 strict 验证 context/bindings，再调用既有成熟 Ed25519 verifier 真实验签并比对 checkpoint digest；旧 anchor 未通过则无写入。Node `get` 改为 async，所有仓内 caller 包括 Kit 初次非零锚点读取均 await，不复制同步 crypto。

追加回归覆盖 Kit 接入、缺失/部分/extra context、错误公钥、epoch/digest 绑定损坏，以及坏签名连同 digest 一起重算；`get/advance` 拒绝且 SQL 行不变。Kit 接入失败还断言内存组合未初始化。旧 schema 缺 verification 列 fail closed；旧 creator 后来被撤销的正常重启读取/advance 和新 Kit 初始化仍通过，不拿当前 ACTIVE/epochs 错误拒绝历史合法锚点。此前 missing kind、双 epoch、完整历史、Kit/recovery 原子性与互操作回归保留。

去掉冗余字段并补齐 context 负例后的最新实际验证：

```powershell
.venv/Scripts/python.exe -m pytest tests/secure_sync -q --basetemp storage/runtime/s2-cp-auth-minimal-final
.venv/Scripts/python.exe -m pytest tests/sync_prototype tests/sync_kernel tests/sync_vectors tests/secure_sync -q --basetemp storage/runtime/s2-cp-auth-minimal-combined
.venv/Scripts/python.exe -m pytest tests/secure_sync/test_lifecycle_interop.py -q --basetemp storage/runtime/s2-cp-auth-minimal-interop
$env:PATH='E:\node;'+$env:PATH
npm --prefix packages/secure-sync test
npm --prefix packages/secure-sync run typecheck
```

- secure：**162 passed in19.64s**，包含root独立TLS材料2；材料单测不代表网络验收。
- 旧协议/Kernel/向量+secure：**220 passed in24.55s**。
- Python↔Node 独立双向interop：**1 passed in0.77s**。
- Node：**38 passed**；typecheck PASS。
- 本轮 Python checkpoint/source test Ruff check/format-check PASS；本轮8个文件（含 untracked）逐个 no-index whitespace 检查 PASS。

本轮只改 Python/Node checkpoint、Node keys 的异步读取接入、Python checkpoint/Node lifecycle tests，以及 checkpoint/lifecycle/本QA三份文档。缺 verification 的旧QA store需要从可信材料重建，生产迁移 UX 未实现。完整 body/context/kind 及其他可信材料一致恶意替换/回滚仍无法自证全局 freshness；未引入新 witness 或生产 vault。无Git提交/推送，无Task3/网络/生产/个人服务操作；冻结交独立spec与quality复审，不宣称Sprint2完成。

## 最终独立复审与 root 验证

2026-10-08 同spec复审PASS：排除TLS的合并218通过、Node38/typecheck通过；Python/Node各11类自行构造的持久损坏探针均在get/advance/Kit入口拒绝，完整SQL行、Kit内存及journal不变。合法历史creator撤销后的重开/推进/Kit恢复、BOOTSTRAP非空context拒绝及真实AFTER UPDATE回滚通过。

随后独立quality/security APPROVED：排除TLS的合并218通过（22.55s），Node38/typecheck及Ruff通过；两语言各22个额外负例检查通过。原历史权限复活、双epoch回退、坏持久签名即使重算digest均拒绝，SQLite更新失败保留原行；权威调用链与async callers复核，无未关闭Critical/Important。

root从当前实际代码重新运行 `pytest tests/sync_prototype tests/sync_kernel tests/sync_vectors tests/secure_sync --ignore=tests/secure_sync/test_tls_material.py -q --basetemp=storage/runtime/s2-root-verified-checkpoint-final`，218 passed in26.16s；Node38/typecheck、全部secure Python Ruff/格式通过。排除的两项TLS证书材料文件属于后续Relay实现，不纳入本次生命周期提交。本页各历史结果按轮次保留，不抵充最终Sprint2完整审查后回归。root负责RH-014提交及GitHub同步，结果另见CHANGELOG和最终报告。
