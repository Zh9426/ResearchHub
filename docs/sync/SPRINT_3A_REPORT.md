# Sprint 3A 浏览器离线工作台验收记录

状态：Sprint3A 完成，范围仅限隔离合成数据的浏览器离线工作台。Windows 与 Linux 实际浏览器验证通过，精确实现提交首次 CI 五个 job 全部通过；已按要求 STOP，不进入 Sprint3B。

## 基线与隔离

- 基线提交：`b882738916c320e1a8c6ef43e33ab27f3b128a9d`；开发分支 `codex/researchhub-v0.3`，开始时工作树干净且远端一致。
- `main` 与 `v0.2.0` 目标保持 `4a4db4a4bd54a598f640d7de99281c15bd46e3b9`，不合并、不移动标签、不发布版本。
- 固定 QA origin：`http://127.0.0.1:3313`；不混用 localhost。浏览器、profile、静态构建和原始证据位于 ignored `storage/runtime/browser-local-qa/`。
- 仅合成数据；不调用生产 API、PostgreSQL、MinIO，不读取个人浏览器 profile。草稿采用明文 QA 存储，不能用于真实科研。
- TLS-001 **OPEN**。原调查记录、失败归档和测试保留；绿色 CI 不构成关闭条件。

## 已执行的阶段证据

| 阶段 | 结果 | 范围与证据 |
|---|---|---|
| RH-022 静态应用壳 | 2 tests PASS / 5.3s | Chromium 156.0.8078.4，Windows 10.0.22631 x64；`review-build.log`、`review-green.log` |
| 服务停止与浏览器重开 | PASS，仅壳 | 静态服务停止后连接失败；CDP取得浏览器PID，关闭后OS检查全部退出；同profile新进程离线直访详情及刷新，无重新灌入 |
| SW安装失败 | RED→GREEN | 真实服务器503注入；`review-red-install.log`；补丁改为有界失败提示及可重试，未吞错成功 |
| 原前端兼容 | 46 tests PASS；typecheck PASS | `web-test-task1-elevated.log`；纯展示组件提取，未修改API行为 |
| 协议基线 | Python17 / Node7 PASS | `python-vectors-baseline.log`、`node-vectors-baseline.log`；原向量哈希 `baseline-protected-hashes.json` |
| 独立复审 | Task1规格PASS、质量补丁复审APPROVED | 当时仅静态复核清理；Task5后续补齐实际启动失败与close拒绝用例 |
| RH-022 精确提交CI | 4 jobs success | `08aafe4a1c1ff8123b3cf9f53d5887cf00c72628`，[37867406210 attempt 1](https://github.com/Zh9426/ResearchHub/actions/runs/37867406210)；20轮TLS诊断保存于 `ci-37867406210-attempt1/`，不关闭TLS-001 |
| 本地模型与工作台 | 4 tests PASS / 12.2s | `task2-delivery-verified.log`：服务停止后Run/Note/失败阴性星标；同profile进程退出重开后全snapshot相等；刷新不重灌；双tab CAS/另存/并行创建；写后abort全回滚 |
| 保存边界故障 | RED→GREEN | `task2-red-notification.log`、`task2-red-refresh.log`：通知失败或提交后读取失败不能否定已经提交的事务 |
| Task2 独立复审 | 规格PASS、质量APPROVED | 审查代码、测试和保留日志；审查者未重复执行浏览器，未将审查计为新测试 |
| RH-023 精确提交CI | 4 jobs success | `e88519429b8ce98284e4b99539c6e658c1670ed6`，[37868749984 attempt 1](https://github.com/Zh9426/ResearchHub/actions/runs/37868749984)；TLS20轮诊断归档 `ci-37868749984-attempt1/` |
| 救援与存储 | 完整7 tests PASS；adapter补丁后3 PASS /16.6s | `task3-full-attempt1.log`、`task3-transport-green.log`；实际下载→新profile文件预览/恢复、幂等、冲突、严格字段/摘要、原来源/新身份、未保存草稿、真实导入abort和升级阻塞/失败 |
| 非空pending故障 | 1 PASS /10.4s | `task3-nonempty-pending.log`；先保存Note并断言pending非空，quota与TEST ONLY adapter拒绝后完整快照和dirty输入不变 |
| RH-024 精确提交CI | 4 jobs success | `906a83fa8cbb66a36d75feb84a630a72a6b877ec`，[37869813951 attempt 1](https://github.com/Zh9426/ResearchHub/actions/runs/37869813951)；TLS20轮诊断归档 `ci-37869813951-attempt1/` |
| 浏览器wire与安全探针 | 全部11 tests PASS /35.6s；追加2 PASS /4.5s | `task4-browser-final.log`、`task4-browser-interruption.log`；原26/59/3/10场景20step共237检查；AES-GCM key重载、双tab/刷新/重开、exact retry、耗号、损坏/缺失/旧导入拒绝及实际key救援排除 |
| 关联安全回归 | Node48、Python191 PASS | `task4-node-security.log`、`task4-python-security.log`，Python21.91s；protocol Node7及两包typecheck通过；原fixtures及TLS调查文件哈希未变 |
| RH-025 精确提交CI | 4 jobs success | `8a38e9a676119f415c844f955cc3af0fe8e93912`，[37870842565 attempt 1](https://github.com/Zh9426/ResearchHub/actions/runs/37870842565)；TLS20轮归档 `ci-37870842565-attempt1/`，zip SHA256 `fe489ab08a2c8d5539478a2b837aecae4ef7fbc30f9ea01ed7ebbf4473445a68` |
| 最终本地完整验收 | 17 tests PASS /50.6s，0 retry/skip | `evidence/attempt-2/` 的完整log、JUnit与summary；构建JS+CSS SHA256 `7f7b3c0cc1a50b241924a9bc1df9a556b826a7807d6420e55db9c71656b594c0`；修改布局前首轮17 PASS /42.3s另存attempt-1 |
| RH-026 Linux浏览器CI | 17 PASS /35.03s，0失败/跳过/重试 | 首次run37871775036；Linux6.17.0-1022-azure x64、Node24.21.0、Chromium156.0.8078.4；buildHash与Windows一致；白名单artifact SHA256 `f9ef4e9a2eceb55ce4231ef162b1b5654b073cdf0c0a213df96ff47a8b2d34fe` |
| 补充失败边界 | 6 targeted PASS /6.6s | 四类缓存错绑定分别拒绝、counter不变、encrypt=0、恢复缓存exact retry；真实目标浏览器executable缺失释放来源浏览器和静态服务；close拒绝仍清理服务且传播错误 |

全部上述路径相对 ignored `storage/runtime/browser-local-qa/`。初始沙箱 ENOTCACHED/EPERM、构建扫描误匹配以及使用旧构建的中间测试均在 `task1-attempts.txt` 区分，未计入最终构建验收。所有浏览器测试 `retries=0`。

最终六张实际页面、逐文件SHA256、测试命令和可版本管理的脱敏JSON见[截图与证据索引](../screenshots/sprint3a/README.md)。Windows本地浏览器版本如上，Node24.15.0；移动截图仅390px视口。CI的Linux结果单独列出，不由本机通过推断。

## 验收状态

| Gate | 当前状态 |
|---|---|
| G1 离线启动与进程重开 | 最终本地17项通过；停服、所有PID退出、同profile离线重开、直接详情/刷新通过 |
| G2 对象/队列/审计原子性 | Task2实际IDB写后abort与snapshot全等通过，两阶段复审通过 |
| G3 双标签页保护 | Task2一成一拒、保留输入、比较/另存及不同记录并发通过，两阶段复审通过 |
| G4 星标、状态与救援恢复 | 真实新profile救援、幂等/冲突/未保存草稿通过；Task3规格PASS、质量APPROVED |
| G5 浏览器协议、key/nonce边界 | 237固定检查与受限AES-GCM/key/nonce探针通过；Task4规格PASS、质量APPROVED，网络仍BLOCKED |
| G6 隔离与TLS证据 | 固定origin/profile/合成数据通过；RH-026首次CI五job成功、TLS20轮归档；原失败和诊断哈希不变，TLS-001 OPEN |

## 交付分类

- **IMPLEMENTED IN BROWSER QA**：隔离静态应用壳、SW就绪检查、固定origin/专用profile CLI；三合成项目、Run/Note/星标、原子本地命令及CAS；明文救援预览/恢复、存储风险与故障提示；纯wire browser入口及独立AES-GCM/key/nonce探针。
- **VERIFIED IN REAL DESKTOP BROWSER**：离线编辑、进程重开、直接详情导航、刷新、两标签页CAS、未知缓存保留、端口占用拒绝；新profile文件救援、key持久重载/加解密、nonce跨tab和完整封装重试、固定wire向量。
- **VERIFIED ON PHYSICAL MOBILE**：无；390px截图只是移动视口。
- **FAULT-INJECTED ONLY**：首次SW静态资源503；实际IDB写后abort、导入中止与升级中止；通知/提交后读取故障；模拟QuotaExceededError、persist拒绝/不支持与TEST ONLY adapter拒绝；加密拒绝/挂起和局部IDB损坏。真实升级阻塞已触发并解除；加密挂起后正常关闭全部浏览器进程，不是崩溃、物理磁盘满、断电或TLS证明。
- **DESIGNED ONLY**：未来正式字段/wire迁移、浏览器授权与恢复威胁模型仅记录候选方向，不作为本轮已实现能力。
- **NOT IMPLEMENTED**：真实Push/Pull、后台同步、完整DAG批准、配对/撤销/epoch恢复、相机/文件同步、生产Recovery Kit。
- **BLOCKED FOR NETWORK / PRODUCTION**：TLS-001 OPEN；完整浏览器安全适配、站点一致回滚、平台驱逐/断电保证、生产vault及真实授权均未证明。

## A–L 场景与证据边界

| 场景 | 已实施的实际验证 | 主要测试 |
|---|---|---|
| A 离线创建/观察/星标 | 初始化静态缓存和空合成工作区后停止QA静态服务，浏览器设为offline，继续创建和保存；该入口从未启动或依赖QA API | local.spec.ts |
| B 关闭重开 | CDP枚举PID，关闭后OS确认全部退出；同profile新浏览器读取完整snapshot相等（对象/Note/星标/pending/audit/身份），没有再seed | local.spec.ts、lifecycle.ts |
| C 详情直访/刷新 | 停服离线的新进程直接导航已保存详情并继续编辑；刷新前后快照相等 | local.spec.ts、shell.spec.ts |
| D 模块与未知值 | Generic/HDSP/ICE类型来自冻结manifest；unknown科研结果、空语境保持未知；HDSP/ICE高级字段救援往返 | local.spec.ts、rescue.spec.ts |
| E 原子性 | 最后写请求成功后、commit前真实abort；对象/版本/队列/审计全部不变，dirty保留；恢复事务也做写后abort | local.spec.ts、rescue.spec.ts |
| F 多标签 | 不同ID并发均保留；同版本先提交成功，后提交冲突且保输入，可比较或另存；BC仅通知 | local.spec.ts |
| G wire | 原固定向量237检查；decimal字符串精度和Unicode保持；highlight额外字段拒绝，LocalOperation完整保存而未声称wire兼容 | wire.spec.ts |
| H key/nonce | 独立AES256 CryptoKey持久重载；双tab/刷新/重开、exact retry不加密/不耗号、预约失败耗号；加密挂起后正常关闭全部进程，重开pending拒绝 | security.spec.ts |
| I 存储失败 | 实际persist/estimate调用；拒绝/不支持/QuotaExceededError是TEST ONLY模拟；升级阻塞由真实tab连接产生，升级失败由真实升级事务abort产生，均可恢复 | rescue.spec.ts |
| J 救援 | 实际下载文件→全新独立profile预览/恢复；幂等、冲突及错误摘要/额外字段拒绝；新身份和原来源；未保存草稿另存，真实key DB不克隆 | rescue.spec.ts、security.spec.ts |
| K 无假同步 | 实际transport始终not_configured；无receipt/ScientificAccepted；无网络TEST ONLY adapter拒绝，非空pending与完整快照不变 | local.spec.ts、rescue.spec.ts |
| L 页面 | 六张实际桌面1280px与390px移动视口截图均已view_image检查，没有实体手机/平板验收 | docs/screenshots/sprint3a |

测试源码位于 [apps/browser-qa/tests](../../apps/browser-qa/tests)。独立错绑定负例见 binding.spec.ts，真实启动失败与清理故障见 lifecycle-failure.spec.ts。浏览器关闭层级明确为正常关闭context后核验进程全部退出；加密停滞是故障注入，不是强制杀进程、OS崩溃或断电。

## 失败保留与未覆盖范围

- 壳缺失、静态资源503、通知/提交后读取异常、救援入口缺失、ICE语境白名单差异、adapter缺失和损坏封装等RED及修复日志均保留在ignored runtime。初期救援RED只有日志/上下文，没有截图；后续加入逐attempt截图。
- 重开初次定位失败保留 `task2-green-attempt1.log` 和 `task2-diagnostic-label.log`：implicit label包含已加载textarea内容，改用语义textbox/name定位；仍断言恢复值和全snapshot相等。
- 非extractable仅限制WebCrypto导出，不阻止同源脚本使用key，也不证明硬件或磁盘加密。当前业务草稿仍是明文合成数据。
- high-water镜像与ledger同属IDB，仅检测局部ledger回退；两者一致回滚没有外部可信锚。全站一致回滚、浏览器驱逐、整机断电、实际移动平台、生产解锁/授权/密钥生命周期和HPKE适配均未证明。
- `TESTONLY-AES-GCM-v1`不是SecureEnvelope。本地module_hash是冻结JSON快照的本地哈希，Note.body和全部highlight字段仍需显式wire adapter；不得直接发送当前队列。

## 停止边界

本轮验收完成，已STOP。Sprint3B仅候选：独立ADR审查字段/wire迁移、正式浏览器密钥授权及恢复威胁模型、受控传输失败语义。在TLS-001仍OPEN及上述安全缺口未解决前，不将本地探针结论扩大为生产或跨设备同步可用。

启动和停止命令见 [浏览器QA说明](../../apps/browser-qa/README.md)。六张截图与A–L矩阵已交付；精确实现提交 `8e6200d7318413c535bcafb59f8dee17fade69d3`，远端已一致。首次CI [37871775036 attempt 1](https://github.com/Zh9426/ResearchHub/actions/runs/37871775036) 五个job全部success：browser-local-qa、frontend、backend-mcp-migration、sync-kernel-qa、secure-relay-qa。该SHA是最终实现与截图提交；随后只提交报告收尾，不改实现。


## 独立复审与保护项

Task1–5均完成先规格、后质量审查，所有阻断项已处理；Task5最终规格PASS、质量APPROVED，全实现最终复审APPROVED。审查均为独立只读代码/证据核对，未冒称审查者重新执行全部测试。

根协调者复核四份冻结wire fixture与原TLS调查记录SHA256全部保持基线值；API/Relay业务及原同步/安全测试未修改。`git ls-files storage/runtime`为空。稳定main和v0.2.0目标仍为 `4a4db4a4bd54a598f640d7de99281c15bd46e3b9`；仓库仍为用户指定public。QA静态端口3313在验收结束后未监听，没有遗留演示服务。

## 最终 CI 证据归档

精确实现SHA的首次完整CI已下载到 ignored `storage/runtime/browser-local-qa/ci-37871775036-attempt1/`；浏览器与TLS artifact均按原字节保留。TLS 20/20固定轮次通过仅说明本次未复现，不关闭TLS-001。

- `tls-stages.zip` SHA256 `3bfa21a87c8ae535d3a4f68d72dac02f9e6690e4156dbaa716bbbe0ead8c5fc9`。
- `browser-local-qa.zip` SHA256 `f9ef4e9a2eceb55ce4231ef162b1b5654b073cdf0c0a213df96ff47a8b2d34fe`。

最终提交前原失败zip/日志/30次基线XML的SHA256再次核对一致。整个Sprint没有跳过TLS测试、放宽证书验证或按结果重跑CI；所有记录均为不同迭代提交的首次attempt。
