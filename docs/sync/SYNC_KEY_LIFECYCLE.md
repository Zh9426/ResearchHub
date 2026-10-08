# Device / Project Key Lifecycle

状态：Task 2 的纯公共校验器与 trusted-client QA prototype 已实现；最终八项 Gate 和真实网络验收仍在后续阶段。QA keys不用于真实科研。

## Keys 与可信状态

设备UUID绑定独立Ed25519 signing key与X25519 recipient key。project每key_epoch有独立随机32byte AESkey；Artifact独立DEK。KeyVault/DeviceKeyStore是trusted-client接口，仅本轮临时内存或被忽略QA文件实现。Relay只存publickeys、签名manifest/grant与标准HPKE wrappedkey。普通Audit/log/Git不保存随机私钥、projectkey、kitsecret。

用户密码是登录材料，不是projectkey，passwordreset不产生E2E解密权限。root/recoverypublickeys在bootstrap本地预先pin或trustedpairing人工核对，不相信Relay返回的新root。固定vectors包含公开可复制的TEST ONLY私钥属于需求66例外，绝不用于运行时身份。

## Membership 状态与 transition

manifest完整列出opaqueproject、membership/keyepoch、previousdigest、authority、recoveryanchor及members。成员至少含UUID、两公钥/fingerprint、role、status、永久nonceprefix、granted/revokedtime。全部canonical字段在authority签名内。

| 状态/role | 能力 |
| --- | --- |
| PENDING | 不获得projectkey，不push mutation |
| ACTIVE reader | 获取被授权密文/key；不能push mutation或修改membership |
| ACTIVE writer | 签名push合法currentepoch mutation；不能授予membership |
| ACTIVE owner | writer能力与受验证membership变更 |
| REVOKED | 新请求/新envelope拒绝，无futurekey grant，不能重新用旧pairingreceipt激活 |

普通transition验证**旧pinned manifest**的ACTIVEowner签名，previousdigest与本地digest CAS、membershipepoch精确+1。加入keyepoch不变；撤销keyepoch精确+1并freshkey。保留所有旧member和prefix，公钥不可静默替换，同epoch异digest报MEMBERSHIP_FORK；跳跃需验证完整连续chain，不接受Relay“最新版”自证。

recovery是唯一例外：仅bootstrap已pin的recoverysigningkey可签`operation=recovery`，parent/CAS与双epoch精确+1；新recipient两公钥/新prefix显式绑定，新ownerACTIVE、全部旧成员REVOKED并保留历史。

## Key grants

RFC9180 Base X25519/HKDFSHA256/AES256GCM one-shot wrapping，enc32||ct。canonical info绑定opaqueproject、recipientUUID/recipientpubkey、membership/keyepoch、session/grantidentity。Base senderanonymous，所以先验证受信authority签名的完整grant（含context/wrappedbytes），再unwrap；不能直接解开Relay返回的任意包。

撤销B后所有新消息采用freshkeyepoch。A/C等仍ACTIVE收件人获新grant，B既没有grant也不能用旧key解密。旧key/过去plaintext不能被远程擦除；科学created_at不证明旧权限有效。已durable旧epoch历史经已锚定历史manifest验证后transportquarantine，不送Kernel，不挡住新epoch后续page。

## Nonce ledger

authority永久分配不重复uint32prefix，nonce=`prefixBE4 || counterBE8`，counter1..safeintmax。Python/Node同SQLite+fsyncwitness契约，预约提交后才encrypt。重试保存原envelope；reencrypt必须新预约nonce/newmessageUUID但semanticidentity不变。

显式freshkey注册；文件丢失/坏尾部/row丢失/DBwitness不符/回滚/overflow停写旧key。正常crash可能耗号或要求rotate，绝不清零“修复”。全trustedstate同时rollback无法检测，备份恢复写入前rotate。HPKE只freshoneshotcontext不复用nonce状态。

## Recovery matrix

| 场景 | 安全恢复路径 |
| --- | --- |
| 丢phone，电脑可信keys仍有 | owner撤销phone、换epochs、配对newdevice |
| 丢primary，另一owner仍有keys | 可信owner恢复newprimary并撤销旧设备 |
| 丢password，设备keys仍有 | 独立loginreset，不从Relay制造projectkey |
| 全devices丢失，kit与可信最新anchor仍有 | 验证anchor起连续chain，recoverysign授权newowner/rotate |
| kit私钥仍有但可信anchor丢失 | RECOVERY_FRESHNESS_UNVERIFIABLE，不能信Relay旧签名状态 |
| devices私钥与kit全部丢失 | E2E_DATA_UNRECOVERABLE，无servermaster |

kit是高熵secret与可信manifest/checkpointanchor的组合，需要随着verifiedtransition更新；陈旧kit不能证明没有Relay隐藏的未锚定更新。完整gossip/transparency、硬件keys、真实browservault和userpresence均NOT IMPLEMENTED。

## Task 2 实际接口与字段

Python `packages/secure_wire/membership.py` 是纯公共校验层，只依赖 canonical/envelope schema 和 Ed25519 public verification；不依赖 Domain、client、private-key 或 AEAD。对应 Node 独立实现位于 `packages/secure-sync/src/membership.ts`，只在本轮 Node QA 使用。

完整 manifest exact fields：`version, opaque_project_id, membership_epoch, key_epoch, previous_digest, operation, authority_device_id, recovery_device_id, recovery_signing_public_key, recovery_recipient_public_key, members, signature`。签名 preimage 为 `ResearchHub/Membership/v1\0 || canonical(all fields except signature)`。kit 两公钥和不具设备写权限的 opaque recovery UUID 由首次受信 owner 签名 bootstrap 绑定；后续不可替换。成员 exact fields：`device_id, signing_public_key, recipient_public_key, fingerprint, role, status, nonce_prefix, granted_at, revoked_at`。fingerprint 为两公钥 canonical object 的 SHA256。日期为合成 QA 整秒值，不能解释为当前权限证据。

`verify_bootstrap` 要求显式已知 owner/recovery signing public roots；`verify_transition(previous, candidate, recovery_public)` 从旧 manifest 选 authority，只允许连续 CAS。`member_of` / `verify_active_envelope` 检查当前 role、status、双 epoch、signature 与 authority 分配 prefix。`verify_historical_envelope` 只接受本地已 pin 的连续历史，结果为 `QUARANTINED`，不能送入 Kernel。`classify_envelope(TrustedStore, env)` 使用持久历史选择这两条路径。

Python trusted APIs 位于 `apps/api/researchhub/sync/secure/keys.py`；TypeScript 使用 camelCase 对应名：

- `Device.generate()`：随机 UUID，独立 CSPRNG Ed25519/X25519 seeds；secret 字段从 repr/JSON 隐藏。
- `DeviceKeyStore`：`TestOnlyMemoryDeviceKeyStore` 与 `TestOnlyFileDeviceKeyStore`。后者用 **未加密 TEST ONLY SQLite** 演练重启 identity，仅允许 resolved `storage/runtime/` 或 system temporary 路径；不允许写 fixtures/Git 管理目录。此实现不是生产 keystore。
- `KeyVault` / `TestOnlyKeyVault`：内存 per-project/per-epoch 32-byte 随机 key，已有 epoch 不得覆盖；密码不参与 key 生成。
- `TrustedStore`：SQLite FULL，持久 roots、完整 signed manifest history、challenge/attempts、wrapped receipt，以及公共 Kit 组合 metadata journal/head；不存 project plaintext key、device private seed 或 kit secret。
- `transition(add=member)` 允许 owner 签入 PENDING 或 ACTIVE；PENDING 不可获 grant、不可 mutation。`transition(activate=device_id)` 只能将已记载 PENDING 改为 ACTIVE；旧 UUID/公钥/prefix/role/granted_at 不变。撤销永远保留旧 identity 和 prefix。
- `make_grant` / `open_grant`：完整 exact signed grant 包括 `version, authority_device_id, context, role, manifest_digest, wrapped_key, signature`；context 使用 Task 1 的七个 HPKE info 字段。先验 authority 与全部 scope/bytes，后 unwrap。
- `revoke_and_rotate`：当前 prototype 要求 store 内一个显式已 pin project；双 epoch 前进，新 CSPRNG key，并仅为仍 ACTIVE 的成员签 grant。返回 `Rotation`，raw key repr/JSON 隐藏。失败后的孤立 QA epoch key 不复用；需 fresh QA vault 重试，生产 durable key-store transaction 未实现。

SQL `project/digest/epoch` 是索引而非可信授权状态。每次读先核对所有公共 manifest 行与 strict signed body 的 scope、canonical digest、membership epoch 一致，并按项目要求 SQL/body epochs 从1连续递增及 previous digest 相连；扫描全部公共行也防止 SQL project 列被改走后漏读该项目的撤销行。Python `current/history/verified_current` 均重验所选项目独立 roots 起的完整签名链。Node 同步 `current/history` 只提供完整历史结构/索引一致性读取，不能据此作授权；异步 `verifiedCurrent` 重验完整签名链，`accept/classifyEnvelope/recover/revokeAndRotate` 以及配对 challenge/consume/receipt 权威入口均使用它，并在写入或分类时复用同一个 SQLite connection。完整相同 current manifest 的 accept retry 仍幂等，不把存储的重复 bootstrap 行当作合法 retry。QA 实现全表扫描，不声称生产大规模索引性能。

## 实际 RecoveryBackup

`make_recovery_backup(manifest, owner, kit, project_key)` 用已 pin kit X25519 public recipient 做标准 HPKE wrapping。完整 authority signed fields 为 `version, authority_device_id, manifest_digest, context, wrapped_key, signature`，domain 为 `ResearchHub/RecoveryBackup/v1\0`。`open_recovery_backup` 要求 kit 的 project/latest trusted manifest **与 checkpoint 组合 anchor** 完整可信，且 manifest 与本地 store 当前值相等，随后验证 owner signature、project、两 epoch、kit UUID/两公钥，最后 unwrap；wrong kit、project、epoch、root 或 signature fail closed。

QA recovery 流程是：先用最新匹配 backup 恢复之前授权的 Project Key；再 `recover(store, kit, new_owner, chain=...)` 从已 pin组合 anchor 验证连续 chain，kit signing root 签 recovery transition，撤销全部旧成员，给新 owner 全新 prefix/两公钥，双 epoch +1。新 owner 使用 fresh key 与 grant，之后要生成并保存对应新 epoch 的 backup。`recover` 在同一个 SQLite 事务内验证并写入 chain/new manifest、由 new owner 签同 cursor/chain 和新 epochs 的 checkpoint、写入公共组合 metadata journal/head；只有 commit 成功才更新 Kit 内存。签 checkpoint、journal/head 持久化或 commit 失败均不得留下部分 membership rotation。其他 verified transition 的调用方必须同步 `kit.update_anchor(verified_manifest, verified_checkpoint, store=trusted_store, rows=verified_rows)` 并更新 backup。旧 backup 不会被当作 current epoch，遗漏刷新会导致明确 freshness/binding failure，不会 fallback。

`RecoveryKit.update_anchor`（Node `await kit.updateAnchor(manifest, checkpoint, trustedStore, rows, checkpointStore?)`）要求 local TrustedStore；会从独立 pinned bootstrap roots 重新验证全部 stored manifest 连续历史，再验证 checkpoint strict schema/project/两 epoch/creator signature/chain。checkpoint 缺失、来自 Relay 的未 pin manifest、其他项目、坏签名、bool cursor、错误 epoch/chain、无法验证当前 history 一律 `RECOVERY_FRESHNESS_UNVERIFIABLE`。

只有 `RecoveryKit.generate()` 在 trusted client 本地新建随机 Kit 时获得一次性 bootstrap 初始化能力。初始 signed checkpoint 明确定义为 cursor0/zero64 genesis；若新 Kit 首次设置的是非零 cursor，必须额外提供已验证并持久保存精确该 checkpoint 的本地 `CheckpointStore`，不能凭一份 Relay 返回的合法旧签名假定其最新。成功设置后初始化能力不可再用；内部 checkpoint digest/初始化状态不随 public nullable anchor清空而重置。manifest/checkpoint丢失时，即使还保有Kit私钥，也不能把旧合法cp0当初次bootstrap恢复freshness。

CheckpointStore 的 SIGNED 读取须用此前可信提交保存的 creator 公钥真实验签，并核对公共 context 与完整 checkpoint digest；局部坏签名或 cursor/chain 改动不得被 Kit 当作可信非零初始化证据。Node `CheckpointStore.get` 是异步 API，Kit `updateAnchor` 等待该验证完成后才保存组合；读取失败保持 Kit 内存与 journal/head 不变。历史 creator 后来撤销不影响已认证旧 checkpoint 作为单调起点，新增 checkpoint 仍按当前 manifest 验证。具体字段与旧 schema fail-closed 边界见 `SYNC_CHECKPOINTS.md`。

直接 `RecoveryKit(signing_seed, recipient_seed, ...)` / Node `new RecoveryKit(...)` 是 **imported-seeds-only**，默认没有bootstrap能力；全部trusted metadata丢失时，不论旧签名cp0是否有效或现造一个本地CheckpointStore，均 `RECOVERY_FRESHNESS_UNVERIFIABLE`。raw私钥本身不证明初始或最新状态。公开fixed-vector例外只通过显式 `from_public_test_vectors` / `fromPublicTestVectors`，且仅接受已公开 TEST ONLY 的固定bytes-range seeds；随机运行时私钥不能借此获得初始化能力。

## TEST ONLY Kit 公共 metadata 保存与重建

`update_anchor` / `updateAnchor` 成功时，在同一个本地 TrustedStore 事务中追加 `kit_anchors` 并更新 `kit_anchor_heads` 的 latest revision/digest，提交后再替换内存 anchors。journal 每条 exact fields 是 `version, revision, previous_digest, device_id, signing_public_key, recipient_public_key, project, manifest_digest, membership_epoch, key_epoch, checkpoint_digest, checkpoint, rows`；checkpoint 是完整 strict signed object，rows 是已验证的连续公开 sequence/envelope digest。首次设置没有前置 cursor，rows 必须为空；非零首次 checkpoint 的信任仍须来自既有本地已验证 CheckpointStore。数据库只记录公共字段，绝不保存 Kit/device seeds 或 Project Key。

重新启动后，保留原本独立保存的两 private seeds 和 Kit UUID，并指定本地可信项目与已存在 TrustedStore：

```python
kit = RecoveryKit.restore_from_trusted_store(
    signing_seed, recipient_seed, device_id=kit_id,
    project=opaque_project_id, store=reopened_trusted_store,
)
```

Node 对应 `await RecoveryKit.restoreFromTrustedStore(signingSeed, recipientSeed, kitId, opaqueProjectId, reopenedTrustedStore)`。这两个公开 TEST ONLY load API 不接受调用者提供的“最新 checkpoint”。它们从 private seeds 重新导出公钥，对比 UUID/root/project，重验独立 pinned bootstrap roots 和完整 membership chain、所有 journal revision/previous digest/epoch、对应历史 manifest、strict checkpoint signature/bindings、连续 cursor/chain/rows，最后核对 committed head，并要求组合 manifest 仍等于本地当前 manifest。缺 metadata/head/history、部分记录、坏 signature、旧 cp 替换/尾部丢失、错 seeds/UUID/project 都 fail closed；保存失败不改原内存，恢复失败也不提交中间 transition。

真实 QA 正例使用 cp0→cp1，关闭每次事务连接，重新创建 TrustedStore、CheckpointStore 和 Kit 实例，加载最新 cp1 后 unwrap backup/recover，再重建确认新 epochs。生产私钥 vault、encrypted Kit 导出格式、用户恢复 UX 尚未实现。journal+head 是本地可信组合，不是外部防篡改 witness；二者和相关可信 membership/checkpoint 材料被一致恶意回滚时无法自证全局 freshness，也不能证明 Relay 没有隐藏尚未锚定的更新。

以后 cursor 增长必须提供全部连续 `rows`，same cursor 必须 same chain，old cursor 或 fork拒绝。失败保持已有 kit anchors；恢复/unwrap还核验 kit 记录的 checkpoint digest 未被替换，与相应已 pin历史manifest绑定且组合manifest仍是本地当前值。recovery传入的chain在任何写入前必须全属于kit.project，再从其pinned anchor连续验证；foreign project、`[own valid transition, foreign transition]`均不得修改任一project或Kit组合anchor。此机制保护已有trusted anchor，仍不能证明 Relay 没隐藏未锚定更新或全trusted files同时被回滚。缺少latest trusted manifest/checkpoint任一部分报 `RECOVERY_FRESHNESS_UNVERIFIABLE`；所有设备和 kit 丢失报 `E2E_DATA_UNRECOVERABLE`。hardware keys、密码重置服务与全 split-view 防护尚未实现。
