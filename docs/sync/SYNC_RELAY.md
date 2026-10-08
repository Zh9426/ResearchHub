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

## Task 3B 实际可信客户端

`apps/api/researchhub/sync/secure/transport.py` 使用固定、CA/hostname 验证的 loopback HTTPS；成熟 httpx 流式接收累计最多 524288 bytes，不信 Content-Length，不接受压缩响应。response body 使用不重聚合的 `iter_raw()`，每次底层 chunk 与 EOF 检查 15 秒 body deadline；单次 socket read timeout 也为 15 秒，因此阻塞读取可能使检查比 deadline 晚至一个 read timeout 加调度误差。它不是含 connect/TLS/headers 的严格 15 秒总请求上限，也不是完整 DoS 防护。直接 receive 输入在 canonical 编码前后同样检查预算。边界单元测试使用真正 httpx Response/SyncByteStream 与模拟时钟，只证明库迭代/限额逻辑；实际服务验收由独立 HTTPS/PG 测试完成。

`transport_pg.py` 的 outbox 保存完整 immutable canonical envelope bytes；proof 每次 fresh UUID/time 并使用当时持锁读取的当前 manifest，重复请求不会 seal 或烧新 nonce。S1 client PG 仅精确隔离的 35433/database/role，拒绝 URL query 覆盖、缺密码及产品连接回退。trusted history 与 receive 外层状态同 PG 行锁，完整根 pin/transition history 在读取时复验，更新不能穿过预验证到 commit 的锁窗口。

`receiver.py` 完整 page 通过 crypto/映射预验证后才调用既有 `apply_in_session(relay_seq=None)`；同事务写入 outer receipt/cursor/chain 与新 signed checkpoint。旧 page 必须核对已持久原 bytes/digest/chain，不能只见 cursor 小就忽略；新 wrapper 同 SemTx 不增加 Kernel Audit/inner seq。历史合法项只 transport quarantine；无效 AEAD/签名/digest/history/gap 均整页回滚。checkpoint 保存完整签名并按已 pin 的历史 creator 验签，远端 checkpoint 不得跳过未消费历史。

fresh mock HumanGrant 与注册 principal 继续遵循 Sprint 1；传输签名不自授 Human。客户端 ACK 表示 `DEVICE_DECRYPTED`，包括可解密且已持久的 candidate/quarantine；不发自动 `SCIENTIFIC_ACCEPTED`。实际子进程 kill 前后、错误矩阵与网络测量见 [Task 3B QA](SPRINT_2_TASK3B_QA.md)。

完整 `scripts/secure-relay-qa.py --test` 现在要求 **HUB_RELAY_QA=1 与 HUB_SYNC_QA=1**，以及现有 S1 client PostgreSQL 可用。为保持原 64 project budget，顺序执行 Relay 与 client 两 cohort；任一失败或缺少本次完整 privacy v2 证据立即停止，不开始下组清表。每 CLI trial UUID、cohort invocation UUID 绑定 service run/cohort，并保留独立 aggregate JSON/JUnit，避免下组或后次执行覆盖前组证据。Task 3A 历史的单 Relay opt-in 命令仅代表当时范围。

完整 runner 仅对子进程清除 `PYTEST_ADDOPTS` 并覆盖配置 addopts，保留用户进程/全局环境。独立 pytest evidence plugin 记录 selected/executed/deselected、cohort 实际文件集和 invocation；runner 必须核对正数 JUnit tests 与 selected/executed 一致、deselected=0、全部指定文件均收集且无失败/skip，不能把 `-k/-m` 子集或缺收集证据当完整成功。没有硬编码当前测试总数。
