# SecureEnvelope v1

状态：冻结实现契约；实现/测试状态以SPRINT_2_REPORT为准。QA ONLY / SYNTHETIC ONLY。

## Wire、AAD 和签名

RH-C14N-1沿用Sprint1：UTF-16 key排序、UTF-8、无Unicode normalization、native number仅safeinteger；科研decimal/integer字符串原样保留。严格JSON拒绝重复key、未知字段、无效Unicode/编码、unsafeinteger。

Suite固定为 `RH-v1/AES256GCM/Ed25519/HPKE-X25519-HKDFSHA256-AES256GCM`。Header精确字段：

| 字段 | 约束 |
| --- | --- |
| envelope_version / protocol_version / schema_version | 均1，未知拒绝 |
| crypto_suite | 上述完整suite标识 |
| record_type | transaction / snapshot / artifact_manifest |
| opaque_project_id / sender_device_id / message_id | 非零lowercase canonicalUUID；opaque project与科研project映射只在客户端 |
| membership_epoch / key_epoch | 正safeinteger |
| semantic_transaction_digest | canonical plaintext SHA256 lowerhex64；名称不授予业务批准 |
| dependencies | sorted uniqueUUID数组 |
| nonce | lowerhex24（12bytes） |
| checkpoint_sequence | 非负safeinteger |

完整wire仅增加ciphertext（canonicalbase64url无padding，AESGCM ciphertext||16byte tag）、ciphertext_digest（SHA256 lowerhex64）、signature（Ed25519 signature64 base64url）。任何字段删改增皆拒绝。

```text
AAD = UTF8("ResearchHub/AEAD/v1\0") || canonical(header)
signature_preimage = UTF8("ResearchHub/SecureEnvelope/v1\0")
                   || canonical(envelope_without_signature)
```

签名覆盖每个header、ciphertext及其digest。AAD与signature分别防密文跨scope与签名metadata替换；不可用signature替代AEAD tag，不能使用公开SHA替代身份认证。公共Relay验证器只使用Ed25519publickey与purecanonical，没有业务decoder或解密API。

## 接收顺序

1. 严格解码/容量/字段/版本/suite检查。
2. 从本地已锚定current或历史manifest查senderpublickey、role/status/prefix；不能用Relay新root自授权。
3. 核验完整signature与ciphertextdigest、scope/epochs/nonceprefix。
4. 仅current授权record解密，拒绝坏tag/wrongkey；未知或旧epoch storedrecord只有验证历史signature/chain后才可transportquarantine，不入Kernel。
5. plaintext bytes须等于重新canonical encoding，digest严格相等；transaction另验证semantic project映射、device/deps/versions及Sprint1schema。
6. 本地principal/grant决定Domain权限；有效签名不等于Human。outerreceipt/cursor/chain与Kernel同QA PG事务提交，完整页失败不前进。

## Identity 与 ACK

新的加密wrapper使用新messageUUID和新预约nonce；transaction/revision identity不变。同messageID同完整bytes返回原Relayreceipt，异bytes拒绝。Kernel仍按semantictransaction幂等，outerRelaysequence不能直接充当Kernelsequence。

RelayStored / DeviceReceived / DeviceDecrypted / KernelApplied / ScientificAccepted / ArtifactPrimaryDurable独立。HTTP200、正确AEAD、Kernel candidate均不等于ScientificAccepted。

## Metadata 泄漏和边界

Relay可见opaqueproject/device、epochs、message/semanticdigest/dependencies关联、大小/时序与retention；科研字段、文件名、HumanConclusion/Audit正文位于ciphertext。防护不解决trustedendpoint compromise、XSS/malware、用户共享、DoS或已撤销设备过去明文。Base HPKE不认证sender，keygrant先验证authoritysignature再unwrap。
