# Task 3A：隔离 Secure Relay 实际 QA

范围：SYNTHETIC / LOCAL LOOPBACK ONLY。此记录不把 Relay durable ACK 当作客户端 Kernel 应用或科研验收；Task 3B 的客户端事务/进程 crash 和 100-envelope 性能尚不在本次结论内。没有个人数据、公网服务或生产 migration。

## 接管与故障修复

接管时遗留 TLS helper 容器 Exit 1，未生成 run state。精确核验其 scope/run labels、ID、none 网络、只读源目录、唯一目标 TLS 卷及 CHOWN capability 后，捕获到 `PermissionError: Operation not permitted: /target/server.key`。原因是移交 owner 后再 chmod，cap-drop ALL 下不具 FOWNER。改为 chmod 0600 后 chown 10001，不增加 capability。失败 helper、其确切 TLS 卷和 run 证书目录已清理，原 PG 保留。

此前 QA PG 容器 Env 曾被打印。已在核验精确 ID、database/user、两条专用网络、127.0.0.1:35434 及原数据卷后轮换服务密码；实际验证新密码认证成功、旧容器 bootstrap 密码认证失败、ignored JSON/env 新值一致。旧失效值仍在 PG 容器元数据中，未声称物理消除；没有输出新旧值或把它们写入 Git。

初始化现在记录 initializing/ready phase、确切容器/网络/卷 ID 和临时路径。真实 Docker helper exit 7 与入口 invalid image create 失败两项测试均能通过 journal 只清理该 run，保留旧 PG ID 并继续认证：`2 passed in 20.97s`。不通过 label 扫描删除资源，不 prune。

第一轮真实 HTTPS 基础测试：8 passed。安全扩展首次 31 项中 29 passed、2 RED：owner 无法取得自己的公开配对 submissions；expired challenge 未持久标记 EXPIRED。修复为 owner 仅可读取本人签发会话，并把自然到期状态独立持久化，过期请求仍先拒绝。

扩展真实故障/限额 suite 首轮：45 passed、1 setup error（115.49 秒）。PG SIGKILL 后客户端 QA SQLAlchemy 池借出失效连接；增加 pool_pre_ping，保持中途失败为 503/安全重试，不吞事务错误。后续验证结果另列，不把此轮称全绿。

## 已实施边界

- HTTPS 由 Relay 终止；客户端验证临时 CA 和 SAN 127.0.0.1。先真实 handshake 成功，再断言 wrong CA/hostname 的 `SSLCertVerificationError`，以及明文 HTTP 无成功响应。
- Relay 只在 internal data 网络；固定目标 TCP ingress 与 PG 在两条独立 QA 网络；仅发布 127.0.0.1:38001/35434。非 root Relay 能读取 0600 server key；CA private key 仅签发进程内存。
- 每次服务操作核验精确 IDs、labels、actual networks/members/aliases、ports、mounts、read-only rootfs、caps、UID、资源上限、image command 和 env allowlist。入口无 TLS/client keys、任意目标参数或 Docker socket。
- request proof/current manifest/epochs/ACTIVE role 验证先于 immutable PG response cache 和 business receipt。recovery 与 pairing 为独立受限 profile，HTTP 不能注册 root。
- 真实 PostgreSQL 项目行锁与 synchronous_commit 事务内保存完整 envelope、nonce uniqueness、sequence/chain、quota、receipt；commit 后返回 RELAY_STORED。其他五阶段 ACK 是设备签名声明。
- raw body 524288、envelope 262144、batch 16、page 100/524288、chunk 65536+16、项目实际 ciphertext 16777216、独立 response cache 8388608、rolling 60 秒 120 次。没有降低测试阈值或用 mocked 服务替代。
- Hypothesis 生成 retry 序列、malformed envelope 与 chunk 到达排列，全部请求走真实 TLS。Blob 接口保留 opaque 字段，客户端自行解密与核验次序/内容。

## 实际故障与隐私方法

上传半截/全量后关闭 TLS socket；由 host 在固定 `/fault` marker 到达后对精确 Relay ID 发 SIGKILL，分别覆盖 commit 前与 commit 后 ACK 前，并直接查询 PG 是否已有完整 receipt/envelope/sequence。分别 kill/start Relay、PG、ingress，检查原 durable ciphertext/receipt；故障控制不暴露 HTTP endpoint。

隐私审计在 pytest session 终点执行，所有测试生成入口登记 Device signing/recipient seeds、Recovery seeds、Project keys 与 Artifact DEKs，仅保留 client 内存。client 捕获 PG dump、所有 Relay/ingress stdout+stderr logs、只读应用文件及全部 writable mounts（/fault、/tls）；实际 rootfs diff 仅允许 Docker 创建挂载点产生的 `A /tls`、`A /fault` 两个目录，随后读取并扫描这两处全部挂载内容，其他 diff 一律拒绝。核验应用 AST/挂载/env 中无 client AEAD/Domain/vault/fixtures。搜索 raw、hex/uppercase hex、base64/base64url/padding variants 和全部合成科研 canaries，只有汇总计数写入 ignored QA evidence。

TLS server key 和专用 PG 服务密码是显式传输/服务例外；不把标准 cryptography wheel 内部包含 AES 实现当作 Relay 应用持有解密钥匙。client 私钥搜索模式不传入 Relay。最终零命中计数必须以实际测试会话结果为准。

## 终点审计失败、修复与 fresh run 证据

中间一轮网络断言 46 passed，但终点审计错误地要求 Docker diff 完全为空，因此为 1 teardown ERROR（整体未通过，448.42 秒）。失败回溯又展开 audit 参数中的临时合成私钥列表，属于诊断输出缺陷；这些不是个人/生产钥匙，但同样不能忽略。修复为 SecretInventory/SecretBytes 与 QAConfig 对象 repr 脱敏、隐私失败只抛固定代码，搜索 markers 不进入异常参数/日志；CLI 同时采用 short traceback，不能以隐藏回溯替代实际断言。扫描器从低效正则 alternation 改为同范围的原生精确字节计数。

后续 fresh run 未复用失败会话的 keys；只清专用 Relay QA 表，直接查 PG 确认所有旧 Project registry 行消失，再用新 outsider 签名请求逐一访问旧 project，均为 HTTP 401。后者验证未注册项目拒绝，不冒称持有旧合法 proof 的重放复现；旧授权失效的依据是完整 registry 清除。

定向 RED 还发现：在项目锁外取得的 `now` 允许等待锁后已过期的 proof 获得 200；未认证 pairing body 为非 object 时返回 503。改为锁内采样时间，以及 profile 解析时严格检查 object 后统一 AUTH_REJECTED。两项均已纳入 fresh 完整测试并通过。

2026-10-08 fresh run `945b1506-6236-4299-8664-a34988b216ab`，命令 `HUB_RELAY_QA=1; python scripts/secure-relay-qa.py --test`：**50 passed in 179.24s**，含旧版终点审计。旧扫描器报告 268 项私密材料、1541 个搜索表示、65,443,291 bytes、0 hits。**独立 spec 随后证明该扫描器存在假阴性，此处旧 0 hits 不再作为隐私通过证据**，修复见后文。未保存明文 dump、搜索 keys 或日志正文。其后新增 repr 回归所在 contract 文件 **3 passed in 0.15s**；TLS 材料测试 **2 passed in 0.50s**（沙箱临时目录 ACL 先报错，窄提升后实际通过，未 skip）。

额外初始化故障探测表明：Docker 可对 stopped 容器的不存在 network 名返回成功并保存空 NetworkID 占位。严格 topology guard 拒绝了它；该特定注入入口经逐项核验后由人工维护脚本精确移除，再按 journal 清理剩余资源。此过程不是自动 cleanup PASS。正式第三项故障回归改为真实 Docker `network connect --ip invalid` 参数失败，并检查可直接通过 journal 自动销毁。

最终三项生命周期回归命令 `HUB_RELAY_QA=1; python -m pytest tests/secure_relay_lifecycle -q --tb=short -p no:cacheprovider --basetemp storage/runtime/relay-lifecycle-tests-final2`：**3 passed in 36.69s**。每项检查 journal 对应的 helper/service IDs、TLS 卷和目录均移除，原 PG ID 保留且可认证。

最终格式检查覆盖本 Task 19 个 Python 文件：Ruff format 与 Ruff check 全通过。格式整理保持 API sanitizer 的故意 broad catch（有明确边界注释）；QA TLS readiness 收窄至 httpx.TransportError，入口断流分支以 return/finally 关闭连接。最后独立复核须在这些最终文件上再验证，50 项数字对应上述 fresh run，不冒称其后每个文本修改都已重跑全 suite。

## 独立 spec 的三项问题与回归修复

独立 spec 在既有 suite 51 passed、lifecycle 3 passed 后仍给出 FAIL，不能以测试数量代替合同审查：

1. P1：旧扫描器只给 private inventory 扩展编码，canary 仅 raw；而 `pg_dump` 又将 bytea 包成 hex。实际临时 PublicObject bytea 内的 raw canary、hex/base64 私密哨兵没有被检出。
2. P2：chunk `key_epoch=true` 通过 Python `True == 1`，真实 TLS 返回 200/RELAY_STORED。
3. P2：签名 query 的 `cursor=false,limit=true` 与实际 URL 的 `cursor=0,limit=1` 被 Python dict equality 当作相同，真实 TLS 返回 200。

实施者重新通过真实 HTTPS/PG 取得 RED。scanner positive controls 确认应抛错误却没有抛；两个类型请求在修正测试合成 ciphertext 长度后均明确收到错误的 200。没有把测试准备失败冒称漏洞 RED。

最小修复：

- 所有 canary 与私密 inventory 统一生成 raw、lower/upper hex、standard base64 有/无 padding、base64url 有/无 padding 变体。保留直接 pg_dump、logs、files 扫描；另在核对实际 database/user 后反射 public 表，使用 SQLAlchemy Table/Column 引用，流式扫描每个真实 bytea 列的驱动解码原始 bytes，避免猜测 dump 的外层编码次数。搜索模式不传给 PG 或 Relay。
- 增加真实 DB positive controls：运行时随机 synthetic sentinel（不是真实 Device/Project/Recovery key）分别作为 canary/private inventory，七种表示逐次提交到专用 QA PublicObject bytea 临时行，audit 必须抛固定 `PRIVACY_NONZERO_HITS`；finally 按精确 `(project,kind,id)` 删除并查询确认不存在，再要求 audit 通过。此检查针对逻辑 DB/dump 与实际读取值，不宣称清除 PostgreSQL WAL 的物理残留。
- chunk 所有数值字段使用 `safe_int`，包括遗漏的 key_epoch；schema 类型预检在授权后、分配任何 request cache/receipt/quota 之前。True/False、float、null、string 均验证拒绝且三个计数不变、无 Chunk/RequestReceipt 行；合法整数请求仍通过。
- query 绑定改为 RH-C14N-1 canonical bytes 精确比较，对全部 endpoint 保留 JSON 类型差异；messages 和 chunks 均覆盖布尔伪装以及合法整数请求。

定向修复命令 `HUB_RELAY_QA=1; python -m pytest tests/secure_relay/test_review_regressions.py -q --tb=short -p no:cacheprovider --basetemp storage/runtime/relay-spec-review-green`：**4 passed in 77.59s**，包含 2 个类型测试与 2 类各七种编码的真实数据库泄漏控制。20 个 Python 文件 Ruff/format 检查通过。

修复后的 fresh 全 suite 命令 `HUB_RELAY_QA=1; python scripts/secure-relay-qa.py --test`：**55 passed in 277.90s**。版本 2 审计 run `7398722b-0c6d-4a57-a0ef-4f13a92579b6`：289 个 private inventory 条目（含 1 个随机 synthetic positive-control sentinel），8 个显式 canary 条目（另加 3 个内置合成科研标记），1918 个唯一编码表示；扫描 11 个实际 bytea 列、859 个非空值，driver 解码原值 32,624,609 bytes；连同 dump/files/logs 总计 **98,094,593 bytes，0 hits**。positive-control 临时行已全部精确删除，零命中来自清理后完整 session 终点审计。`--status` 实测 QA_TOPOLOGY_VERIFIED，服务保持同一 run READY。汇总证据仍仅包含计数，不持久化原值/模式/dump。

实现及本轮修复再次冻结，等待原 spec 复审，然后独立 quality/security 审查；不将此处测试结果自行提升为独立审查 PASS 或 Sprint 2 八项 Gate 全通过。

## 独立审查结论

独立spec首次FAIL：隐私canary编码及pg_dump bytea外层导致漏检（P1）、chunk epoch布尔混同（P2）、proof query布尔/整数混同（P2）。三项有效RED→GREEN后，原spec独立完整55 passed / 284.64s，并自行重放原HTTPS探针得到400/401、实际PG无chunk/receipt/quota/cache/sequence副作用，最终PASS。

后续独立quality/security APPROVED，无未关闭Critical/Important：实际完整55 passed / 288.64s、部分初始化清理3 passed / 37.95s、TLS材料2 passed / 0.37s；项目存在/不存在乘六种畸形pairing session_id的12项独立未认证探针统一401。该独立探针后来覆盖了聚合扫描文件，其7项私密材料汇总仅代表该probe，不冒称完整suite inventory；完整suite终点审计随55项测试通过。两阶段审查仅限Task3A，不能代替最终全系统安全验收。

root提交前fresh实际执行同一`--test`：**55 passed / 284.98s**。run `24804e63-c77e-41fa-b34c-68b0809031a0`的v2终点证据：289项私密库存、8显式及3内置canary、1908个唯一编码模式；实际11个bytea列859个非空值、解码原值32,624,609 bytes；全部dump/原值/文件/日志**98,100,447 bytes、0 hits**。此汇总代替先前被probe覆盖的文件。本地协议/密码依赖Python220项、Node38项/typecheck通过，Ruff/format20文件通过；暂存区29文件secret形状零命中、新旧两个专用QA服务密码在36个候选文件中均零命中。

## 可复现实验命令

设置 `HUB_RELAY_QA=1`。使用项目虚拟环境 Python，先在无当前 run 时执行 `pytest tests/secure_relay_lifecycle -q`；随后 `python scripts/secure-relay-qa.py --init`、`--test`，最后 `--destroy`。CLI `--status / --restart relay|pg|ingress / --kill ...` 都通过同一 ownership/topology guard。`--destroy` 支持有 journal 的部分初始化，不删除已有专用 PG。

Linux CI 使用同一 Docker TLS helper 和非 root 服务；本地 Windows 的成功不冒称 Linux CI 已运行。Task3A 两阶段独立审查已通过，但客户端原子接收及最终全系统验证尚未完成，不能据此宣布 Sprint2 八个 Gate 全部通过。
