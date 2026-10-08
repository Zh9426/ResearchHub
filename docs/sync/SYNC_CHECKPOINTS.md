# Checkpoint / Rollback Detection / Snapshot Manifest

状态：Task 2 纯公共 chain/checkpoint 校验、SQLite monotone anchor 和最小 encrypted snapshot prototype 已实现；Task 3B 另实现 QA client PG/Kernel 同 Session adapter，实际验证记录见 `SPRINT_2_TASK3B_QA.md`。完整transparency/keytransparency/gossip/split-view防护NOT IMPLEMENTED。

## 持久锚点

每Relay消息有连续perprojectseq与完整envelopehash：

```text
chain_digest[n] = SHA256(canonical({previous_digest, sequence, envelope_digest}))
chain_digest[0] = 64 lowerhex zeroes（所有cursor0 checkpoint/pin/chain起点均强制此值）
```

可信ACTIVEdevice签checkpoint，绑定opaqueproject、membership/keyepoch、cursor、chain_digest与creator。签名有独立domainseparator；client从可信manifest取得publickey，不能接受Relay自签checkpoint。

client持久lastverifiedcursor/chain/checkpointanchor。oldercursor或同cursor异hash拒绝ROLLBACK_DETECTED；tail须从本地链起连续验证完整page。缺seq、截断page、错nextcursor、坏signature/hash/epoch不得advance。接收同完整page允许幂等，不能重复Kernel事件。

## 与 Kernel 的原子性

整页预验之后，outerreceipt/cursor/chain和Kernel `apply_in_session(relay_seq=None)`同客户端QA PG事务提交。commit前kill全部rollback，commit后kill重放不多Audit/revision。历史epoch按已pin历史manifest认证后持久transportquarantine，不解释旧mutation；不能因为“旧消息”跳过坏签名或gap。

RelayStored、DeviceDecrypted、KernelApplied与ScientificAccepted区别记录，candidate/quarantine不能伪装scientificwatermarkadvance。Relay假200或签名合法但grant不合法的设备不获得Human权限。

## Snapshot 最小 prototype

manifest包含opaqueproject、snapshotcursor、module_snapshot_hash、state_digest、keyepoch、creator，可信device签名并作为snapshotrecord加密。验证manifest内容/signature/epoch/cursor/checkpointbinding后才认可；不实现整个状态bootstrap、500k重建或压缩清理。

新device需要trustedpair提供root/currentmanifest和checkpointanchor。没有独立anchor，无法证明Relay没隐藏更晚消息；单client无法证明另一client未收到splitview。全trustedstate恶意同时rollback、未锚定新消息隐藏、DoS不是本轮能保证的事项。Recoverykit的trusted最新anchor丢失必须报freshness错误，不靠墙上时钟。

## Task 2 实际 API

纯公共 Python `packages/secure_wire/checkpoint.py` 提供 `extend_chain(previous_digest, cursor, rows)`、`verify_checkpoint`、`verify_advance`。rows exact shape 为 `{sequence, envelope_digest}`，每页最多 100；必须从本地 cursor+1 连续。`envelope_digest` 是完整 canonical SecureEnvelope 的 SHA256（含 ciphertext/signature）。调用方要先完整验证 envelope，不能把 Relay 提供的 digest 自认可信。

checkpoint exact fields：`version, opaque_project_id, membership_epoch, key_epoch, cursor, chain_digest, creator_device_id, signature`；安全整数严格拒绝 bool/unsafe/negative。cursor0 必须 zero64 chain digest，`extend_chain`、`verify_checkpoint`、`CheckpointStore.pin` 均执行同一 genesis 规则，合法签名的非零 genesis 也拒绝。domain 为 `ResearchHub/Checkpoint/v1\0`，signature 覆盖除 signature 外全部字段；creator 从受信当前 manifest 的 ACTIVE member 获取。`verify_advance` 拒绝 older cursor、same cursor wrong chain、membership epoch 或 key epoch 任一回退、context mismatch、坏 candidate 签名、缺 sequence、最终 chain mismatch；同 cursor 或 cursor 增长均不能降低任一 epoch。exact 相同 checkpoint + 空 rows 可幂等确认。

trusted Python `CheckpointStore`（Node 同名）用 TEST ONLY FULL SQLite 持久 opaque project/cursor/chain/signed checkpoint，`pin` 必须来自本地 trusted bootstrap/pairing，不能接受 Relay 单独提供的“最新根”；`get` / `advance` 重启后保留 monotone anchor。此 SQLite 接口只验证并持久 transport anchor，不与 QA PG Kernel apply 同事务；Task 3B 使用下述独立 PG adapter，不能把 Task 2 单测当作网络服务/Kernel 验收。

Task 3B 的 `transport_pg.Trust` 保存完整根 pin/连续签名 history、outer cursor/chain 与 signed checkpoint；`receiver.checked_anchor` 每次从可信完整 history 取历史 creator 验签，再核对 PG 行 cursor/chain/project。没有 checkpoint 仅在 cursor=0 且 zero chain 的显式本地初始化成立。`receiver.receive` 持同一 Trust 行锁先预验全页，调用 Kernel `apply_in_session(relay_seq=None)`，最后同 Session 保存 `sign_checkpoint(current_manifest, local_device, cursor, chain)`；后续 membership 更新不能插入这个锁窗口。`SecureTransport.accept_checkpoint` 只接受当前 verified manifest 签名且 cursor/chain 精确匹配本地已消费位置的 checkpoint，旧位置、同位置错误 chain、旧双 epoch 或未消费的新位置拒绝，不用 remote checkpoint 跳过缺失消息。

`verify_advance(anchor, checkpoint, manifest, rows, *, bootstrap=False)`（Node 第5参数 `bootstrap=false`）默认要求完整 strict signed anchor，包括两个 safe integer epochs、creator UUID、signature 编码；这里 anchor 必须此前已由调用方认证，`validate_anchor/validateAnchor` 仅做结构校验，candidate 仍完整验签。只允许可信初次 pin 调用显式 `bootstrap=True` / `true`，此时 anchor 必须精确为 `{opaque_project_id, cursor, chain_digest}`。字段缺失不能自动推断初次状态。

SQLite anchors 独立保存 `kind=BOOTSTRAP|SIGNED`。`pin` 写 BOOTSTRAP，首次成功 `advance` 同事务保存完整 checkpoint 并改为 SIGNED；之后 `get/advance` 按持久 kind 检查 exact schema，删任一 epoch/signature，甚至删成三字段，都不能退化为 bootstrap。无 kind 的旧 QA schema 以 `CHECKPOINT_STORE_KIND_REQUIRED` 拒绝，不根据不完整 body 自动迁移或重新授信。需从可信材料重新建 QA store；生产迁移 UX 未实现。kind 与 anchor 同属可信本地材料，不能抵御二者及其他可信状态一致恶意回滚。

SIGNED 行还保存 exact 公共 verification context：`version, opaque_project_id, membership_epoch, key_epoch, creator_device_id, signing_public_key, checkpoint_digest`。creator 公钥只在 candidate 已通过受信 manifest 验证后取得，与 checkpoint body/kind 在同一 SQLite 提交中保存。每次 `get` 和 `advance` 读取旧锚点，先核对字段、types、scope/epochs/creator，再用保存的公钥执行成熟 Ed25519 实现的真实签名验证，最后核对完整 checkpoint digest；不是把 signature 编码或 digest 匹配当作认证。缺 context、缺/多字段、公钥或绑定损坏、坏签名均 fail closed，失败不得覆写旧锚点。即使 body 被改为 cursor0/zero64，或坏签名的 digest 被重算，也不能重新授信。

该公钥来自此前可信提交，不由当前坏 checkpoint 自造；旧 checkpoint 的 creator 后来被撤销、当前 epochs 已增长时，仍可验证其历史签名并作为 monotone 起点，新 candidate 仍按当前 manifest 验证。Node `CheckpointStore.get(project, db?)` 现在返回 `Promise<PublicObject>`，包括 Kit 初始化接入在内的所有调用方必须 `await`；Python `get` 保持同步。已有 kind 但缺 verification 列的旧 QA schema 以 `CHECKPOINT_VERIFICATION_CONTEXT_REQUIRED` 拒绝，不静默迁移；BOOTSTRAP 行的 verification 必须为 NULL。context/body/kind 均为本地可信公共材料，三者和其他可信锚点一起一致恶意替换或回滚的局限不变，没有引入生产 vault 或独立 witness。

`snapshot_record` / `verify_snapshot_record` / `seal_snapshot` / `open_snapshot`（Node camelCase）实现最小原型。inner signed manifest exact fields：`version, opaque_project_id, snapshot_cursor, checkpoint_digest, module_snapshot_hash, state_digest, key_epoch, creator_device_id, signature`；snapshot record exact shape 为 `{manifest, state}`。domain `ResearchHub/SnapshotManifest/v1\0`。外层 SecureEnvelope record_type 为 snapshot，绑定 sender/双 epoch/prefix/cursor 并加密全部内容；开包检查 current authority、内层签名、state canonical digest、expected module hash、精确 trusted checkpoint digest/cursor、内外 creator 一致，任何 corruption fail closed。全量状态 bootstrap、500k 重建和压缩清理尚未实现。

## Small Artifact framing prototype

Python `artifacts.py` / Node `artifacts.ts` 实现独立互操作 `seal_artifact` / `open_artifact`。输入为 bounded bytes iterable，最大 1 MiB、最多 16 chunk、每 chunk 1..64 KiB；超过上限在迭代时立即拒绝，未来 10GB streaming path 尚未实现，不能把此 bounded prototype 宣称为生产 MAT importer。`StagingSink` boundary 提供 begin/write/commit/abort，TEST ONLY memory sink仅用于上述上限。

每 artifact fresh random 32 byte DEK；DEK 以 AES-KW 用当前 Project Key wrapping，并且仅在 **signed + encrypted artifact_manifest** 内。inner fields：`version, opaque_project_id, opaque_locator, key_epoch, creator_device_id, total_size, total_chunks, plaintext_digest, chunk_sizes, metadata, wrapped_dek, nonce_prefix, signature`。metadata `{filename, category, run_title}` 均在 ciphertext，Unicode scalar 文本各最多1024。domain `ResearchHub/ArtifactManifest/v1\0`，opaque locator 与外 envelope message_id 一致。

chunk fields：`opaque_project_id, opaque_locator, key_epoch, index, total, size, manifest_identity, nonce, ciphertext`。AAD 为 `ResearchHub/ArtifactChunk/v1\0 || canonical(all chunk fields except nonce/ciphertext)`；manifest_identity 是完整 signed inner manifest SHA256。nonce 从 Task 1 durable NonceVault 按 fresh DEK/prefix 注册、预约，不能用 memory counter 重启重置。chunk bytes 与 metadata/signature不可分离替换。

接收端先验 outer/inner signatures、epoch/creator、unwrap DEK，再严格检验 integer/schema/order/count/size/manifest identity、nonce prefix/counter/uniqueness、AEAD tag、整文件 size/SHA256。任一失败 abort staging，全部通过后才 commit READY。exact cached ciphertext bundle retry 零二次 write；同 locator 的不同 bundle 不被当作 exact retry。locator、epoch、chunk count、每 chunk size、活动时间和签名相关 identity 是可见 metadata leakage；filename/category/run_title 不公开。无 MinIO、OPFS 或真实科研文件集成。
