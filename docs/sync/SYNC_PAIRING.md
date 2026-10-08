# QA Trusted Pairing

状态：Task 2 trusted-client QA text protocol 已实现；无相机/实体手机/userpresence验收。

1. 新设备本地生成两种私钥，公布UUID、Ed/X25519publickeys与fingerprint。
2. 可信owner从本地pinnedmanifest创建challenge：5分钟、单session、selectedproject、recipient两公钥/fingerprint、role、currentmanifestdigest及randomchallengeidentity全部签名。
3. 双方核对文本QR/SAS、fingerprint、project、role；明确确认记录参与协议，但不冒充系统级userpresence。
4. recipient签名possessionproof绑定完整challenge；owner核验recipientkeys、scope、expiry、attemptcount≤5、未消费和currentmanifestdigest。
5. trustedclient一个持久事务消费challenge、保存新manifesttransition、签名grant/wrappedkeyreceipt。exactretry返回同原receipt，changedscope拒绝；crash不留下消费但没grant或grant未消费状态。
6. recipient先用预先可信owneranchor验证challenge/transition/grantsignature、自己的recipient/session/role/project/epoch，再HPKEunwrap；Relay提供的新root不能通过。

Relay只转存公开签名材料，无私钥或projectkey。用户名/密码、deviceUUID、猜到challenge、重放他人的QR均不授予projectkey。撤销后旧pairing exactretry也不得再取receipt或重新激活。

必须测试expiry、重复、错误project/device/pubkey/fingerprint/role/session、所有字段篡改、错误proof五次限额、崩溃原子恢复及撤销后重放。科学Humangrant仍由Sprint1受信QA签发；pairingconfirmation不批准HumanConclusion、Gate或Evidence。

## 实际 API 与原子性

Python `pairing.py` / Node `pairing.ts` 对应接口：`create_challenge`, `confirmation`, `answer_challenge`, `consume`, `retry_receipt`（Node camelCase）。所有动作是 trusted client，Relay 不签 grant，也不拥有 plaintext Project Key。

Node `retryReceipt` 现在与其他权威入口一致返回 `Promise`，调用方必须 `await retryReceipt(store, challenge, recipientId)`。challenge 创建、consume 和 receipt 重取都先从本地独立 pinned roots 验证完整签名 membership history；同事务操作复用已有 connection，不用同步结构 getter 作授权。Python 对应入口也验证全链。本地 history 的 SQL列/body/digest/epoch 不一致或 matching digest 的坏签名属于存储/信任失败，必须在 proof attempt 计数前逸出并 rollback，不能当作一次 recipient proof 失败；合法坏 proof 仍按原五次限额持久计数。回归检查此类历史错误不会新增 challenge、消费 attempt 或改变/返回 receipt。

challenge exact fields：`version, session_id, opaque_project_id, manifest_digest, membership_epoch, key_epoch, authority_device_id, recipient, issued_at, expires_at, wrapped_challenge, sas, signature`。`recipient` 包含完整两公钥、fingerprint、role、永久 prefix、status/date。SAS 为未含 sas/signature 的 challenge canonical SHA256 的前 12 lowerhex。签名 domain 为 `ResearchHub/PairingChallenge/v1\0`，覆盖 sas 和所有 scope。固定五分钟；`issued_at <= now < expires_at`，墙上时钟只是本地短 session 过期检查，不授权历史科学 mutation。

`wrapped_challenge` 是每 session 独立随机 32 byte challenge，经标准 HPKE 且绑定完整七字段 context 加密给目标 X25519 public key；owner 本地仅持久其 SHA256。proof 中 response 是一次性公开挑战答案，不是 Project Key。recipient 提供 Ed25519 signed `PairingProof`：`challenge_digest, challenge_response, confirmation, signature`，domain `ResearchHub/PairingProof/v1\0`。confirmation 必须精确等于 `{fingerprint, opaque_project_id, role, sas}`。随机 response 的 unwrap 确认 X25519 私钥，proof signature 确认 Ed25519 私钥；猜 UUID/SAS 或只有一种私钥不够。

最多五次尝试在 SQLite 中跨重启保留。`consume` 对 local stored exact challenge 作绑定，重新校验旧 pinned manifest、authority/scope/expiry、两种 possession、确认文本；proof validation 失败仅持久 attempts。成功后一个 FULL SQLite transaction 中保存新 manifest、signed wrapped grant receipt 和 used 状态；任何 persistence error 回滚，不允许只激活或只消费。receipt exact fields 为 `challenge_digest, manifest, grant`。

`consume` 第二次调用一律 `PAIRING_USED`，满足 CASE K。显式 `retry_receipt` 是不同接口，仅 exact stored challenge + exact recipient UUID 可读原 immutable receipt；还要求 recipient 当前仍 ACTIVE、原 role/pubkeys/prefix 不变且 key epoch 仍授权。scope/session 替换、撤销后 retry、旧 key epoch retry均拒绝，不进行第二次 activation。receipt 验证后才能由 recipient `open_grant`。

本轮 `crash_point=before_commit/after_commit`（Node `crashPoint`）是**异常注入的事务边界单测**，已证明 rollback/原 receipt 查询及重启读盘；尚不等价于真实 process kill、网络 ACK loss 或 Relay restart 验收。相关网络/PG adapter 在后续 Task 3 独立完成。QA 文本确认也不宣称真实 user-presence。
