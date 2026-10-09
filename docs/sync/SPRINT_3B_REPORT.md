# Sprint 3B 实施记录（进行中）

本文件在本轮验收完成前不代表封版。`SPRINT_3B_QA_INTEGRATION = INCOMPLETE`；`TLS-001 = OPEN`；`PRODUCTION_READY = NO`；`PHYSICAL_MOBILE_VERIFIED = NO`。

## 基线与隔离

2026-10-09，从干净工作树 `187fdfd10f34027882ed7c0f52f472b66e78295c` 继续 `codex/researchhub-v0.3`，当时远端一致。用户明确授权受控 loopback QA；仓库保持用户指定公开状态。main/v0.2.0 均保持 `4a4db4a4bd54a598f640d7de99281c15bd46e3b9`。仅合成数据，不连接生产数据库或个人浏览器 profile。

3A 保留3313；3B浏览器3314、PC入口3315、既有Relay HTTPS38001；业务QA PostgreSQL35433和Relay35434独立。详细边界见 [设计增量](SPRINT_3B_DESIGN_DELTA.md)。

## 已完成的内部迭代

### A1 — RH-028 / 1fd6a0fbaa263ceb024fff965acf02a05438d51c

`IMPLEMENTED`：显式(2,2) Run/Note协议、Run星标精确字段、Kernel版本物化、内外Envelope版本绑定及能力声明。原v1向量/套件不变。独立规格、质量审查PASS。

- 本机Python完整sync_vectors+secure_sync初轮221PASS；后续扩展v2定向28PASS、tmp_path修正后安全8PASS；Node协议初轮26PASS、扩展v2定向25PASS、安全51PASS；两包typecheck通过。
- 本机真实隔离QA PostgreSQL旧Kernel/Domain/Outbox回归132PASS，23.88s。
- [精确SHA首次CI37875621054](https://github.com/Zh9426/ResearchHub/actions/runs/37875621054)，attempt1，五job全部success。Linux Chromium156.0.8078.4旧3A17项PASS、retries0；旧TLS固定20轮通过。这不是3B浏览器安全或双向网络Gate证据，也不关闭TLS-001。
- CI归档在被忽略的 `storage/runtime/browser-local-qa/ci-37875621054-attempt1/`；TLS zip SHA256 `93d72922d0f662f6ac6deba72258acfef85e3d47df5b3d99558bab578a9f6469`；browser zip `3d33a45d60fc21d0d62d274be5944fc5450e13f0e6efbc61fb6bb4f5753b1a81`。
- 原v1/secure-v1八文件hash保持；TLS调查记录hash保持 `abd49c88a84a7460cfcab2a0d77d547e5bb991b69f2c1144ddcc535eb148e075`。

### A2a — RH-029 / 8b5aaafa774dd592a91af8bd5f282a5889cd7a74

`IMPLEMENTED / VERIFIED_IN_REAL_BROWSER`：3314独立origin/业务IDB/运行目录；复用工作台adapter；单击星标CAS、脏正文保留、离线工作、正常关闭全部进程重开；稳定mapping/父链/prepare token及真实IDB abort。正式转换仅显式TEST ONLY授权夹具测试，普通入口没有此注入，真实owner pin/配对尚未实现。

最终 `final-context-identity` 共4项PASS（2项Node纯结构/规则测试，2项真实Chromium测试），11.02s、retries0。另无fixture普通构建入口 `normal-build-a2a` 1项PASS；星标额外字段拒绝且整个IDB snapshot不变定向1项PASS。真实Python workflow.validate_context 7个纯函数对照场景通过，不是Domain/PG端到端验收。原3A完整17项最终51.6s通过，证据 `storage/runtime/browser-sync-qa/a2/final-3a-regression/`；后续仅sync专属补丁未重复该回归。typecheck/build通过。

Windows / Chromium156.0.8078.4；普通构建 `549a40efe012b388`，最终TEST ONLY构建 `379833083b415b18`。实际页面：[桌面](evidence/sprint3b/a2a-desktop.png)、[390px移动视口](evidence/sprint3b/a2a-mobile-viewport.png)。图中故意触发另一tab更新后的CAS拒绝，未保存中文正文仍在；不是实体移动验收。

[RH029精确首次CI37877406718](https://github.com/Zh9426/ResearchHub/actions/runs/37877406718)，attempt1，五job全部success；旧3A17项与固定TLS20轮通过并归档。该CI尚未执行新增3B专项测试，不将旧job成功冒充3B网络验收。

`NOT_IMPLEMENTED`：PC服务、真实配对/密钥/nonce/网络/接收冲突、3A救援导入。绑定内容预览只返回UNVERIFIED/BLOCKED，未建立信任。不支持的旧语境字段按冻结模块明确BLOCKED并保留，不隐式改快照或删除内容。

### A2b — RH-030 / bbd03cf680525ea18c0d5c558e726d2a51d8664e

`IMPLEMENTED / VERIFIED_IN_REAL_BROWSER`（仅本地 PC 路径）：受限3315界面复用工作台；Run/Note创建编辑与星标经独立QA PostgreSQL的Domain、Kernel、Outbox事务，读取分别提供工作副本、可信投影、候选和历史。持久owner/recovery设备、签名公开项目绑定和nonce账本不进入Git；尚未完成浏览器配对或网络同步。

`storage/runtime/browser-sync-qa/pc/attempt-015/` 的21项PG测试通过（8.570s，含既有Domain/Outbox回归）；attempt-016独立owned CLI启动停止1项通过（2.826s）；attempt-017实际Chromium UI 1项通过（7.555s），验证Run/Note创建编辑、Unicode空白、星标不提交脏正文以及公开绑定内容哈希预览。以上保留为较早阶段证据，最终修补后的结果见下文；精确SHA CI另行核验。

attempt-012暴露保存响应与刷新之间的竞态，后继编辑被误分类为create；adapter改为立即登记保存响应的版本/heads，并避免旧snapshot回退版本。attempt-013到截图后清理超时，伴随Windows连接重置；保留原始失败，**根因仍未解释**。原日志已确认Chromium各PID退出，故超时范围缩小到后续owned stop或server退出等待，但没有足够阶段证据确定其中一步。attempt-016验证无浏览器连接时的CLI退出，attempt-017增加阶段时刻并提前登记子进程退出Promise；两次成功不证明attempt-013已解决，也不关闭TLS-001。attempt-021确定性SIGTERM用例验证exitCode=null/signalCode=SIGTERM时晚订阅会漏掉退出事件，预登记或检查signalCode可完成；这仅证明独立清理竞态，不能外推为013根因。

初次规格审查通过；质量审查发现两个P2：PC重启后页面缓存旧会话、模块高级语境输入与冻结字段不匹配。最小补丁后规格、质量复审均PASS；会话失效明确失败，原页再次保存重建会话，同一prepared命令身份和脏正文保留，并发初始化只请求一次；PC表单按实际snapshot/run_forms显示合法字段，旧不适用key须用户明确删除。

最终attempt-031 PC/CLI与Domain/Outbox共34项PASS（10.68s，0 skipped）；attempt-032完整PC浏览器套件6项PASS（27.692s，retries=0），包括三模块实际UI、服务重启/并发会话、Run/Note/dirty-star及确定性退出竞态。Python3.12.4、Node24.15.0、Windows Chromium156.0.8078.4；PC build `7bc714f4539c3f99`，app.js SHA256 `f7328337815079a5e08fd17d734f8c1c18303a529ae3a37169e685ddcff192fc`。实际截图：[PC Note](evidence/sprint3b/a2b-pc-note.png)。该本地PC页面没有跨端传输。

attempt-025保留重启会话RED；026/027/029的模块测试是locator错误，分别保留，不能冒充产品失败用例或整次通过。attempt-027是3失败/3通过，修正测试定位器后的030为4通过；032为最终完整现行套件。attempt-019/022产品测试在受限pytest临时目录报PermissionError，未到产品断言；授权专用目录attempt-024实际108项通过（88.24s）。原3A attempt-023共17项通过；attempt-020同步工作区5项通过（11.6s）。这些后续绿灯不覆盖先前失败记录。

PC命令的change/audit/time在首次成功持久提交后固定；完全回滚前没有独立持久PREPARED命令，不能声称未落盘计算已有稳定身份。Browser不可变prepare/vault仍待B实现。PC清理事件attempt013继续OPEN，尚不能宣称生命周期所有故障已解释。

已推送并核验远端精确SHA相同，main/v0.2.0未移动。[首次CI37879759374](https://github.com/Zh9426/ResearchHub/actions/runs/37879759374) attempt1五job全部成功。Linux原3A17项、固定TLS20轮通过，新增PC后端也被sync-kernel job实际收集；当前CI尚无PC/3B浏览器专项job。归档 `storage/runtime/browser-local-qa/ci-37879759374-attempt1/`，TLS zip SHA256 `910fc64a5bcce1fd24addd78aeed28e9fae975fb3abfca38f40d5f480a7673a7`，browser zip `7ae7152ffdf8cff15f728047639b1302fd77cc6654ea4d46fc509a073ae31096`。该成功不关闭TLS-001或PC013。

### B1 — RH-031 / 5ae5eeda09e3cc35db23106b17d13019500e106d

`IMPLEMENTED / VERIFIED_IN_REAL_BROWSER`（仅密码与本地持久化范围）：共享平台无关 Envelope、membership、checkpoint 规则；真实 Chromium 使用 WebCrypto 与固定 @hpke/core 1.9.0 执行正式密码操作，独立 Python 实现验证双向互通。设备私钥和项目 CryptoKey 独立 IDB 保存且 non-extractable；业务 mapping 与 vault 之间采用可恢复准备/密封状态，不声称跨库原子提交。

本阶段使用显式 TEST ONLY 授权材料，尚未完成真实 owner 加入界面、浏览器 HTTPS 或双向传输，不能将这些结果计为完整 G2/G4 PASS。普通构建没有测试注入入口。

`security/b1-browser-009` 的9项真实 Chromium 测试通过（retries=0，构建 `9dc46c817c66e147`），但随后独立规格审查发现新的损坏恢复缺口：vault 已持久 sealed、业务尚未复制 READY 时，单独清空 preparation.sealed 可被误认为未密封并重新预约。`b1-browser-010` 已保留实际 RED。最小补丁将 sealed 状态和摘要与永久 prepare marker 同事务保存；最终复审及新增局部 counter 回滚验证尚在进行，009不作为最终封版依据。

此前 `b1-browser-007` 保留授权永久标记缺失仍可继续、业务 mapping 身份损坏未被 ready 拒绝的实际失败；对应补丁在读取/预约/最终 CAS 核验完整授权、业务身份与密文绑定。008为测试复用了此前已 BLOCKED 的对象，修正隔离后验证，不冒充安全规则修复。Python首次回归被临时目录 WinError5 阻断，专用授权目录 `b1-python-002` 实际182项通过；Node安全回归54项通过。这些结果均不关闭 TLS-001 或 PC013。

当前 Windows 仅发现 docker-desktop WSL；未修改个人证书库。后续 B2 计划在 Linux CI 一次性 OS 用户的实际 home/NSS/profile 完成原 Relay 入口严格 TLS 验收，Windows 网络仍 `NOT VERIFIED`。

最终 `b1-browser-012` 全部10项通过，无skipped、retries=0；Windows 10.0.22631 / Node24.15.0 / Chromium156.0.8078.4 / @hpke/core1.9.0，完整构建hash `9314b08923ee4779a84ab20ca8cfe1433e3583f7ec4d0ee6c3af00cb4fcd62fc`。011先验证sealed补丁通过，再真实复现双counter同时降低而更高prepare仍在的失败（5通过、1失败、4未执行）；012最小补丁以复合索引最高nonce核对计数器，损坏只拒绝、不抬升或清零。010为2通过、1失败、6未执行，不能按总计9条描述为9条均执行。规格与质量独立复审均PASS；精确SHA CI待推送后核验。

普通构建 `b1-normal-004` 实际Chromium1项通过，hash `f014176147fb8b5ea2908ddcc8142585de2c74225776a315494da3233270ef91`，无测试注入。原A2工作区5项通过；两包typecheck通过。现有3313未知所属服务未终止，本机未重复原3A，保留此前及精确CI的范围区分。脱敏结果：[正式密码](evidence/sprint3b/b1-security-summary.json)、[普通构建](evidence/sprint3b/b1-normal-summary.json)。

已推送并核验远端相同SHA，main/v0.2.0未移动；[首次CI37882487122](https://github.com/Zh9426/ResearchHub/actions/runs/37882487122) attempt1六job全部成功。Linux Chromium156.0.8078.4正式密码10项、原3A17项、固定TLS20轮通过；B1构建hash与Windows相同。归档 `storage/runtime/browser-local-qa/ci-37882487122-attempt1/`：TLS zip SHA256 `fea09842528ac2723d8dd7d42c8232bfa0e2cff577528a361de422048a9de614`，原browser zip `8c8e711e0c3b11a948792ac320ffcc4f3f0eb5620349c94c72edaa5ee6eebd16`，仅含白名单summary的security zip `1d38684e5e9c94b647caa0d6b845906e59a81babd37f3b07c7335d48d750d4ed`。该Linux密码测试没有执行浏览器网络或真实配对；不计B2/G4，也不关闭TLS-001/PC013。

### B2a — PC owner 配对协调器（RH032）

`IMPLEMENTED / VERIFIED_IN_REAL_LOOPBACK_NETWORK`（仅PC/Python配对路径）：持久PG journal、固定session challenge、SQLite原consume/receipt、原Relay membership发布/未知ACK查询恢复及PG chain/principal提交。启动仅恢复已登记journal；非空项目与未知第三head阻断。动态PcProjectBinding从PG构建，JSONB回读恢复canonical键序；完成态重取仍检查当前ACTIVE/epoch/head。实际浏览器配对UI、浏览器TLS/CORS尚未实现，不能计完整G1/G2/G4通过。

最终 `pc/b2a-regression-05`：sync_vectors、sync_kernel、sync_pg、secure_sync完整集合403项通过，exit0、无skipped，包含原owned_start_stop。独立 `pc/b2a-network-02`：真实严格HTTPS原38001入口配对1项通过，exit0、无skipped。两目录保留command/result/exit/JUnit。异常边界、503、ACK未知等故障使用显式注入，单列 `FAULT_INJECTED_ONLY`，不能外推真实进程崩溃或断电。规格与质量独立复审均 PASS。

RED01/02为临时目录权限；03/04预期缺实现；05为业务阻断/端点/transport缺失；06为JSONB回读snapshot哈希；07为setup CLI缺失；08为完成态撤销及503分类；09为stream deadline分类；10为崩溃注入窗口。逐项保留，不将环境错误、测试缺项与产品失败混为同类，也不关闭TLS-001/PC013。

两项质量 P2 先以 `pc/b2a-red-11` 复现（5 failed / 1 passed）：同步配对阻塞 HTTP 事件循环、构造环境错误绕过异常映射。最小补丁将构造/动作/关闭整体交给线程池，精确处理已知 setup 错误。修补后 `pc/b2a-api-regression-02` 五个完整 PC 文件 **43 passed / 11.40s**，`pc/b2a-network-03` 原严格 HTTPS **1 passed / 1.44s**，均 exit0、0 skipped。中间 api-regression-01 为 Windows monotonic 同 tick 的测试误判（39 passed / 1 failed），改为事件先后断言，保留原记录；不是放宽超时或反复重跑。上述403项是P2修补前完整结果，未混称为修补后重跑。

RH032 已推送 `e7eedb7b56eb417d5ae9bef26a4391fae349316f`，远端同 SHA，main/v0.2.0 不变。首次 [CI37902517081](https://github.com/Zh9426/ResearchHub/actions/runs/37902517081) attempt1 六job成功；原TLS固定20轮通过。归档 `storage/runtime/browser-local-qa/ci-37902517081-attempt1/`：TLS zip `d35ecac580cb93ca7abe0eca19990b5324e04363eb2da3bc28acf10872ad8de2`，browser zip `ade271cb619518d6c78e30a6159de33ce9865e2dafccdcdc31d2796a39c6a2fe`，security zip `06eb5cebca0fae784405cdb0f0a2712e00bd737c2d6efad2ef9ca7d130364053`。TLS-001/PC013仍OPEN，浏览器网络尚未验收。

### B2b — 实际加入界面与严格网络验收入口（RH033，验收中）

`IMPLEMENTED`：空B工作区原生生成设备公钥；PC/B通过独立信任根与SAS核对、标准配对证明、正式grant与签名绑定加入。B验证全部链、目标principal、模块内容和双哈希，vault授权先于业务绑定；原HTTPS签名hello确认当前空基线后才写VERIFIED。相同已完成receipt幂等重取不因后续新消息误报首次历史bootstrap。首次加入非空历史仍明确阻断。

正式browser Fetch保持原RelayRequest域、精确路径/query/body摘要/epoch/head，credentials omit、redirect error、524288字节及15秒边界；窄CORS只允许3314，OPTIONS无业务访问，实际请求仍校验proof。Linux CI使用新OS账户各自真实home/NSS/profile，runner runtime与Git元数据保持私有，仅复制公开CA；不导入个人全局根库，不绕证书、不代理浏览器密码计算。

`VERIFIED_IN_REAL_BROWSER`（仅Windows本地UI）：`b2-local/binding-status-green-20261009-01` 两项通过、exit0、0 skipped，4.2s。其profile Last Version为Chromium156.0.8078.4。第一项为原生身份生成与刷新保持、未确认按钮禁用、项目仍空；第二项是明确的合成BindingRecord注入，只验证状态显示与预览不改授权，不计真实加入。对应RED保留于 `binding-status-red-20261009-01`，build/typecheck/diff记录位于 `binding-status-build-20261009-01`。

本机CORS单元3项、Node请求/安全规则56项通过；两包类型检查与普通构建通过。B构建完整hash `f283ee604f1e28041a5280cd529aff80814322c075ca9e204616dcd428a4b66d`；PC `96a5e71643977b5f0ff6ebaa753328071935ef237445719e9285ece71ea2092e`。早期CORS拒绝、缺请求函数、重复hex编码和缺加入按钮等RED保留在执行记录；早期UI曾复用固定输出目录，部分Playwright文件可能覆盖，不能声称这些原始产物完整。后续已改唯一attempt并拒绝覆盖。

`NOT VERIFIED`：Linux严格浏览器TLS/真实Fetch/完整UI配对将由精确提交首次CI执行。其测试明确区分实际证书/CORS拒绝与 `FAULT_INJECTED_ONLY` 的pin+grant后hello网络中断；仅pin之后、grant之前中断尚未专测。Windows浏览器网络仍未验证。B2b规格与质量静态复审PASS，仍不计完整G2/G4通过；C业务双向传输尚未实现。

## 失败保留

B2a收尾遇到环境中断：`pc/b2a-regression-03` 没有退出状态/JUnit，不能计通过。继续执行的 `b2a-regression-04` 期间35433/35434/38001均不可达，核验Docker Linux engine未运行；保存 `environment.txt` 后仅终止该轮明确owned等待进程，记录 `ENVIRONMENT_BLOCKED/CANCELLED`、exit -1。后台启动Docker Desktop、核对既有QA scope并只start原容器，原Relay `--start` guard成功；没有init/destroy/清库、重建身份或调整超时/证书。恢复记录在该轮 `restore.txt`，后续新attempt结果单列。

本轮第一次Relay初始化使用PATH中的Anaconda Python，缺少psycopg；被既有就绪检查包装为QA_PG_UNAVAILABLE。独立诊断定位在驱动导入、未到SQL/TLS。保留首次输出及诊断；改用项目.venv后单次受guard数据库连接和--start通过，未改源码/超时/证书。证据 `storage/runtime/browser-sync-qa/init-attempt1-transcript.txt`、`init-failure-analysis.md`、`pg-diagnostic-venv.json`、`start-venv-attempt2.log`。

A1所有RED、错误解释器、受限临时目录、Node工作目录/导出/对象原型测试错误及明确修正后结果分别保留在 `storage/runtime/browser-sync-qa/protocol/`，不覆盖原失败，不以重跑关闭未知问题。

A2a独立复审修复了nil UUID、null principal与模块额外字段错误接受；保留审查转录、RED和修正后记录。最终规格与质量复审PASS。

## A–P 验收进度（整体尚未验收）

| 场景 | 当前实际证据与缺口 |
|---|---|
| A 同一项目加入 | PC签名公共绑定、浏览器严格预览已有；真实配对正在B2实施，未计通过 |
| B 离线创建与星标 | A2独立浏览器工作区已验证；同一已加入项目的端到端重开待验收 |
| C 连续离线修改 | 稳定mapping与父链、实际浏览器正式密封已验证；真实发送待C |
| D Browser→PC | NOT IMPLEMENTED |
| E PC→Browser | NOT IMPLEMENTED |
| F PC节点暂离线 | NOT VERIFIED；本机进程停止不等于宿主断电 |
| G 双向冲突 | DESIGNED ONLY；三方比较与解决尚未实现 |
| H 不同对象与回显 | NOT VERIFIED |
| I ACK丢失/重复 | vault密文exact retry已验证；真实网络ACK丢失尚未验收 |
| J 保存和接收失败 | 本地IDB/CAS及安全持久化负例已验证；接收整页事务待C |
| K 星标字段隔离 | A2/B1本地即时保存、dirty隔离及协议映射已验证；跨端待C |
| L 版本与身份 | v1/v2/Python/Chromium密码与身份负例已验证；完整网络路径待验收 |
| M 浏览器网络边界 | NOT VERIFIED；严格Linux TLS/CORS待B2，Windows明确未验证 |
| N 撤销与旧epoch | B1 vault撤销/history负例已验证；PC真实撤销与网络待验收 |
| O 旧3A记录适配 | NOT IMPLEMENTED；不能按名字合并或克隆发送身份 |
| P 状态真实性 | 本地工作与可信PC投影已分列；peer receipt与双端状态尚未实现 |

上述局部测试不等于对应完整场景PASS。正常关闭重开、故障注入与真正进程终止分别记录；尚无操作系统断电、实体手机或真实磁盘满证据。

## 当前 Gate

| Gate | 当前状态 |
|---|---|
| G1 项目与协议一致 | INCOMPLETE；仅版本契约已验证，同项目加入/操作映射尚在实施 |
| G2 浏览器安全接入 | NOT VERIFIED |
| G3 本地可靠性 | INCOMPLETE；3A回归通过不替代3B |
| G4 实际双向传输 | NOT VERIFIED |
| G5 冲突与幂等 | NOT VERIFIED |
| G6 人类体验与状态 | INCOMPLETE |
| G7 隔离与回归 | INCOMPLETE；A1回归已通过，后续改动待验收 |

仍在按A→B→C实施。最终A–P矩阵、实际截图、启动停止命令和最小往返步骤将在真实验收后补充；未进入Sprint3C，也未发布生产版本。
