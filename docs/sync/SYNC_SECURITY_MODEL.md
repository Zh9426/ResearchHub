# E2E、权限与设备安全设计

状态：Sprint2已在**合成loopback Secure QA**实现双语言密码、可信生命周期、实际HTTPS Relay及客户端Kernel原子接收。最终安全审查与八Gate以[SPRINT_2_REPORT.md](SPRINT_2_REPORT.md)为准。生产同步账户、OAuth、受保护vault、真实用户presence、移动与公网均NOT IMPLEMENTED。Sprint0明文原型仅保留历史证据。

## Sprint2 已实现范围与规范优先级

正式QA suite为`RH-v1/AES256GCM/Ed25519/HPKE-X25519-HKDFSHA256-AES256GCM`，Python cryptography50.0.2与Node WebCrypto/@hpke/core1.9.0、common1.10.1独立实现。官方来源和维护边界见[选库审查](CRYPTO_LIBRARY_REVIEW.md)，exact字段/AAD/signature以[SecureEnvelope](SYNC_SECURE_ENVELOPE.md)为准。HPKE Base来源认证来自先验已pin authority签名，不能把Base本身当sender认证。

nonce为4byte authority永久唯一设备prefix+8byte持久counter；SQLite FULL/BEGIN IMMEDIATE与append/fsync witness在commit后返回，之后才加密。真实跨语言多进程/重启/强制退出与损坏回归通过，缺失/回滚/溢出fail closed；全部可信材料一致回滚不能自证，恢复必须rotate。重加密new wrapper不改变semantic revision。

生命周期见[密钥与恢复](SYNC_KEY_LIFECYCLE.md)、[配对](SYNC_PAIRING.md)、[checkpoint](SYNC_CHECKPOINTS.md)：旧ACTIVE owner授权连续完整会员链；五分钟/五次持久配对，Ed+HPKE挑战证明两私钥持有；撤销fresh key只给ACTIVE。Recovery Kit公共journal/head与manifest/checkpoint同事务，seed-only不能重获freshness，无server master或密码重置救回内容。已持有旧明文不能收回。

持久SIGNED checkpoint每次读取核严格公共验证上下文、真实验签和digest；局部损坏不得覆写，合法历史creator撤销后旧锚点仍有效。小Artifact fresh DEK/AESKW位于加密签名manifest，64KiB chunks严格AAD/index/size/hash/tag，错误不READY。随机密钥仅内存或明确UNPROTECTED TEST ONLY QA DeviceKeyStore；生产vault/Kit export UI仍未实现。

下列密钥层次和交互段落保留架构历史建议，不能代替上述冻结实现契约。尤其Account Master Key、真实扫码/登录/用户presence仍未实现；当前高熵Recovery Kit不能由账户密码派生。Task3的外层设备认证必须与Sprint1真实QA PostgreSQL的synthetic principal/mock fresh Human grant分别验证，不能以设备签名替代科研授权。

## 威胁模型与内容边界

保护：不受信 Relay/网络不能读取科学 payload、文件名、Audit before/after 或 Artifact bytes；未授权设备不能加入或改写科研状态；重放、密文损坏、未知 schema、越权 AI 不能成为 accepted 数据。假设受信终端可保护私钥且客户端代码未被篡改。被攻破的终端、XSS、已合法读取并复制的内容、拒绝服务不能靠 E2E 消除。

冻结SecureEnvelope的Relay可见字段包括opaque project/device/message、semantic digest/dependencies、epochs、nonce、密文长度/摘要与传输seq，public membership与流量时间仍泄漏关联和活跃度。科研字段/文件名/正文/Artifact DEK位于密文内部；padding未实施。已记住的可信签名checkpoint能检测明显回退/缺页；未锚定消息隐藏、完整split-view及全可信本地材料一致恶意回滚仍无法自证，不承诺绝对防丢。

## 历史架构建议：密钥层次

| 密钥 | 生成/保存/用途 |
| --- | --- |
| Account Master Key | 客户端随机 256-bit；包裹恢复/项目密钥材料，绝不由账号密码直接派生或发送 Relay |
| Device encryption key | 每设备独立，HPKE recipient key；私钥保存在本机受保护 vault，公钥可登记 |
| Device signing key | 每设备独立 Ed25519；签名消息、授权与 snapshot，成员 epoch 绑定；签名不代表 Human 本人确认 |
| Project Key（epoch） | 每项目随机对称内容密钥，给获准设备分别封装；ChangeSet/Audit 内容加密 |
| Artifact DEK | 每个文件独立随机 data key，由项目 key 包裹，支持撤销/epoch/refcount 与大文件分块 |
| Recovery material | 用户离线保存高熵 recovery kit，或另一受信设备恢复；不上传裸密钥，不承诺密码重置可救回 E2E |

候选基于成熟标准：AES-256-GCM 的 AEAD（nonce 唯一、AAD 绑定上下文）、[HPKE RFC 9180](https://www.rfc-editor.org/rfc/rfc9180.html) 的公钥封装（拟选 X25519/HKDF-SHA256/AEAD suite），签名使用 [Ed25519 RFC 8032](https://www.rfc-editor.org/rfc/rfc8032.html)。[NIST SP 800-38D](https://csrc.nist.gov/pubs/sp/800/38/d/final) 说明 GCM；正式库和 suite 需专门审核与测试，不手写密码算法。

历史要求是AEAD的96-bit nonce在同一key下绝不重复，不能相信时间戳；当前已由上文持久prefix/counter+witness实现，exact AAD/signature以冻结SecureEnvelope为准。重加密不改变semantic change_id/revision。Artifact独立nonce、index/长度/manifest/tag校验已在小合成prototype实现，错误不得READY或降级明文；生产大文件恢复仍待后续。

## 历史交互建议与当前限制：配对、撤销和恢复

新手机生成独立 signing/encryption 公钥；Primary 或其他获准受信设备生成短期一次性 challenge/QR，显示双方 fingerprint。人确认匹配、项目范围与角色后通过经审核 HPKE channel 封装所选项目 key，签名 membership grant，并写配对审计。code 需短期、限流、防重放、绑定 session/recipient public key；扫码不等于无限授权。知道账号密码只可登录 Relay 验证身份，不可自动取得密钥。具体二维码交互、SAS 与算法互通 **OPEN QUESTION**。

撤销：签名 membership_epoch 更新，拒绝旧设备新消息，所有剩余设备收到撤销纪要并 rotate 受影响 project keys；旧离线变化持久隔离，人工迁出/审查。撤销不能抹去旧设备已保存的 plaintext/旧 key，也不能瞬间通知离线端。恶意旧端伪造过去 created_at 不能绕过接收 epoch。未来需可信 key transparency/checkpoint 机制减少 Relay 隐藏撤销。

丢设备：另一可信设备/离线 recovery kit 恢复并撤销旧设备；只有账号密码时不能解密。丢密码但 key 仍在时可重新验证账户并保留内容，账号重置不重新派发密钥。所有 key 与 recovery material 都丢失则 E2E 内容不可恢复。恢复密钥保管 UI、轮换周期、旧 Artifact rewrap/重加密与恢复演练仍待批准。

## Human/AI authority

同步外层 device signature 只证明设备，payload 的 actor_type 不是可信身份。Domain decoder 必须校验授权来源、scope、membership 和 Human-only 字段。拟将 final scientific confirmation 绑定对象/完整 heads/字段/transaction，并要求可信客户端 fresh user-presence；离线只能保存 draft/proposal，离线最终确认能力未获准。账号/设备常驻会话不能直接当作这份 Human consent。

Codex/ChatGPT 令牌不持有 Human grant，也不得获得不必要的 E2E project key。AI 可写允许的 proposal/observations 并记 actor/source，不能确认 Human Conclusion、Evidence、Decision、Gate 或模块升级。同步收到的 AI 提案进入独立 Review Inbox。原型只有预登记 synthetic principal 检查，**不是真实登录、人机权限、签名或 user-presence 验收**。

## 生产接入前安全门槛

跨语言canonical/signature vectors、库版本、envelope绑定、nonce崩溃恢复与本地撤销/Kit演练已由Task1/2实现；真实Relay/客户端安全审查、受保护vault、XSS/供应链治理、生产备份与Kit保管仍须生产接入前完成。个人`.env`、GCM、研究文件和原始备份不进入QA；GitHub公开不扩大本地科研数据与凭据边界。
