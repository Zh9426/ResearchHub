# Sprint 2 密码库调查

状态：**SELECTED**，2026-10-07。这是标准库选型与 QA 互操作的前置评审，不代表 ResearchHub 协议已经外部安全审计。尚未运行本轮 crypto 验收，结果须另外记录。

## 选型比较

| 候选 | 维护、兼容与许可证 | 决定 |
| --- | --- | --- |
| Python cryptography 50.0.2 + Node WebCrypto + @hpke/core 1.9.0 | Python 本机已安装50.0.2；官方版本/平台文档覆盖Python3.12/Windows。Python Apache-2.0/BSD，hpke-js MIT；标准AES-GCM、Ed25519、RFC9180，Node24兼容 | **SELECTED**；npm实际解析树须核对并锁定，core必须≥1.7.5 |
| Python pyhpke 0.6.5 + hpke-js | 支持RFC9180四模式，MIT，依赖cryptography；官方明确没有正式审计 | 不增加这个依赖，采用cryptography已提供的原生HPKE单次API |
| PyNaCl 1.6.2 + libsodium-wrappers 0.8.4 | PyNaCl Apache-2.0、sodium ISC；XChaCha20/Ed25519成熟实现，sealed-box为匿名发送 | 不选择；不能把sealed-box称authenticated HPKE，也不自行拼新的密钥分发协议 |

选型来源：[cryptography发布记录](https://cryptography.io/en/stable/changelog/)、[平台支持](https://cryptography.io/en/50.0.2/installation/)、[许可](https://github.com/pyca/cryptography/blob/main/LICENSE)、[hpke-js发布](https://github.com/dajiaji/hpke-js/releases)、[hpke-js许可](https://github.com/dajiaji/hpke-js/blob/main/LICENSE)、[PyHPKE官方](https://github.com/dajiaji/pyhpke)、[PyNaCl变更](https://pynacl.readthedocs.io/en/latest/changelog/)、[libsodium wrapper发布](https://github.com/jedisct1/libsodium.js/releases)。检索发生在本轮，锁文件实际版本与测试才是实现证据。

## 冻结 primitive suite

- 正文：AES-256-GCM，32-byte key、12-byte nonce、128-bit tag，返回ciphertext||tag。Python AESGCM / Node WebCrypto AES-GCM。
- 签名：普通Ed25519（RFC8032），32-byte raw seed、公钥32、签名64；不使用ph/ctx变体。导入导出由库处理。
- Recipient wrapping：RFC9180 Base mode=0，DHKEM(X25519,HKDF-SHA256) 0x0020 / HKDF-SHA256 0x0001 / AES-256-GCM 0x0002。Python Suite one-shot / TS CipherSuite新context只seal一次。
- HPKE bytes为enc||ct（enc32字节）；info为canonical wrapping context，HPKE aad为空。Base不认证sender，签名membership grant认证授权来源并绑定完整wrapped bytes与recipient/context，先验受信签名再unwrap；不称HPKE Auth。
- Artifact DEK包裹：库实现AES-KW（RFC3394）；context由已签名并加密的manifest绑定。CSPRNG使用OS/库，不实现RNG/KDF/曲线或密码算法。

依据：[Python HPKE](https://cryptography.io/en/50.0.2/hazmat/primitives/hpke/)、[Python AEAD](https://cryptography.io/en/50.0.2/hazmat/primitives/aead/)、[Node WebCrypto](https://nodejs.org/download/release/v24.15.0/docs/api/webcrypto.html)、[RFC9180](https://www.rfc-editor.org/rfc/rfc9180.html)、[RFC8032](https://www.rfc-editor.org/rfc/rfc8032.html)、[RFC3394](https://www.rfc-editor.org/rfc/rfc3394.html)。未来浏览器可使用WebCrypto，但本轮不验收浏览器vault或实体设备。

## 安全公告与限制

hpke-js [GHSA-73g8-5h73-26h4](https://github.com/dajiaji/hpke-js/security/advisories/GHSA-73g8-5h73-26h4) 指出旧core并发seal会复用nonce；1.7.5已修复。仍禁止复用/并发调用/持久恢复HPKE context，只采用one-shot fresh ephemeral wrapping。检查lockfile而非只看umbrella版本。

cryptography的[安全公告](https://github.com/pyca/cryptography/security/advisories)与changelog记录历史修复；未查见某primitive专项公告不能证明无漏洞。其官方和hpke-js均不提供整个ResearchHub协议已审核的保证，hazmat接口仍需正确context/nonce/权限边界。

当前Node24.15仅用于合成QA，不以它的Permission Model隔离秘密；后续真实数据使用前需重新核对支持线安全patch。[Node2026-07安全发布](https://nodejs.org/en/blog/vulnerability/july-2026-security-releases)记录旧版本权限绕过修复。本轮Relay独立容器不挂载客户端vault、密钥或科研文件。

## 库 gate 的后续验证

npm registry 已实际查询：2026-10-07 latest `@hpke/core=1.9.0`，MIT，Node>=16，依赖`@hpke/common ^1.10.0`。原候选1.8.0仍存在，但本轮采用精确1.9.0及lockfile冻结传递树；不能依据GitHub release页面缺少tag就假设npm也没有该版本。尚未安装或执行互操作，执行结果另列。

两端必须独立运行AES encrypt/decrypt、Ed sign/verify、HPKE wrap/unwrap，固定公开TEST ONLY向量与运行时随机材料都验收；错误key/info/project/epoch/tag/signature拒绝。生成的私钥仅在内存或忽略的临时vault，测试日志不打印。若实际版本/API/互操作失败，gate改BLOCKED，不能放宽校验或自实现primitive。
