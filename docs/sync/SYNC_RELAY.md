# Secure Relay QA

状态：Task3A 独立 QA Relay 已实施，spec复审PASS、quality/security APPROVED。初审隐私扫描假阴性及两项bool/int绑定问题已实际RED→GREEN，两个独立审查各自完整55项通过；版本2审计含真实DB泄漏对照及全部bytea原值读取。实际过程与旧证据撤回见 [SPRINT_2_TASK3A_QA.md](SPRINT_2_TASK3A_QA.md)。Task3B客户端Kernel集成与Sprint2最终八项Gate仍待完成。SYNTHETIC / LOOPBACK ONLY。

## 隔离与部署边界

Relay专用PG `researchhub_secure_relay_qa / researchhub_relay_qa`，loopback35434、container `researchhub-secure-relay-pg`，label `researchhub.qa.scope=secure-relay-s2`。`HUB_RELAY_QA=1`与实际DB/role校验必须同时满足，不能回退产品DATABASE_URL。初始化工具`python scripts/secure-relay-qa.py --init`只创建/启动该label容器，随机credentials位于被忽略.env与storage/runtime配置，命令不输出password。

Relay运行环境只安装publicwire/Ed25519public verification和服务依赖，不含Domain decoder、client crypto/vault或研究文件。client私钥/projectkeys不在Relay mounts/image/env。TLSserverprivatekey是传输身份的明确例外，只挂载临时servercert/key；CA签发私钥和clientkeys不交给Relay。

本轮HTTPS证书由临时QA CA签发，SAN=127.0.0.1。客户端实际CA/hostnameverification，错误CA/hostname失败；没有verify=False或明文fallback。公网/DNS/tunnel/VPS/cloud/OAuth/mobile/ChatGPT均NOT IMPLEMENTED。

### 回环入口的实际网络前置验证

2026-10-08 使用已存在的合成 QA 镜像创建独立带 scope label 的临时 TCP 探针，仅接 `researchhub-secure-relay-qa` internal network 并发布 `127.0.0.1:38002`。实际 host socket 在重试窗口内无法连接；探针容器随后按 label 核验并删除，未碰个人服务。现有 PG 同时连 default bridge，因此其35434 host访问不能作为“internal-only端口可发布”的证据。

[Docker 官方 internal network 说明](https://docs.docker.com/reference/cli/docker/network/create/#network-internal-mode---internal)指出该模式不配置默认外部路由；host通信还取决于网关与平台端口转发。[端口发布文档](https://docs.docker.com/engine/network/port-publishing/)描述了明确绑定127.0.0.1及internal/isolated网关区别。当前机器Docker29.8.2，不改变全局daemon或firewall。

Task 3A 已实现并实测固定目标入口：Relay 只连内部 QA data 网络；无 TLS/client keys 的 TCP ingress 双连专用 transport/data 网络，仅将 127.0.0.1:38001 转发到 Relay TLS8443。TLS 终止与 CA/hostname 验证仍在 Relay/client。入口不解密 TLS、不解析 Domain、不挂 client vault/Docker socket。实际 guard、TLS、进程 kill/restart 与隐私结果见 Task 3A QA 记录；没有改为持有全部客户端文件权限的 host Relay 或公开监听。

## API 与身份

Hello、messages push/pull、ack、publicmembership/pairing/checkpoint和opaquechunk接口只接严格scope字段。signedrequest proof绑定method/path、opaqueproject/device、currentmembershipepoch、body/query和requestUUID；不能凭deviceUUID读密文。publicregistry来源必须是已可信authority签名transition；reader不可mutation，revoked不可新请求。

新push验证currentmanifest、senderrole、signature/ciphertextdigest/nonceprefix、currentepoch及exactfield/suite。旧timestamp不提供授权，unknownsuite/downgrade/malformed一律拒绝。

请求512KiB、envelope256KiB、page≤100、chunk≤64KiB、projectpendingciphertext≤16MiB；显式rate window/timeout/batch限制。无SQL或filesystempath来自用户输入的执行入口。稳定errorcode，不向HTTP/log写payload、wrappedbytes、SQLstack或keys。

2026-10-08 HTTP补审冻结：exact proof/audience/60秒过去与5秒未来窗口、immutable GET原响应、current authorization先于全部receipt、recovery限定profile、Relay pairing不能冒充X25519 possession、实际cipher字节quota及独立cache预算、未认证统一AUTH_REJECTED详见SPRINT_2_SECURITY_DELTA“HTTP身份实施前补充冻结”与ADR-026。该补审为DESIGN PASS WITH CONDITIONS，不是Task3代码或网络PASS；实施不得仅用request UUID作为永久bearer凭据。

## Durable storage / retry

PG项目行锁下原子分配perprojectseq、保存完整ciphertext/metadata/hash/receipt，synchronouscommit后才RELAY_STORED ACK。同messageID同完整bytes返originalreceipt，异bytes拒绝。新messageID相同keyepoch/nonce拒绝；合法reencrypt新nonce/newwrapperID，Kernelsemantictransaction仍一次。

Pullpage包含完整envelope、continuoussequence与chain；partial/gap/incorrectnextcursor拒绝，不切开单message。client先验整page，再在同一QA Kernel PG事务中写transportreceipt/cursor/chain及调用apply_in_session(relay_seq=None)。rollback整页无advance，duplicatewrapper不新增innersequence。旧epoch历史只在验证已pin历史manifest/chain后transportquarantine，不当科研accepted。

ACKstage分RELAY_STORED、DEVICE_RECEIVED、DEVICE_DECRYPTED、KERNEL_APPLIED、SCIENTIFIC_ACCEPTED、ARTIFACT_PRIMARY_DURABLE。设备后续声明不让Relay成为科研裁决者，不返回笼统synced=true。retain_until_ack仅保存metadata，未实现GC/compaction/harddelete。

## 真实故障与隐私验收

必须实际TLS半上传/上传后disconnect、commit前kill、commit后ACK前kill、ACKloss、duplicatePOST/GET、partialpage、outoforderretry、Relayrestart、PGrestart及clientcommit前后kill。核验完整PGreceipt/seq/ciphertext、同receipt重试和Kernel/Audit幂等；仅异常注入不抵充真实进程/network测试。

直接dumpRelayPG、扫描全部Relaypersistedfiles/logs，搜索每种syntheticresearchmarker以及所有runtimeproject/device/recoveryprivatekey的raw/hex/base64表示；0hits才ConfidentialityPASS。公共TESTONLYfixedvectors不得挂载Relay；TLSprivatekey与PGpassword另有明确传输/服务权限范围，不混称projectkey。

Relay可主动丢弃/回滚/重排密文，客户端现有anchor只检测明显rollback/gaps/伪造；availability、完整splitview、隐藏未锚定消息、trustedendpointcompromise不在保障范围。
