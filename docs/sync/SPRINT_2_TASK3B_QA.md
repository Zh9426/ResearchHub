# Sprint 2 Task 3B — 可信客户端与故障证据

范围：QA ONLY / SYNTHETIC ONLY / LOOPBACK ONLY。实现与证据针对单机隔离 QA，不代表生产部署、分布式吞吐或 Sprint 2 最终八项 Gate 审批。

## 可信客户端边界

- `transport.py` 是实际可信客户端，独立于测试用 `ProjectClient`；固定 `https://127.0.0.1:38001`，显式 CA、hostname 验证、禁环境 proxy 与 redirect，无 HTTP/verifyFalse fallback。
- `transport_pg.py` 独立 client metadata，仅连接 S1 QA `127.0.0.1/localhost:35433`、`researchhub_sync_kernel_qa`、`researchhub_sync_qa`。连接前检查 driver/host/port/database/user/password/query；连接后核对真实 database/role。绝不读取产品 DATABASE_URL 或 native-env。
- 原 S1 QA 容器启动前检查精确名称、scope label、loopback 端口绑定、DB/user/password 与本地 ignored 配置一致，保留既有 volume 与所有原数据。客户端新增表仅 `create_all`，无生产 migration。
- outbox 存完整 canonical sealed envelope bytes。重试不调用 seal、不重新分配 nonce；每次请求生成 fresh proof UUID/time，并绑定当前 verified manifest、audience、method/path/query/body。重新加密由显式 seal 使用新 wrapperID/nonce，保留同 semantic transaction。
- 完整根 pin 与连续签名 membership history 保存在同一 client PG Trust 行；读取每次复验 bootstrap、transition、项目绑定与 canonical history。更新与 receive 共用 `FOR UPDATE`，锁覆盖整页预验证直至 PG commit。
- 整页 schema、连续 seq/chain、claimed cursor、envelope digest/signature/prefix/双 epoch、AEAD、semantic project/device/dependencies 全通过才调用 `apply_in_session(... relay_seq=None)`。Kernel、外层 receipt/cursor/chain、signed checkpoint 同 Session 提交；外层 seq 与 Kernel sequence/accepted watermark 分离。
- exact old page 校对已保存的原 bytes/digest/chain 并返回原 result；new wrapper 同 SemTx 只增加外层历史。历史合法消息在完整 pinned history 与成功解密下为 `TRANSPORT_QUARANTINED`；不会进入 Kernel。未知历史、坏签名/AEAD/digest/gap 不前进。
- Device 仅是传输签名身份；独立本地 principal 映射交给 Sprint 1 authority 检查。fresh HumanGrant 只由可信本地 setup 发放，wire actor_type 不能自授 Human。ACK 固定表示已持久解密，绝不依据网络到达自动发 ScientificAccepted。
- checkpoint 保留签名 body；读取根据完整 pinned history 重新验证签名/epoch/项目/cursor/chain，历史 creator 后续撤销不抹掉已认证锚点。远端 checkpoint 只能匹配已完整消费的本地位置，不跳过验证历史。

## RED/GREEN 记录

1. `python -m pytest tests/secure_relay/test_transport.py -q`：首次 `test_trusted_transport_implementation_exists` 明确失败（模块不存在）；随后加入真实 transport/outbox/page 行为断言，首次执行因同一缺失实现有 1 failed / 2 setup errors。实现后首批 **3 passed / 12.43s**。
2. 扩展 ACK/checkpoint 用例首次失败：`SecureTransport.ack` 尚不存在。实现 durable receipt ACK 与 checkpoint 接口；其余整页错误矩阵已通过。AI 权限断言曾匹配错误字符串，应匹配既有 ProtocolError 文本；这是测试纠错，不算安全实现 RED。
3. 连接守卫新增 5 项无网络连接负例：query host/port/dbname/service override 与缺密码，首次 **5 failed**（DID NOT RAISE），修复后 **5 passed**。负例仅创建未连接 Engine，未访问任何个人数据库。
4. 实际客户端终止、HumanGrant、晚 Kernel 失败整页回滚等扩展 **25 passed / 18.77s**。不是以抛异常模拟进程崩溃。
5. 扩展生成场景、并发 history 锁、撤销、checkpoint 损坏及网络 Artifact 后 **36 passed / 35.63s**。Artifact metadata/chunk size 与 revoke 参数曾有夹具调用错误，修正既有接口调用，不降低任何生产验证，不能计作有效实现 RED。
6. 首次本地回归使用默认 pytest 临时目录出现 Windows ACL 环境失败（18 failed / 8 passed / 139 fixture errors），不作为代码 RED；改用授权执行与 ignored 专用 basetemp 重跑。
7. 重跑时错误包含 `secure_relay_lifecycle` 目录：3 项在第一行缺少 Relay opt-in 断言失败，未进行初始化/清理；186 项通过。不计实现 RED，不计 lifecycle 通过。随后严格原四目录的 **220 passed / 25.09s**，没有变更 S1 旧测试。
8. 首次单 pytest 全网络组 **76 passed / 15 setup errors / 314.62s**，固定 64 project quota 触顶，另跨模块 fixture export 失效；该整套未通过。共享 fixture 移至 conftest，并改完整 CLI 为顺序两 cohort，保持 quota。每组完整 privacy 扫描通过并保留证据之后才运行下一组。
9. bounded response/direct page 与 runner 首批单元边界 **4 failed → 7 passed**。读取超长流在第 9 个 64 KiB chunk 拒绝，不继续消费，不信虚假 Content-Length，压缩响应拒绝。直接 page 在数据库访问之前拒超长。这些是单元输入，不冒称真实网络服务。
10. 新增 runner freshness 的 run/cohort/invocation/trial 错配 **4 failed（未拒绝旧证据）→ 8 passed**；后续补缺失 aggregate 与两项缺 opt-in 负例。每次 CLI 使用新 trial UUID，每组新 invocation UUID，privacy fixture 将上下文写入 aggregate，runner逐项核对，失败不进入下组。
11. 修正共享 fixture、完整历史坏页矩阵与 candidate ACK 后，客户端 cohort **57 passed / 39.15s**；之后新增的 runner freshness/opt-in 负例纳入最终完整命令。
12. 独立 spec P2：继承 `PYTEST_ADDOPTS=-k selected/-m selected` 会隐藏隔离 pytest 中的必需失败项。真实 pytest 子进程回归 **2 failed RED**，当时两组各 1 passed / 1 deselected 却 runner exit 0。另 incomplete collection 的 deselected/zero-selected/少执行/JUnit 数量不符/缺文件集 **5 failed RED**。修复仅对子进程清环境选项并 `-o addopts=`，用独立 pytest evidence plugin 与 JUnit/指定文件集交叉核对；真实子进程的通过/失败两类场景均确认每组 2 项完整执行。runner **20 passed**；用户 env 保持原值，不硬编码测试数。
13. 独立 root 补审：`iter_bytes(chunk_size=65536)` 的内部聚合会隐藏慢滴流时间。真正 httpx Response/SyncByteStream、每个 1-byte chunk 模拟 6 秒的测试 **RED：消耗 100 chunks / 600 模拟秒才拒绝，应为 3 chunks**；延迟空 EOF 同样 **RED：未拒绝**。改 `iter_raw()` 默认不聚合并在 EOF 复查后通过；bounds 5 项与 runner 20 项合计 **25 passed / 7.22s**。这是库迭代单元测试，不宣称真实网络跑了 600 秒。

body deadline 从已取得 HTTP response 后开始计 15 秒，逐原始 chunk/EOF 检查；单次 socket read timeout 同为 15 秒，允许检查延后最多一个阻塞 read timeout 加调度误差。connect/TLS/headers 不包含在这个 body deadline 内，不能宣传严格 15 秒全请求上限或完整 DoS 防护。

所有含私有材料的测试使用 redacted inventory；后续完整命令使用 `--tb=short`，不保存 keys/dumps/config/env/完整 traceback。

## 实际进程故障

父进程通过 stdin 将已登记 inventory 的合成 QA keys 交给精确创建的 Python 子进程，命令行不含 secrets。子进程真实 TLS pull，进入真实 client PG receive。

`before_commit` barrier 位于所有 flush 后、Session commit 前；父进程见到 ignored 本地 barrier 文件后直接 kill 子进程。两条 page 的 Kernel cursor/Audit/outer cursor 均为 **0**。重试完整 page 后 Audit 为 **2**。

`after_commit` barrier 位于 PG commit 后、ACK 前；父进程 kill 后 Kernel cursor/Audit/outer cursor 均为 **2**。同完整 page 重试返回原 receipt，Audit 仍为 **2**，随后才发送实际 transport ACK。没有把 catchable 异常作为 crash 证据。

原 Relay/PG/ingress 的实际 kill/restart、断上传、ACK loss、immutable GET/POST、privacy scanner positive controls 继续纳入完整 suite。

## 网络性能

Windows 11 10.0.22631、Python 3.12.4、Intel64 Family 6 Model 151 Stepping 2；单机本地 Docker QA TLS/PG。

最终完整 CLI 运行：100 envelope 共 228800 canonical bytes（每条 2288 bytes）。owner/writer 发起 **100 次 push / 100 条消息**；合法 reader 发起 **100 次 pull / 100 条消息**，每次 limit=1。120 rolling device rate 未修改；bootstrap/授权/封装与 outbox 预存不在计时内。

| 操作 | 总耗时 | mean | p95 |
| --- | ---: | ---: | ---: |
| push（实际 HTTPS + client outbox 读取/签名） | 2.765 s | 27.653 ms | 30.218 ms |
| pull（实际 HTTPS + proof/严格解析） | 2.363 s | 23.631 ms | 27.838 ms |
| 随后 100 页 client PG apply | 3.907 s | — | — |

pull 计时不包含随后 Kernel 提交；不是批量平均冒充逐条网络延时。p95 为 100 个逐请求计时的第 95 个顺序统计量。结果是该次单机 sequential 样本，不能宣称分布式吞吐；aggregate 文件为 ignored `storage/runtime/secure-client-performance.json`。

128 KiB 合成 Artifact，4 × 32 KiB chunk：seal 39.078 ms；网络 + local outbox/manifest 验证准备 350.708 ms；open 37.903 ms。真实调用为 manifest push/pull 各 1、chunk push/pull 各 4。独立复验签名/AEAD/顺序后 staging ready；不代表科研 Artifact 已由 Kernel 接受或 Primary 持久化。该项单样本仅补充网络证据，不替代先前 10 次纯本地均值基准。

## 最终回归与隐私

2026-10-08 最终完整 CLI **exit 0**。service run `24804e63-c77e-41fa-b34c-68b0809031a0`；trial `fd0264c6-b98e-40dc-90e5-ce61544a614f`。

| 验证 | 实际结果 |
| --- | --- |
| 原 Relay cohort（含原真实故障与 14 个 privacy 正对照） | 55 passed，316.34 s |
| 新 client cohort | 75 passed，45.95 s；包含真实 HTTPS/PG 场景及明确标注的 guards/iterator/runner 单元边界，不能把 75 全称网络测试 |
| 原本地四目录回归 | 220 passed，25.09 s |
| Node secure-sync | 38 passed；Node v24.15.0 |
| TypeScript typecheck | exit 0 |
| Ruff：整个 secure 目录、secure_relay 测试及 runner | All checks passed |
| 本任务已跟踪文件 diff whitespace | 无错误；仅 Windows CRLF 提示 |

两 cohort 的 collection evidence 同时证明 selected/executed 分别为 **55/55** 与 **75/75**，deselected 均为 **0**，实际文件集与 runner 指定的完整 cohort 文件集精确一致。独立 `scripts/secure_relay_pytest.py` 输出的 collection JSON 已绑定同一个唯一 invocation，并与 JUnit 正数 tests 交叉核对；缺失、空收集、少执行、被筛选或缺文件都拒绝。

上述为实现者交接证据，当时未运行GitHub CI或提交；后续独立审查记录见下文。最终八项Gate另由整体安全审查及其后回归决定。

两组终点均执行实际 PG dump、全部 public bytea 列的 driver-decoded 原值、Relay/ingress 文件与日志七种表示扫描，未把 keys 或扫描模式传入 Relay 容器。private inventory 来自 redacted `PRIVATE_MATERIAL`，包括新设备、Kit、Project Key、Artifact DEK 与子进程使用的同一合成材料。

| cohort | private inventory | canaries | unique patterns | scanned bytes | bytea columns / values / decoded bytes | hits |
| --- | ---: | ---: | ---: | ---: | --- | ---: |
| relay | 289 | 8 | 1932 | 98107806 | 11 / 859 / 32624609 | 0 |
| client | 252 | 7 | 1678 | 4722920 | 11 / 867 / 1495832 | 0 |

完整 aggregate 索引位于 ignored `storage/runtime/secure-relay-suite-result-24804e63-c77e-41fa-b34c-68b0809031a0-fd0264c6-b98e-40dc-90e5-ce61544a614f.json`。该索引保留两组独立 privacy 文件名、counts 与 invocation：relay `58e93bfa-762b-43d3-8677-d8262dc8e1e3`；client `769af168-ab1c-4715-836d-9a66c2bdb593`。没有保存原始 dump、keys 或日志内容。

可复现完整命令（PowerShell，仓库根目录；前提：已有 guarded Relay QA READY，独立 S1 PG 35433 可用，ignored S1 配置或精确 CI `HUB_SYNC_QA_URL` 已提供）：

```powershell
$env:HUB_RELAY_QA='1'
$env:HUB_SYNC_QA='1'
.venv/Scripts/python.exe scripts/secure-relay-qa.py --test
.venv/Scripts/python.exe -m pytest tests/sync_prototype tests/sync_kernel tests/sync_vectors tests/secure_sync -q --tb=short -p no:cacheprovider --basetemp storage/runtime/task3b-local-220
npm --prefix packages/secure-sync test
npm --prefix packages/secure-sync run typecheck
.venv/Scripts/python.exe -m ruff check apps/api/researchhub/sync/secure tests/secure_relay scripts/secure-relay-qa.py scripts/secure_relay_pytest.py
```

不能与其他网络或 lifecycle suite 并发。Task 3A 原 55 与 Task 3B 各自完整扫描后保留独立 `secure-relay-privacy-<service-run>-<trial>-<cohort>.json`；唯一 `secure-relay-suite-result-<service-run>-<trial>.json` 是两组汇总，JUnit 与 basetemp 同样唯一。任一 pytest 非零、privacy 缺失/错 run/cohort/invocation/trial/非零 hits 或 JUnit failure/error/skip，完整命令失败；不以第二组覆盖第一组证据。

## 独立审查与根核验（2026-10-08）

- 独立spec复审PASS。原PYTEST_ADDOPTS筛选探针现为1 failed/1 passed，入口非零且不开始第二组；root原httpx raw-drip探针在3个chunk/18模拟秒拒绝。独立完整CLI trial `cc6a01d5-9a39-4f18-ad24-1160211ab12e`：Relay55 passed/306.45s、client75 passed/51.85s；无skip/deselection/error/failure，完整文件集，privacy0/0。
- 中断后的第一次quality执行没有完成，未计为通过。恢复原QA容器及卷并核验拓扑后，新的独立quality/security审查 **APPROVED**，未发现未关闭Critical/Important。
- quality独立完整CLI trial `9d420cef-332b-4a1f-95d9-193307b8f732`、service run `24804e63-c77e-41fa-b34c-68b0809031a0`：Relay **55 passed/264.47s**，client **75 passed/47.68s**，exit0；selected/executed55/55和75/75，7/4个完整测试文件，全部failure/error/skip/deselected=0。
- 两组privacy分别289/252项private inventory、1914/1674模式、98,115,591/4,730,640 scanned bytes、0/0 hits；各11个bytea列，859/867值，解码32,624,609/1,495,832 bytes。
- root独立读取实际aggregate、两份collection/privacy和JUnit，交叉验证数量、完整上下文与0失败/0命中。最新Ruff与diff检查通过；候选源码针对三份QA服务凭据的精确扫描0命中。此前root本地四目录220 passed/26.35s、Node38/typecheck通过，属于Task3B依赖验证。
- 本次不重复运行已由独立审查完整执行且行为未变的网络suite；Task4整体安全审查后会重新执行最终完整回归。GitHub同步记录由CHANGELOG及最终Sprint2报告提供。

## 已知限制

完整 split-view/透明日志、所有 trusted state 一致恶意 rollback、真实 user-presence/浏览器 vault/hardware keys/移动端/OPFS/公网服务均 **NOT IMPLEMENTED**。恶意 Relay 可丢消息、阻断服务或隐藏尚未形成可信锚点的消息；本客户端不证明 availability 或 globally latest history。可信 endpoint compromise 与已撤销设备既有历史明文仍不受 E2E 消除。
