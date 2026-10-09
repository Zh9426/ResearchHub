# Sprint 3B 固定 v2 向量

全部为合成数据。envelope.TEST_ONLY.json 的密钥是公开确定性 TEST ONLY 输入，严禁生产使用。

protocol.json 的规范 JSON 与 SHA-256 预期由标准 JSON 排序/紧凑 UTF-8 编码独立计算（本组数据没有科学数值歧义）；envelope.TEST_ONLY.json 使用 cryptography 的 AESGCM/Ed25519 直接生成，未调用产品 seal 或 validator。Python、Node 独立读取同一固定预期；浏览器后续直接复用。signed_inner_outer_mismatch 是密码学有效而版本绑定无效的拒绝用例。

原 fixtures/sync/v1 与 secure-v1 未修改。新版只接受 (2,2) 的 Run/Note；混合版本、错误字段类型、unknown field、成员 schema 与 actor 绑定等拒绝用例留存。这里只是协议与密码单元证据，不代表浏览器、PostgreSQL 或 HTTPS 集成已经验收。
