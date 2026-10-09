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

`FAIL / INCOMPLETE`：Linux严格浏览器TLS/真实Fetch/完整UI配对首次CI在启动或版本读取前段失败，具体位置待诊断，见下方首败记录；实际TLS与配对尚未到达。其测试明确区分实际证书/CORS拒绝与 `FAULT_INJECTED_ONLY` 的pin+grant后hello网络中断；仅pin之后、grant之前中断尚未专测。Windows浏览器网络仍未验证。B2b规格与质量静态复审PASS，仍不计完整G2/G4通过；C业务双向传输尚未实现。

## 失败保留

### C1 — 浏览器记录内核差异验证（RH039）

RH039已提交并同步 `8d7afcb1705fd805835efd6d4be1e70bcc29dfd8`；首次 [CI37918402713](https://github.com/Zh9426/ResearchHub/actions/runs/37918402713) attempt1七job全部成功。Linux Chromium156.0.8078.4的24场景差异与B2原入口安全接入均通过，dirty=false，bundle与最终本机hash一致，owned浏览器/子进程清理通过。完整归档 `storage/runtime/browser-local-qa/ci-37918402713-attempt1/`，网络zip `33ec20c06d9c40b2792e51356e65c683d354eb653ea4f70553dec73ff4627c4a`；原TLS固定20轮通过，TLS zip `4e6cee0d09a82f16b29ad86b97eff2df9792fdeb435f0dad6e11264bcc3da7a2`。本地归档解析器最初拒绝新增两个C1摘要路径，失败记录保存 `rh039-archive-parser-failure.json`；只扩入两个精确固定路径后完成解析，原zip按bytes一致性保留，未重跑CI。远端main/v0.2.0与公开状态复核未变。

质量复审发现核心状态缺少项目/模块pin，合法的另一项目context可能与既有state混合；另验收runner对子进程缺少阶段期限。已保留独立复现并修补，规格与质量复审最终均PASS。下方22场景是修补前范围；最终 `c1-local/pins-browser-20261009-01` 为24场景实际PG/浏览器快照通过，bundle SHA256 `ffbf37344d1da2120e8780b3fc3232f07c843d0f9f708863d9a67cb593b3adca`，仍明确dirty工作树。RecordState与receiver都固定项目和模块，含echo也核验pin；原跨项目与换模块两个RED保留 `pins-red-20261009-01`。最终协议59项及两包类型检查经根协调者复验通过；最终PG固定向量pytest在 `c1-local/root-pg-final-20261009-01` 1项通过、4.37秒、无skip。

runner现在直接持有本次独立persistent Chromium句柄，worker只经临时loopback CDP连接；endpoint不上传。oracle/PW子进程各有120秒阶段期限，超时即失败并只回收本次spawn句柄，保存退出元数据。`oracle-timeout-20261009-01`、`worker-timeout-20261009-01` 使用明确挂起子进程故障，两者均FAIL/exit1、timedOut与exited均true，实际浏览器最终清理PASS，单列FAULT_INJECTED_ONLY；不是业务成功或真实数据库死锁证据。原测试网络参数不变。子进程helper两项经独立复验通过。

`IMPLEMENTED / VERIFIED_IN_REAL_BROWSER`：无IO纯TS记录内核复用严格wire/canonical校验；窄Python QA wrapper仅对新普通Run/Note解决事务检查exact当前heads并选择候选提案，旧Kernel不改。普通offline_proposal不升级为ACCEPTED；三个AI principal清空Human字段仍拒绝。保存不可变修订、共同BASE、当前事务状态与首次receipt_state；晚冲突撤回整批和依赖后继投影，保留独立对象，重复回显不增加序列与审计。

`c1-local/browser-diff-20261009-03` 实际Windows Chromium156.0.8078.4，对真实隔离PG逐步比较22场景的heads、修订/文档、事务/回执、候选冲突、投影、依赖、审计、sequence/watermark全部一致。另3组共同BASE由真实旧Kernel合法历史事务构造后与浏览器比较，包含多最大共同祖先返回空。纯页面末项失败保持输入snapshot不变；这不是IDB事务/CAS验收。所有owned浏览器PID已退出。bundle SHA256 `da3ec23a1035fbee07e5da41fbd440ef7c7c9aec233ce61951005918f8f8fcc1`，当时sourceCommit为RH038且workingTreeDirty=true，不能当作RH038已包含C1。

协议57项与类型检查通过（根协调者独立复验），新增PG pytest 1项通过；pytest cache权限warning单列，不影响测试结果。`c1-local/`保留oracle-red01夹具外键错误、oracle-red02四个语义差异、core-red01十九项失败、offline-red01两项错误ACCEPTED、ai-red01三项权限差异，以及修补后结果。browser-diff01是entry路径构建错误，未执行浏览器；02首次22场景通过，03增加状态元数据、历史BASE和进程清理验收。未覆盖原失败，没有放宽原规则。C2实际IDB接收、传输与操作界面尚待实施。

### B2 实际安全接入验收（RH038）

完整首次CI最终7个job全部通过；归档 `storage/runtime/browser-local-qa/ci-37915243012-attempt1/`。原TLS固定20轮通过，TLS zip SHA256 `682b9823bf0ffce91e89e3113d475506766a3e831a67cded73a98aa30a01549c`；旧3A浏览器17项与B1密码10项通过。该结果不覆盖RH033–RH037首败，也不关闭TLS-001。

提交 `97fe70cfbac1d6fca3c17c8ff742b687c303eb45` 已与GitHub开发分支同SHA同步。首次 [CI37915243012](https://github.com/Zh9426/ResearchHub/actions/runs/37915243012) attempt1的网络job通过，retries=0。Linux Chromium156.0.8078.4，新OS账户、独立NSS/profile；trusted流程到达COMPLETE，3次成功OPTIONS、2次签名POST，原38001 HTTPS入口。真实UI完成同一空项目加入、原生证明、签名绑定与module内容/双hash校验、receipt刷新重取。错误CA、错误hostname、无效proof、opaque未授权origin的真实拒绝均通过；pin/grant后hello故障为显式route.abort注入，移除注入后由用户动作恢复，单列FAULT_INJECTED_ONLY。

两浏览器关闭与owned服务退出均通过，新账户最终进程为空。安全摘要与完整网络工件保留 `storage/runtime/browser-sync-qa/rh038-network-diagnostic/`，zip SHA256 `63cdcbb39e45d3639d348817bc7f47c4b0728d5003a19557d330fc5e210e6790`。实际脱敏页面：[桌面](evidence/sprint3b/b2-trusted-desktop.png)、[390px视口](evidence/sprint3b/b2-trusted-mobile-viewport.png)，输入区由Playwright遮盖；只证明加入阶段，非双向业务。浏览器构建hash `f283ee604f1e28041a5280cd529aff80814322c075ca9e204616dcd428a4b66d`。Windows浏览器HTTPS仍NOT VERIFIED，非空历史bootstrap未实现，TLS-001/PC013仍OPEN。下一内部检查点为C。

RH037（`8cd1005f3b27575a4fbe1db583c63147559c6111`）首次 [CI37913330768](https://github.com/Zh9426/ResearchHub/actions/runs/37913330768) attempt1：六个既有job通过，网络job仍FAIL。隔离Chromium156.0.8078.4已实际启动；错误CA拒绝通过，trusted流程通过错误hostname拒绝后到达`OWNER_START`并失败，尚无正向browser Fetch（preflights/signedPosts均0）。清理前继承XDG目录仍EACCES；清理后两个账户均为HOME_FALLBACK、目录实际位于自己的home且临时目录创建/清理成功；browser close与账户进程归零均通过。因此只确认启动隔离补丁有效，不计完整B2通过。

完整归档 `storage/runtime/browser-local-qa/ci-37913330768-attempt1/`：失败日志zip `35610910e1c7e659962068e61b8e07ca7bceb139bd49aaccec01880ade167ae7`，网络zip `5787a7038c8cbbcc078680f565f710d01a9a9d359c4a963f21d6f3e9e268dfba`，TLS zip `0bf405f4bfdeb8aeee2c7eb3f9c2cd5bc74beb8024ab26372cde0ca43d8cabfe`。原固定20轮通过仍不关闭TLS-001。未重跑该SHA。

RH038定向定位：PC配对接口要求canonical JSON字节，界面适配器却使用普通JSON.stringify。独立本机合成节点与新profile在 `b2-local/owner-canonical-red-20261009-01` 实际复现start422 `CANONICAL_PAIRING_REQUEST_REQUIRED`；原Linux CI只有阶段与错误摘要，不能说直接取得了其HTTP422。最小修补仅start/confirm/resume三个配对路径的编码；后端校验不变。新节点/profile的 `owner-canonical-green-20261009-01` 实际Chromium用例1项通过：start200、B原生WebCrypto证明、confirm200 COMPLETE。类型检查与授权后普通PC构建通过；首次sandbox构建EPERM保留于 `owner-canonical-build-20261009-01`，成功构建另存02。本地验证涉及PC严格TLS路径，未验证Windows浏览器Relay Fetch；新SHA Linux首次验收仍待执行。

RH036（`7d54e1d89e696442c058dfcb5af69fdbc1a27acb`）首次 [CI37912368218](https://github.com/Zh9426/ResearchHub/actions/runs/37912368218) 网络 job FAIL，已保留 `storage/runtime/browser-sync-qa/rh036-network-diagnostic/`，网络zip `75f597dbcf6aa14ba7b8047abc46f5be5fe3018e5454754304f4a872fae4b2a5`。同一新OS用户、相同cwd和环境的Node探针观察到：`selector=XDG_CONFIG_HOME`，路径为绝对路径且实际/词法均在home外，最近目录访问 `DENIED / EACCES`，未尝试外部写入；实际HOME仍匹配账户。随后Chromium仍在BROWSER_LAUNCH以CRASHPAD_DATABASE_REQUIRED/SIGTRAP退出。该观测确认继承配置目录的隔离缺口，与官方源码所示初始化失败链吻合；探针本身不证明运行中二进制路径或修补后网络已通过。

RH037修补仅在QA浏览器子进程移除继承的CHROME/XDG目录覆盖，依赖新账户真实home的标准默认目录，不重写HOME、全局环境或ACL。保留清理前观测，并在相同干净环境中核验清理后目录与启动。修补效果必须由新提交首次实际Chromium验收确认，原失败与TLS-001仍保留。

RH036完整归档 `storage/runtime/browser-local-qa/ci-37912368218-attempt1/`：失败日志zip `69ab269c1c8cdb5dfe03780822fb66dcf63ce5bddb4a66401d4209beeba4ff15`；TLS zip `fdf016b3d19276841246e5efa90ed8a98c86203523e526b86e349956d3017206`，六个既有job与原固定20轮通过，网络仍FAIL。RH037定向Python回归7项、Node探针5项通过；证据 `b2-local/clean-browser-env-{red,green}-20261009-01` 与 `clean-browser-probe-green-20261009-01`，不计实际Linux修补后运行通过。

RH035（`0495bc920ba522a76caf81bd0c0b2492b3ffed72`）首次 [CI37910732229](https://github.com/Zh9426/ResearchHub/actions/runs/37910732229) 网络 job 仍 FAIL：`BROWSER_LAUNCH / CRASHPAD_DATABASE_REQUIRED`，退出 `SIGTRAP`，未取得 context，TLS/OPTIONS/签名请求均未到达。该错误的上游目录/环境原因待追踪，不能通过关闭Crashpad或放宽浏览器安全设置回避。网络产物zip `30ab945fd10340369b9e3b9116810a3b49659c91c1fb05866e6bb77cc0dc41d5` 已独立保留于 `storage/runtime/browser-sync-qa/rh035-network-diagnostic/`。

本次确认实际HOME等于新OS账户home；两个owned UID的 `loginctl terminate-user` 均exit0，终态ps均exit1且进程列表为空，无cleanupFailures。因此仅账户会话清理缺口有真实Linux修复证据，浏览器启动与B2网络Gate仍失败。RH035标准Git推送遇到github.com:443连接超时；经官方Git Data API逐个验证相同blob/tree/commit SHA后，以force=false同步同一提交，并复核main/v0.2.0不变。传输诊断保留 `rh035-push-transport-evidence.json`，没有重跑原CI或替换失败归档。

RH035完整CI已结束：六个既有job通过，网络job失败；归档 `storage/runtime/browser-local-qa/ci-37910732229-attempt1/`。失败日志zip `74b61422926c099e1eba4b922de89e0183f49d5a64d7bb41a710e16f9f1d233c`；TLS zip `ecf47a7189cdbd35a953a4c30805e6e5a4ab30483a5c1842ed7591c1a4bfc466`，原固定20轮通过。TLS-001仍OPEN，本次网络失败不获豁免。

RH034（`9452ca9de9c78e7c7682b8fe83ecc23744dc5716`）首次 [CI37909229321](https://github.com/Zh9426/ResearchHub/actions/runs/37909229321) attempt1 再次 FAIL，六个既有 job 通过。新增诊断确定失败为 `BROWSER_LAUNCH / BROWSER_CLOSED`，尚未取得 context，cleanup 为 NOT_STARTED、TLS/请求计数仍0；错误摘要hash `828d513e6f41ef9381ac65efe50a8abfc7d80ee4009e8443f7609b11e1ea0d47`。浏览器具体关闭原因仍 UNKNOWN。两个新UID在NSS准备后与最终快照均只有 systemd（PPID1）及其 sd-pam 子进程，说明这部分清理缺口是本次 sudo login 创建的账户会话资源。

完整归档 `storage/runtime/browser-local-qa/ci-37909229321-attempt1/`：失败日志zip `c0ea94b083039be9959e6fc0cc4cbd052c030edd7a865f27cff3e150c7dbb37b`；网络zip `b84949c33e48ecb5be38dcab8476f1648c3078ba7d85791d0e5bcf9750ac58e2`；TLS zip `23dc97a1280166400ddaaa5cf79613841c26fee4dd8c7f56590cbf4bf979e57c`，原固定20轮通过仍不关闭TLS-001。

后续最小补丁区分两件事：启动错误增加固定退出码/信号和官方已知启动错误分类，不改变launch flags；新建UID的会话使用显式 `loginctl terminate-user` 释放，要求最终零进程，任何额外浏览器/未知进程仍先记FAIL。该命令的范围依据 [systemd官方手册](https://raw.githubusercontent.com/systemd/systemd/main/man/loginctl.xml)，仅应用于本次成功useradd得到的UID，不触及个人会话。进程分类及竞态4项和退出诊断3项纯测试通过；实际Linux清理待新提交首次CI，不计修复验收通过。

RH033 首次 [CI37907069953](https://github.com/Zh9426/ResearchHub/actions/runs/37907069953) attempt1、提交 `c6109d65654a5418c0626d52ac51bb2eac22d415`：六个既有 job 通过，新增 browser-network-qa 失败。`browser-untrusted` exit1，摘要停在 START、Chromium版本为空、证书诊断为空、OPTIONS/签名POST均0；尚不能确认浏览器是否成功启动，不能计错误CA拒绝通过。trusted用例未执行。两个新QA账户均有残留进程；PC与静态服务明确owned停止exit0。网络Gate为 FAIL / INCOMPLETE，根因调查中，不重跑该提交覆盖首败。

原始归档 `storage/runtime/browser-local-qa/ci-37907069953-attempt1/` 保留：失败日志zip SHA-256 `f437d0abbdd3953f3ed3db7fb196d18d5a18634b6d19dae7d1feb4c4bd5505ae`；网络zip `dbdddcb3367e47430cbeded54017bb7c17e71577eafb8d45e83925102141ddc9`；TLS zip `e97ffa1eb18f9dd816bb786a797909c1fc065830c50b89f54ce5a86dabf8c681`。原TLS固定20轮通过不关闭TLS-001，也不豁免本次网络失败。后续诊断将区分启动、测试配置和新账户会话进程；不改变证书规则或失败判定。

B2a收尾遇到环境中断：`pc/b2a-regression-03` 没有退出状态/JUnit，不能计通过。继续执行的 `b2a-regression-04` 期间35433/35434/38001均不可达，核验Docker Linux engine未运行；保存 `environment.txt` 后仅终止该轮明确owned等待进程，记录 `ENVIRONMENT_BLOCKED/CANCELLED`、exit -1。后台启动Docker Desktop、核对既有QA scope并只start原容器，原Relay `--start` guard成功；没有init/destroy/清库、重建身份或调整超时/证书。恢复记录在该轮 `restore.txt`，后续新attempt结果单列。

本轮第一次Relay初始化使用PATH中的Anaconda Python，缺少psycopg；被既有就绪检查包装为QA_PG_UNAVAILABLE。独立诊断定位在驱动导入、未到SQL/TLS。保留首次输出及诊断；改用项目.venv后单次受guard数据库连接和--start通过，未改源码/超时/证书。证据 `storage/runtime/browser-sync-qa/init-attempt1-transcript.txt`、`init-failure-analysis.md`、`pg-diagnostic-venv.json`、`start-venv-attempt2.log`。

A1所有RED、错误解释器、受限临时目录、Node工作目录/导出/对象原型测试错误及明确修正后结果分别保留在 `storage/runtime/browser-sync-qa/protocol/`，不覆盖原失败，不以重跑关闭未知问题。

A2a独立复审修复了nil UUID、null principal与模块额外字段错误接受；保留审查转录、RED和修正后记录。最终规格与质量复审PASS。

## A–P 验收进度（整体尚未验收）

RH038规格复审另发现测试清理串行调用可能因证据写入或浏览器close失败漏停owned PC。修补为各步骤独立执行，主错误与全部清理错误一并抛出；确定性RED 3失败/1通过，GREEN 4通过，保存于 `b2-local/owner-cleanup-{red-20261009-02,green-20261009-01}`。red01是sandbox spawn EPERM，单独保留，不计业务RED。根协调者独立执行4项测试和tsc通过；该测试已纳入CI，不以捕获异常继续成功。

| 场景 | 当前实际证据与缺口 |
|---|---|
| A 同一项目加入 | RH038真实Linux UI完成同一空项目加入、双hash与身份绑定；非空历史bootstrap未实现 |
| B 离线创建与星标 | A2独立浏览器工作区已验证；同一已加入项目的端到端重开待验收 |
| C 连续离线修改 | 稳定mapping与父链、实际浏览器正式密封已验证；真实发送待C |
| D Browser→PC | NOT IMPLEMENTED |
| E PC→Browser | NOT IMPLEMENTED |
| F PC节点暂离线 | NOT VERIFIED；本机进程停止不等于宿主断电 |
| G 双向冲突 | DESIGNED ONLY；三方比较与解决尚未实现 |
| H 不同对象与回显 | NOT VERIFIED |
| I ACK丢失/重复 | vault密文exact retry已验证；真实网络ACK丢失尚未验收 |
| J 保存和接收失败 | 本地IDB/CAS及安全持久化负例、真实整页IDB接收已验证；完整网络失败路径待验收 |
| K 星标字段隔离 | A2/B1本地即时保存、dirty隔离及协议映射已验证；跨端待C |
| L 版本与身份 | v1/v2/Python/Chromium密码与身份负例已验证；完整网络路径待验收 |
| M 浏览器网络边界 | RH038实际Linux严格TLS、直接Fetch、CORS正负例通过；Windows未验证，C业务路径仍待验收 |
| N 撤销与旧epoch | B1 vault撤销/history负例已验证；PC真实撤销与网络待验收 |
| O 旧3A记录适配 | NOT IMPLEMENTED；不能按名字合并或克隆发送身份 |
| P 状态真实性 | 本地工作与可信PC投影已分列；peer receipt与双端状态尚未实现 |

上述局部测试不等于对应完整场景PASS。正常关闭重开、故障注入与真正进程终止分别记录；尚无操作系统断电、实体手机或真实磁盘满证据。

### C-接收 — 授权镜像、整页提交与离线因果来源（RH040）

RH040已提交并同步 `7b5ee670d97ff3f05211da73cbac76875082bc0f`；首次 [CI37922293892](https://github.com/Zh9426/ResearchHub/actions/runs/37922293892) attempt1七job全部成功。Linux真实Chromium23项接收与24项C1差异通过，sourceCommit精确匹配、dirty=false、bundle与最终本机一致；B2原入口严格TLS配对仍通过。完整归档 `storage/runtime/browser-local-qa/ci-37922293892-attempt1/`，网络zip SHA256 `4b22932615f2568718a029556f40a25776767868931c25645c274cf55a96d964`，TLS zip `99bb9751d41ce43af3e60b0bc9f1cca7d6e5ec6847f3c3406f0fe458483cb41d`；原TLS固定20轮通过。远端main/v0.2.0及公开状态复核未变。此次成功不关闭TLS-001或PC013。

本片 `IMPLEMENTED / VERIFIED_IN_REAL_BROWSER`，尚未接通真实 Relay 双向业务。正常加入经统一授权协调器：先在业务库写 BLOCKED 与 generation/token，再安装独立 vault，最后短事务 CAS 发布 READY。安装中断保留 BLOCKED；完整相同安装重试不增加 generation。已有绑定缺少授权镜像时明确阻断，不能从 vault 自动恢复为可信。

接收先在事务外完成整页原生验签、AEAD、身份、epoch、摘要与记录内核计算，再在短 IDB 事务复核授权、kernel 和 Relay cursor，原子写修订、接收结果与游标。Relay cursor 与 kernel sequence 分开。保存操作时在同一事务冻结前一待发送操作或已知基线；转换把本地分支加入 kernel，远端更新不能把离线修改改接到新父修订。原操作与审计不重写；独立 pending/handoff 标记只匹配具体 operation/transaction/version。交接后继续编辑读取当前 kernel 基线，冲突不选择赢家。PC 仅在 pending 时显示工作副本，命令锁序统一为 Trust→Project→Work。

身份边界复审前的本机独立验收命令 `node apps/browser-qa/scripts/receive-qa.mjs root-receive-20261009-01`：Windows Chromium156.0.8078.4、16场景 PASS、retries=0、owned cleanup PASS；摘要在 `storage/runtime/browser-sync-qa/c-receive/root-receive-20261009-01/summary.json`，bundle SHA256 `e9d9c2ed4814510d88f3cc6e725ab44be325915286a9207202fcb864c1c1a91e`。sourceCommit 为 RH039、dirty=true，不能称为已提交 RH039 的功能。覆盖安装三断点、有效外层链下坏签名/坏AEAD、整页末项协议失败、实际IDB abort、撤销与并发kernel CAS、旧epoch不跳游标、稳定重试、handoff与后续编辑。页面由明确 TEST_ONLY 合成授权 fixture 准备；浏览器实际处理密钥与完整 envelope，但没有调用 Relay，不能算网络通过或 Windows HTTPS 通过。

失败证据保留在 `c-receive/red-authorization-*`、`red-causality-001`、`red-post-handoff-001` 和各独立 green/adversarial attempt；名称为 green 不代表当次一定通过，以摘要为准。交接后继续编辑最初错误引用旧基线，由真实 RED 定位并修补。PC 的 `c-receive-pg-red-20261009T104206767` 和 `c-receive-pg-lock-red-20261009T105521544` 分别保留缺少handoff服务及实际SQL锁序失败；对应两次定向绿色证据另存。原A2五项、B1十项及正常加入本地UI两项回归通过；原3A本机runner会覆盖固定旧证据，本次不在本机重跑，保留CI原套件验证。根协调者类型检查与网络诊断七项通过；独立真实PG `test_pc_records.py test_pc_api.py` 六项通过、零skip，JUnit/stdout/exit码保存 `c-receive-pg-root-20261009-01/`，另有一条第三方Starlette/httpx弃用警告。

质量复审另发现P2：正式内核以类型+UUID区分对象，当前本地表只用UUID，同UUID的Run/Note可被内核接受却在投影中漏掉一种。纯函数复现记录为 `review-typed-identity-finding.json`；随后 `red-local-identity-001` 真实Chromium同时确认七种身份碰撞被接受并改变持久状态。最小修补在staging拒绝不可表达的同UUID多类型，并在写事务内校验现有object/baseline/pending来源的项目与类型；handoff共用检查，不改变正式内核规则或重分配UUID。`green-local-identity-001` 与根协调者独立 `root-receive-final-20261009-01` 均23项PASS、cleanup PASS、retries=0，bundle SHA256 `1e334a351dd2907db448e89d8983d41d0dd51e6f84671ce182854f63d2714fb5`；碰撞时meta/objects/operations/audit（包括kernel/cursor/receipts）完全不变。该明确阻断是当前本地模型限制，不声称已支持复合对象键。最终类型检查通过。SPEC复审与P2修补后的QUALITY复审均PASS；精确SHA首次CI结果见本节开头。

后续仍需 PC secure receiver 的可信 record policy 接入、PC Outbox→sealed bridge、手动双向传输、设备签名应用回执、冲突界面、显式旧3A导入及完整A–P验收。本片不宣称完成这些范围；TLS-001/PC013继续OPEN。

### C-传输 — 持久发送与设备应用回执（RH041，网络首败保留）

RH041 `2fcdf3cc1a00f481354f137dc743a73f52e04c6a` 已提交且远端同SHA。首次 [CI37928298229](https://github.com/Zh9426/ResearchHub/actions/runs/37928298229) attempt1六job成功、一job失败：实际Linux浏览器停在 `C_B_NATIVE_EDIT_UI`，错误摘要类型Error、SHA256 `30e52582a198b140843bb8de4972de8b693e1749ded236b6d516001fcf90becb`，retries=0、cleanup PASS。该阶段之前的正常配对、PC baseline发送、B接收和PC验证三条应用回执断言已通过；浏览器编辑/发送/PC应用/回执确认中的具体失败步骤尚不能从现有粗粒度摘要判定。不得据此声明完整双向通过，也没有证据把它归因于原TLS EOF。下一补丁先增加固定安全子阶段与白名单诊断，不猜改业务、放宽断言或重跑同SHA。

完整首败归档 `storage/runtime/browser-local-qa/ci-37928298229-attempt1/`：失败日志zip SHA256 `fc32a3068dfc81855f5ceb17b1f1ad156a700c1097e4106b20e3f4356f764686`，网络zip `7c196eed91344bb80b71cc4a077e62281dd1c6a74e1c3ecda162c53ac701384c`，TLSzip `c58bb08c8ba5755cab232c132af6db8b102e79ca4a030d46733c525962fe4095`。原TLS固定20轮通过、错误CA确切拒绝通过，但不覆盖本次业务失败；TLS-001/PC013继续OPEN。本次未到SCREENSHOTS阶段，没有新增最终业务截图。

RH041同SHA的Linux原生接收30项、C1内核差异24项、旧3A和浏览器安全套件通过；接收摘要dirty=false、bundle与本机最终相同。RH042仅补首败观测：原阶段拆为固定子阶段，错误位置只允许两份网络测试源码文件名及有界行列（最多八项），UI同步诊断只匹配现有固定错误码；其余内容不导出。诊断读取失败仍重新抛出原业务断言，不继续成功。根协调者独立Node诊断五项和类型检查通过；缺少位置字段的实际RED、测试进程EPERM分别保留。未改业务、原断言、超时、TLS参数或重试次数，不声明已经修复RH041首败。

当前工作树新增 PeerApplyReceipt v1 的 Python/浏览器独立验证及 Relay 不可变存取；签名绑定具体目标设备、项目、原消息、事务/密文摘要和 epoch。回执来自已提交接收结果并先缓存后发送，只表示历史应用事实。PC 新桥接保留原 Outbox 事务与稳定 message ID，密封在短 PG 事务外执行；完整密文提交后才允许网络发送。两端手动周期采用持久claim、固定集合、有界批次与原密文重试。尚无本片严格 HTTPS 的实际 UI 往返通过证据，不能据此提升 G4/G5。

复审前定向测试34项通过（`transport-attempts/6e502fe3-5726-4657-a3af-149bf9c9d7b3/final-targeted.txt`），完整 Python 安全测试205项、TypeScript安全测试59项通过；一次第三方Starlette/httpx弃用警告保留。根协调者真实 Windows Chromium `c-receive/root-transport-native-20261009-01/summary.json` 27项、cleanup PASS、retries=0，sourceCommit为RH040且dirty=true，bundle SHA256 `95fdf56c1c0c49e51e9e52fb4da232a0ca7c16632be0c517896ae40c58605461`。包括原生非导出签名、持久回执exact retry、并发claim和空页不改变编辑版本；这是浏览器组件验证，不是 Windows Relay HTTPS。此前worker构建与最终代码不同，各摘要独立保留，不混用bundle哈希。

首次独立SPEC复审提出两项P2：PC路由清理异常可能覆盖主错误；普通界面缺少当前记录对应的持久中继/目标设备状态，固定UNCONFIRMED诊断也会误导。保留原RED与每次定向修正后的结果；`transport-attempts/evidence-index.txt` 中早期条目是原工具输出索引，不冒充原始日志。完整 UI 联调、冲突解决、显式3A导入与A–P失败验收仍待后续。

上述两项已完成补丁，SPEC与QUALITY独立复审均PASS：路由双异常先出现实际RED（`fef973bc-11be-469f-826d-233d1e55dda6`），随后3项通过（`368a0141-98c5-4b4e-a45b-99ee817e4b82`）。新增白名单状态投影每次只对应最近保存操作，验证具体peer签名，不借用旧操作回执；当前DAG冲突与历史应用状态分列。PC无本地工作版本的远端Run原先隐藏观察/星标，真实组件RED `spec-ui-red-3a9ac0d1-b2dd-4d7f-8fdd-284d0139b2ca` 后改用独立“曾持久化”编辑状态。随后 `spec-dirty-red-0f90e3e2-ccbc-4958-8761-84ff1050f999` 又复现冲突移除投影后脏观察被隐藏，补丁保持字段可见且不改CAS版本。两次fixture前置错误、一次UTF8补丁未应用后的重复RED均单独保留，不计业务修复成功。

冻结候选最终定向PG/协议组合37项通过（`4454b21a-8638-44d8-bfac-1c464eb11fb2/final-targeted.txt`），类型检查与普通B/PC构建通过。根协调者独立真实Chromium `root-transport-final-20261009-01` 30项、cleanup PASS、retries=0，bundle SHA256 `aee15af7f173d903256767068191456debde4c164f4bda148a61463326794648` 与worker最终构建一致。覆盖Relay-only、新保存不借旧回执、旧ACCEPTED回执同时存在当前冲突、version0记录与脏输入可见。source仍为RH040加未提交工作树，不能称为RH040已实现。新增实际Linux UI往返断言已经接入原测试，尚未运行。

## 当前 Gate

RH038质量复审发现READY前停滞无法取得清理句柄的旧helper缺口，本次新回归复用该路径，故补受限启动检查：15秒未就绪即失败，只回收本次spawn的子进程，最多5秒等待退出；未产生PID不等待不存在的exit，清理失败与原错误一并保留。不修改PC服务、TLS或已有网络超时。`b2-local/owner-start-red-20261009-01` 保留1失败/2通过；`owner-start-green-20261009-03` 四项通过（无READY、提前退出、spawn失败、分段READY/监听器清理），根协调者独立复验四项和tsc通过。

| Gate | 当前状态 |
|---|---|
| G1 项目与协议一致 | 局部已验证：同项目加入、版本契约、稳定操作与父链；完整往返集成待验收 |
| G2 浏览器安全接入 | B检查点PASS；B1正式密码与RH038实际Linux配对/严格TLS/Fetch通过，后续C变更仍需回归 |
| G3 本地可靠性 | INCOMPLETE；3A回归通过不替代3B |
| G4 实际双向传输 | FAIL / INCOMPLETE；RH041首次CI停在C_B_NATIVE_EDIT_UI，已保留证据，尚未定位具体失败操作 |
| G5 冲突与幂等 | NOT VERIFIED |
| G6 人类体验与状态 | INCOMPLETE |
| G7 隔离与回归 | INCOMPLETE；A1回归已通过，后续改动待验收 |

仍在按A→B→C实施。最终A–P矩阵、实际截图、启动停止命令和最小往返步骤将在真实验收后补充；未进入Sprint3C，也未发布生产版本。

### RH042 — 首次诊断定位（未结案）

RH042 `86083ba304ec50733e3812330e789dff6eccfef2` 已同步；首次 [CI37930528881](https://github.com/Zh9426/ResearchHub/actions/runs/37930528881) attempt1 的网络测试再次失败，固定阶段为 `C_B_READ_BASELINE_RUN`，源码位置 `manual-roundtrip.ts:13:146`：浏览器选中 Run 后，观察字段未满足 PC 第二次保存内容的断言。此前 PC 三笔 baseline 发送、B 接收及 PC 验证三条应用回执断言已越过；B 本地修改与发送尚未执行。此证据缩小本次失败范围，尚不能判定 PC 保存、接收投影或表单读取中的具体根因，也不能反推 RH041 必然同因。

原 artifact 保存在 `storage/runtime/browser-sync-qa/rh042-network-diagnostic/network.zip`，SHA256 `914fb795c375d283ab3a004bbf0d28116317c3923d108953bf1bdaa3b68eafa1`；安全错误摘要 SHA256 `93e93ec8d26f74ef083459e73890b4e25b369401a3d84579b8a009d64c07b5b4`。Linux Chromium156.0.8078.4、Node24.21.0，B 构建 SHA256 `db6fb41960633d2b67329030dbb593eb863332e060ddefa5c503c0f1e1f85f4c`；retries=0、cleanup PASS、错误CA拒绝通过。保留 RH041 首败与 RH042 独立证据；G4 仍 FAIL/INCOMPLETE，TLS-001 与 PC013 仍 OPEN。下一步以实际 RED 定位后作最小补丁，不更改该内容断言或安全边界。

同次 CI 最终为五 job 成功、两个 job 失败。除上述浏览器基线读取外，`secure-relay-qa` 在 `test_expired_revoked_epoch_requests_rejected_before_cache` 的未来时间 `issued_at=1791549286+6` 负例（test_security.py:90）收到 200 而预期 401；尚未越过该断言进入后续撤销检查。先保留并单独调查，不能据用例名称断言撤销绕过，也不能未经诊断称为时钟边界抖动。原 TLS 固定20轮全部通过，仍不关闭 TLS-001。完整归档 `storage/runtime/browser-local-qa/ci-37930528881-attempt1/`，失败日志zip SHA256 `172f47c8f647151821f7aeb2cffce4d534002da6eb0aeca408609edae3870458`，TLSzip `2063ff95be76b3a30731c3fe3dc23b5e6c58908ddce6ec4780858c6c6e92e97b`。G7 本次也不能记为 PASS。

RH043 候选只增加定位覆盖，尚未修复串联失败：PC 的实际 Chromium/独立QA PG三次连续保存验证（`pc/baseline-6d9990df-ff5a-4c89-be56-dad48d303469/test.txt`）1项PASS，第二次请求与工作副本/可信投影观察一致；新fixture早期超长node名称导致启动失败另存，不计产品RED。B原生同页 Run创建、更新及Note接收后读取普通工作台，通过31项组件检查（`c-receive/baseline-receive-d169c962-f4ed-421f-a817-8ce624689359/summary.json`），Chromium156.0.8078.4、retries=0、cleanup PASS、bundle SHA256 `591908563d4bae5f227b2a413f7569dabdc1065c4c8bbc7079468a05e737e62f`，测试时sourceCommit为RH042、dirty=true。两者没有复现网络首败，不能冒充根因修复。

原观察断言失败时新增仅含DOM/local/kernel三键的枚举诊断，分别判别缺失、预期/非预期等状态；不输出正文、UUID、proof。IDB只读，数据库缺失时abort，诊断异常后仍抛原断言。原网络超时、断言、retries与TLS设置不变。缺少诊断函数的单测RED单独保留（`transport-attempts/94be7c97-fd3c-45c3-a310-107c3af21188/`）；新增实现后六项通过，根协调者独立六项及类型检查亦通过。精确SHA网络结果仍待后续首次CI。

RH043已提交并同步 `6448d3e38af294aa4f097223501f345e73a5ebd6`，首次 [CI37940691305](https://github.com/Zh9426/ResearchHub/actions/runs/37940691305) attempt1六job通过，browser-network job在新增原生接收/普通界面读取回归失败，未进入后续HTTPS往返。错误为读取未找到的按钮时 `TypeError: Cannot read properties of undefined (reading 'click')`，真实Chromium156.0.8078.4、cleanup PASS、同bundle `591908563d4bae5f227b2a413f7569dabdc1065c4c8bbc7079468a05e737e62f`。初步排查发现多个独立fixture项目使用同route_alias，尚待确定性隔离复现；不以本机通过覆盖CI失败，也不跳该回归。原TLS20轮通过，future负例本次通过不关闭RH042调查。

完整归档 `storage/runtime/browser-local-qa/ci-37940691305-attempt1/`，失败日志zip SHA256 `49776e31013e08fd3e98c239e726ab47d0aa8333194b565974242c8f829adff5`，网络zip `545a4426743fc365c5859a8141aebbcf32c2b77045a955341aa20b5a539189c7`，TLSzip `5f4cbdb57a294ffe63681f42ed5ed495316f6ebcb25fe4251be2c907d280f9a2`；单job私有日志另存 `rh043-network-diagnostic/job-private.log`，SHA256 `aabcdf481bef7a6359f87681b472922dedb257bbd373d64aa221c9e8cf9d35b3`。本次无新的HTTP业务根因证据或最终截图，整体仍INCOMPLETE。

### 请求时间边界的确定性验证（RH044候选）

仅修改测试：使用真实合成Ed25519签名与固定now覆盖 `-61` 拒绝、`-60/+5` 允许、`+6` 拒绝；另在真实隔离QA PostgreSQL调用既有 `service.execute(now=...)`，同一签名在T拒绝且不生成receipt，T+1合法并建立缓存，缓存后再次以非法时间调用仍拒绝。错误假设“到T+1仍必须拒绝”的确定性RED为1 failed，独立保留。它证明跨秒机制能够解释RH042现象，但原CI缺鉴权now，原首败原因仍未实证。

真实网络用例保留原函数及所有安全断言，明确将唯一未来偏移参数由 `+6` 改为 `+3600`，用于验证明显超出允许窗口的请求；精确+6边界由固定时刻测试承担，不再将客户端取时当作服务端鉴权时刻。生产规则、鉴权先于缓存的顺序、原TLS pooled/fresh用例与参数均未修改。没有新增HTTP时钟控制接口或修改系统时间。

证据 `storage/runtime/browser-sync-qa/request-time/e4213146-1e72-4744-a721-5d3fe0dcdf21/` 包含RED、GREEN、JUnit、命令失败和SHA256清单。单元4项、真实PG服务加完整安全文件34项通过，零skip；privacy hits=0、ruff通过，owned Relay/ingress已正常停止。首次命令参数错误exit4未收集测试，原日志单独保留。根协调者独立四边界4项通过；pytest缓存目录权限警告保留，不涉及断言。以上PG固定时刻验证不是HTTP时序实测，RH043的未修改未来负例再次通过也不是RH042结案依据。五项保护文件hash复核不变，TLS-001继续OPEN。

### RH043夹具隔离失败的最小修正（RH044候选）

新增组件测试复用同一TEST_ONLY数据库，多个随机UUID项目共享generic别名；Workbench按别名选择首个项目。确定性把真实旧项目排在新项目前，持久观察断言通过后目标按钮缺失，保存RED `c-receive/fixture-order-red-3168ca8b-81b7-4758-92cf-24cca9beb012/`。更早的RED前置条件误要求旧项目仍有accepted对象，另存500e3132…，不计因果复现。

最小补丁只按目标project ID过滤该测试组件snapshot中的projects/objects，未修改产品alias、真实接收数据或网络断言。两种输入项目顺序分别实际挂载、选择、读取，原31case保留并新增第二种顺序，合计32项。worker `fixture-order-green-e7e6b960-3fc6-4a7f-9e98-d8549815be11` 与根协调者 `root-fixture-order-20261009-02` 均32 PASS、cleanup PASS、retries=0，Chromium156.0.8078.4，bundle SHA256 `fad7429d668b572fbe3f7eaa4f02319f405e963bec51bc3700aa50ba01f7d76f`。root首次01未指定项目browser路径，启动前Executable missing失败另存；纠正环境后02运行，未安装或放宽浏览器安全。类型检查通过。此修正针对RH043新增测试隔离，不声称RH042网络基线读取已修复；新增固定枚举诊断仍待实际HTTPS用例运行。
