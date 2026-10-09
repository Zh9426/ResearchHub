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
| M 浏览器网络边界 | FAIL / INCOMPLETE；RH037实际Chromium启动、错误CA/hostname拒绝已有证据，OWNER_START失败，正向Fetch/CORS尚未通过；Windows未验证 |
| N 撤销与旧epoch | B1 vault撤销/history负例已验证；PC真实撤销与网络待验收 |
| O 旧3A记录适配 | NOT IMPLEMENTED；不能按名字合并或克隆发送身份 |
| P 状态真实性 | 本地工作与可信PC投影已分列；peer receipt与双端状态尚未实现 |

上述局部测试不等于对应完整场景PASS。正常关闭重开、故障注入与真正进程终止分别记录；尚无操作系统断电、实体手机或真实磁盘满证据。

## 当前 Gate

RH038质量复审发现READY前停滞无法取得清理句柄的旧helper缺口，本次新回归复用该路径，故补受限启动检查：15秒未就绪即失败，只回收本次spawn的子进程，最多5秒等待退出；未产生PID不等待不存在的exit，清理失败与原错误一并保留。不修改PC服务、TLS或已有网络超时。`b2-local/owner-start-red-20261009-01` 保留1失败/2通过；`owner-start-green-20261009-03` 四项通过（无READY、提前退出、spawn失败、分段READY/监听器清理），根协调者独立复验四项和tsc通过。

| Gate | 当前状态 |
|---|---|
| G1 项目与协议一致 | INCOMPLETE；仅版本契约已验证，同项目加入/操作映射尚在实施 |
| G2 浏览器安全接入 | INCOMPLETE；正式密码与实际证书负例已有证据，RH037配对阶段失败，正向网络待新补丁首次CI |
| G3 本地可靠性 | INCOMPLETE；3A回归通过不替代3B |
| G4 实际双向传输 | INCOMPLETE；B2网络测试失败，C尚未实现 |
| G5 冲突与幂等 | NOT VERIFIED |
| G6 人类体验与状态 | INCOMPLETE |
| G7 隔离与回归 | INCOMPLETE；A1回归已通过，后续改动待验收 |

仍在按A→B→C实施。最终A–P矩阵、实际截图、启动停止命令和最小往返步骤将在真实验收后补充；未进入Sprint3C，也未发布生产版本。
