# E2E、权限与设备安全设计

状态：**DECIDED（算法与边界推荐）/ OPEN QUESTION（具体实现及安全审核）**。本轮 **NOT IMPLEMENTED** 真实账户加密、密钥管理、签名、OAuth、配对、撤销或云端服务。原型全部是明文 synthetic data。

## 威胁模型与内容边界

保护：不受信 Relay/网络不能读取科学 payload、文件名、Audit before/after 或 Artifact bytes；未授权设备不能加入或改写科研状态；重放、密文损坏、未知 schema、越权 AI 不能成为 accepted 数据。假设受信终端可保护私钥且客户端代码未被篡改。被攻破的终端、XSS、已合法读取并复制的内容、拒绝服务不能靠 E2E 消除。

Relay 可见 opaque project/object/device/revision/parent 标识、seq、成员、流量大小与时间；这些会泄漏关联、活跃度和对象数量。可评估 padding/批次延迟，但本轮不承诺隐藏流量。Relay 若丢弃/回滚 tail，客户端验证已记住的签名 checkpoint；尚未锚定的设备仍可能被隐藏新事件，完整反分叉/可用性证明是未决工程，不夸大为绝对防丢。

## 密钥层次（推荐）

| 密钥 | 生成/保存/用途 |
| --- | --- |
| Account Master Key | 客户端随机 256-bit；包裹恢复/项目密钥材料，绝不由账号密码直接派生或发送 Relay |
| Device encryption key | 每设备独立，HPKE recipient key；私钥保存在本机受保护 vault，公钥可登记 |
| Device signing key | 每设备独立 Ed25519；签名消息、授权与 snapshot，成员 epoch 绑定；签名不代表 Human 本人确认 |
| Project Key（epoch） | 每项目随机对称内容密钥，给获准设备分别封装；ChangeSet/Audit 内容加密 |
| Artifact DEK | 每个文件独立随机 data key，由项目 key 包裹，支持撤销/epoch/refcount 与大文件分块 |
| Recovery material | 用户离线保存高熵 recovery kit，或另一受信设备恢复；不上传裸密钥，不承诺密码重置可救回 E2E |

候选基于成熟标准：AES-256-GCM 的 AEAD（nonce 唯一、AAD 绑定上下文）、[HPKE RFC 9180](https://www.rfc-editor.org/rfc/rfc9180.html) 的公钥封装（拟选 X25519/HKDF-SHA256/AEAD suite），签名使用 [Ed25519 RFC 8032](https://www.rfc-editor.org/rfc/rfc8032.html)。[NIST SP 800-38D](https://csrc.nist.gov/pubs/sp/800/38/d/final) 说明 GCM；正式库和 suite 需专门审核与测试，不手写密码算法。

AEAD 的 96-bit nonce 必须在同一 key 下不重复；按设备/epoch 的派生子键与持久 counter、并行写入/恢复/rotation 的 nonce 策略待定并需审核，不能仅相信时间戳。AAD 包括 project/object/revision/transaction/schema/key epoch，签名还绑定父集合和密文摘要；重加密不改变语义 change_id/revision。Artifact chunk 独立 nonce 与 index/长度/manifest 校验，错误 key 或 tag 均进入隔离，不降级明文。

## 配对、撤销和恢复

新手机生成独立 signing/encryption 公钥；Primary 或其他获准受信设备生成短期一次性 challenge/QR，显示双方 fingerprint。人确认匹配、项目范围与角色后通过经审核 HPKE channel 封装所选项目 key，签名 membership grant，并写配对审计。code 需短期、限流、防重放、绑定 session/recipient public key；扫码不等于无限授权。知道账号密码只可登录 Relay 验证身份，不可自动取得密钥。具体二维码交互、SAS 与算法互通 **OPEN QUESTION**。

撤销：签名 membership_epoch 更新，拒绝旧设备新消息，所有剩余设备收到撤销纪要并 rotate 受影响 project keys；旧离线变化持久隔离，人工迁出/审查。撤销不能抹去旧设备已保存的 plaintext/旧 key，也不能瞬间通知离线端。恶意旧端伪造过去 created_at 不能绕过接收 epoch。未来需可信 key transparency/checkpoint 机制减少 Relay 隐藏撤销。

丢设备：另一可信设备/离线 recovery kit 恢复并撤销旧设备；只有账号密码时不能解密。丢密码但 key 仍在时可重新验证账户并保留内容，账号重置不重新派发密钥。所有 key 与 recovery material 都丢失则 E2E 内容不可恢复。恢复密钥保管 UI、轮换周期、旧 Artifact rewrap/重加密与恢复演练仍待批准。

## Human/AI authority

同步外层 device signature 只证明设备，payload 的 actor_type 不是可信身份。Domain decoder 必须校验授权来源、scope、membership 和 Human-only 字段。拟将 final scientific confirmation 绑定对象/完整 heads/字段/transaction，并要求可信客户端 fresh user-presence；离线只能保存 draft/proposal，离线最终确认能力未获准。账号/设备常驻会话不能直接当作这份 Human consent。

Codex/ChatGPT 令牌不持有 Human grant，也不得获得不必要的 E2E project key。AI 可写允许的 proposal/observations 并记 actor/source，不能确认 Human Conclusion、Evidence、Decision、Gate 或模块升级。同步收到的 AI 提案进入独立 Review Inbox。原型只有预登记 synthetic principal 检查，**不是真实登录、人机权限、签名或 user-presence 验收**。

## 实施前安全门槛

正式实现前确定跨语言 canonical encoding/签名 test vectors、库版本及维护方案、认证与 envelope 绑定、密钥 vault、nonce 崩溃恢复、XSS/供应链保护、撤销轮换演练、备份密文与 recovery kit。个人 `.env`、GCM、研究文件和原始备份不进入该设计 prototype；GitHub 公开不影响本地 E2E 内容边界。
