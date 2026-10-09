# 隔离浏览器离线工作台

## Sprint 3B 当前手动同步入口

3314 浏览器节点和 3315 PC 节点共用工作台组件，各自保存独立数据。完成下方正常配对后，两个页面均提供“立即同步”：保存只写本节点；每次点击执行一个有界周期，剩余记录需再次点击，不做常驻自动重试。PC UI 创建的 baseline 经 PC Outbox 发往原 QA Relay，B 原生验签/解密后可编辑并发送后继。待发原操作、转换映射、完整密文、中继收据和具体设备应用回执分别持久。

当前记录状态区区分本机保存、转换封装、中继接收、指定设备应用和当前科研候选/冲突。中继已存储仍可能尚未被另一节点拉取；只有验过目标签名且绑定这次操作的回执才能确认对端应用。再次编辑后不能沿用上次修改的确认状态。页面输入未保存时，拉取保留脏输入；星标命令只保存星标字段。出现失败时保留内容和原消息，下次显式点击使用相同业务身份重试。

本节描述当前实施路径，真实严格 HTTPS 双向业务验收状态以 `docs/sync/SPRINT_3B_REPORT.md` 为准；截至 RH040，已通过的是 Linux 配对/证书/CORS，新增业务往返测试仍待首次执行。Windows 浏览器 HTTPS 未验证；不得安装个人全局 CA 或关闭验证来运行。冲突解决与显式旧3A导入仍待完成，不能作为已交付功能使用。以下 B2/A2 等分节保留历史切点说明。

## Sprint 3B B2b 浏览器加入（网络验收进行中）

普通3314页面的“加入可信 PC 项目”可在空工作区生成本浏览器设备公钥。不要先初始化演示项目；已有演示或旧3A内容不能按名称合并成联网身份。

1. 使用下节 setup/start 命令建立全新空 PC 合成节点，打开3315。
2. B生成公开身份并复制到PC“授权新浏览器设备”，点击“开始设备配对”。
3. 将PC公开输出复制到B；在可信PC屏幕独立核对设备指纹、Owner/Recovery root与SAS，再生成B配对证明。
4. PC确认该证明，将完成回执与签名绑定交回B。B验证完整授权与模块快照，在本浏览器解封项目钥匙，再向原38001入口发送正式签名hello。
5. 只有B显示加入完成后才在PC创建baseline。首次加入要求当前epoch空历史；已有历史明确阻断，不跳游标或重建身份。

网络失败后保留同一配对会话与回执，显式恢复；不得清库或新建密钥规避失败。独立公共绑定预览不会改变授权。此切点没有双向记录同步按钮，完整业务传输仍待C阶段。

Windows本机已验证原生设备身份持久化与界面状态，**Windows严格浏览器TLS尚未验证**。不得为运行以上步骤安装全局CA或关闭证书检查。Linux网络验收使用一次性CI中的两个独立OS用户、各自NSS/profile和原QA Relay；`scripts/browser-network-qa-ci.py`仅允许在该CI环境运行，结果在正式首轮完成前保持NOT VERIFIED。

本机界面定向测试（先普通 `build:sync`，全新attempt）：

```powershell
cd apps/browser-qa
$env:RH_B2_LOCAL_ATTEMPT='unique-local-join-attempt'
node node_modules/@playwright/test/cli.js test --config playwright.join-local.config.ts
```

其中持久绑定显示测试使用显式合成状态注入，只验证UI，不冒充真实加入。网络CI使用普通构建，真实PC UI与B UI交换配对材料，浏览器直接签名和fetch；白名单摘要区分真实证书/CORS与hello中断注入，原始日志、proof、profile不上传。

## Sprint 3B B2a PC owner 配对 API

这是 owner 端配对切点；浏览器加入界面与浏览器 HTTPS 尚未完成，不计完整双端验收。只对全新、空合成项目使用下列准备命令；已加入或已有历史的节点不得再次 bootstrap。

```powershell
$env:HUB_SYNC_QA='1'
$env:HUB_RELAY_QA='1'
$env:PYTHONPATH='apps/api;.'
# 先按既有 QA Relay 文档启动 35433/35434 与严格 HTTPS 38001。
& .venv/Scripts/python.exe -m researchhub.sync.pc_cli setup --node synthetic-pairing --module generic
& .venv/Scripts/python.exe -m researchhub.sync.pc_cli start --node synthetic-pairing --module generic
# 另一终端使用相同环境
& .venv/Scripts/python.exe -m researchhub.sync.pc_cli stop
```

`/api/pairing/start`、`confirm`、`resume` 仅接收 canonical JSON，通过 PC 3315 同源 session/CSRF 边界。状态查询为 `/api/pairing/status?session_id=...`。journal 固定 challenge 与收据；网络结果未知后显式 resume，同一 session 不重新 consume 或发 grant。完成后 `/api/binding` 返回当前完整绑定。非空历史、未知 head 或失效授权会拒绝，不能清库或重置身份来掩盖失败。仅 Python/PC 原 HTTPS 测试已验证，浏览器 UI 将在后续切点接入。

## Sprint 3B B1 正式浏览器密码验证

B1验证正式Envelope、Python双向互通及独立密钥库，不代表真实配对或HTTPS已通过。正式套件仍为AES256GCM/Ed25519/HPKE-X25519-HKDFSHA256-AES256GCM；浏览器自己的non-extractable设备私钥不传给Node或Python。测试授权材料、profile和原始日志仅存ignored runtime。

从仓库根安装 `npm ci --prefix packages/secure-sync`，再进入 `apps/browser-qa`：

```powershell
$env:RH_QA_TEST_ONLY='1'
npm run build:sync
$env:RH_B1_ATTEMPT='unique-b1-attempt'
node node_modules/@playwright/test/cli.js test --config playwright.security.config.ts
# 普通入口验证须使用另一全新attempt；旧目录禁止复用
$env:RH_QA_TEST_ONLY='0'
npm run build:sync
$env:RH_B1_NORMAL='1'
$env:RH_B1_ATTEMPT='unique-normal-attempt'
node node_modules/@playwright/test/cli.js test --config playwright.security.config.ts
Remove-Item Env:RH_QA_TEST_ONLY, Env:RH_B1_NORMAL, Env:RH_B1_ATTEMPT
```

必须先有项目`.venv`及安全测试依赖；可用`RH_QA_PYTHON`指定受控Python解释器。每次测试使用新attempt、独立Chromium profile、retries=0；第一次失败原样保留，不重复同attempt。CI仅上传白名单`summary.json`，不上传oracle材料、原始错误、密钥、proof或profile。业务数据库与vault分开，整个profile一致回滚仍无法检测；本机明文合成记录不因传输E2E而获得磁盘加密。

## Sprint 3B A2b PC 合成节点

PC 固定 `http://127.0.0.1:3315`，独立受控 FastAPI 工厂，不导入产品 main。复用本工作台与 PC storage adapter，所有记录命令经过独立 QA PostgreSQL 35433 的 Domain / Kernel / Outbox 事务。此前 3313 和 3314 入口继续独立。当前 **配对、Relay 网络与 G4 均未完成**。

仓库根 PowerShell：

```powershell
$env:RH_QA_PROFILE='pc'
npm run build --prefix apps/browser-qa
Remove-Item Env:RH_QA_PROFILE
$env:HUB_SYNC_QA='1'
$env:PYTHONPATH='apps/api;.'
& .venv/Scripts/python.exe -m researchhub.sync.pc_cli start
# 另一终端（同样的 HUB_SYNC_QA 与 PYTHONPATH）
& .venv/Scripts/python.exe -m researchhub.sync.pc_cli stop
```

默认启动创建空 Generic 合成项目；首次可使用 `start --module hdsp` 或 `start --module ice-sonocuring` 冻结另一真实模块。既有节点不允许换模块，不能重新分配项目/对象身份。启动遇到占用端口或 owner 文件即失败；停止仅携带本工具保存的随机 owner token，绝不按端口/PID终止未知服务。异常残留时先核实 owner PID 与 3315 都已退出，保留残留文件作为证据，再恢复；不要删除项目或密钥文件。

为验证其他模块的空合成节点，可运行 `start --node qa-hdsp --module hdsp`。节点只在 `storage/runtime/browser-sync-qa/pc/nodes/<slug>`；slug 只允许小写字母起始的字母数字/连字符，最多48字符，拒绝绝对路径、traversal与Windows保留名。默认节点路径保持 `pc/node`，任何时刻仍只有一个3315 owned服务；stop无需知道node名称。此选项不接受个人目录。

PC 根页面自动选择实际冻结项目；高级语境依据 snapshot 的 context_fields/run_forms，保留不适用旧字段并要求用户显式处理，不静默删除。服务重启使会话失效时，原页保留脏输入及 prepared command 身份，明确提示再次保存；第二次操作重新建立会话，不自动重放业务请求。

私有运行目录 `storage/runtime/browser-sync-qa/pc/` 不进入 Git。owner/recovery 是独立 `TestOnlyFileDeviceKeyStore`，**UNPROTECTED QA ONLY**，不是系统受保护密钥存储。项目 key 仅在内存中生成/从已签名 HPKE self-grant 解封；持久化的是签名公共链及密文 grant。重启复核完整 pin、历史 grant 对应 manifest、当前 owner 与同一 key epoch。设备/信任/nonce 账本缺失阻断，不重置发送状态。

界面创建、编辑 Run/Note；星标单独三字段 PATCH，未保存正文仍保留。下方“刷新可信状态”分列工作副本、accepted projection、冲突候选和不可变历史，不从旧 Domain 行推断无冲突。所有本地 command 均保留待发送状态；`RecordWork.pending` 只代表尚未完成后续受控发送交接，不能解释成对端回执或科研批准。本切点没有清除 pending 的传输接口，C 阶段必须用持久发送事件精确清除对应 last_local_tx，不能清除后续编辑。并发候选只读保留，完整解决 UI 后续实现。

公共绑定可在文本框复制，独立 `ResearchHub/PcProjectBinding/v1` domain owner 签名；包含真实冻结 snapshot、canonical hash、JSON-stringify 来源 hash、semantic/opaque ID、principal、roots 和完整公共链。页面在实际浏览器中校验结构与 hash，仍显示须独立确认信任；自行声明的 roots 不会让 B 自动信任。

真实 PC UI 测试（先 PC build；retries=0、独立 Chromium profile）：

```powershell
cd apps/browser-qa
$env:RH_PC_ATTEMPT='unique-attempt-name'
npx playwright test --config playwright.pc.config.ts
```

后端用 `.venv/Scripts/python.exe -m pytest tests/sync_pg/test_pc_records.py tests/sync_pg/test_pc_identity.py tests/sync_pg/test_pc_api.py tests/sync_pg/test_pc_cli.py`；必须显式 `HUB_SYNC_QA=1`。所有 attempt 保留在 runtime，失败不删除。浏览器 attempt-013 曾在截图后停止阶段超时并出现 Windows connection-reset；后续带阶段日志的 attempt-017 通过，不能据此断言原间歇失败根因已解决。

## 原 Sprint 3A 离线入口

固定 origin：`http://127.0.0.1:3313`。只在此地址启动；不要用 localhost。服务启动遇到端口占用会失败，不终止原监听者。全部构建、浏览器二进制、profile、截图与日志存于 ignored `storage/runtime/browser-local-qa/`，不得上传 profile。

从仓库根运行：

```powershell
npm ci --prefix apps/web
npm ci --prefix apps/browser-qa
npm run install:browser --prefix apps/browser-qa
npm run build --prefix apps/browser-qa
npm start --prefix apps/browser-qa
```

另一终端打开专用 Chromium：`npm run browser --prefix apps/browser-qa`。手动 profile 固定为 `storage/runtime/browser-local-qa/profiles/manual/`。首次点击“初始化离线资源”，等待“离线资源已就绪”，再运行 `npm run stop --prefix apps/browser-qa`。`npm run browser:stop --prefix apps/browser-qa` 关闭该工具启动的浏览器，再运行 browser 命令即可在服务停止时离线重开。停止CLI只使用QA运行目录的随机owner token，不按端口杀进程、不访问个人profile。

测试：`npm test --prefix apps/browser-qa`；类型检查：`npm run typecheck --prefix apps/browser-qa`。测试要求先build，自动在固定3313启动/停止自己的静态服务。workers=1，retries=0。每次测试使用独立profile，重开阶段复用该profile。CDP取得当前浏览器进程ID；context.close后用OS进程存在性检查确认全部退出，再启动新的persistent context。此证明不是操作系统断电或浏览器崩溃恢复证明。测试截图390px只是移动视口。

可支持路由：`/`、`/diagnostics`、`/projects/{generic|hdsp|ice}` 及其 `/runs/{id}`、`/notes/{id}`（id为字母数字或连字符）。SW只缓存枚举HTML/JS/CSS/icon，拒绝其他origin，不缓存API；不删除未知缓存、不skipWaiting强刷页面。旧版本缓存暂保留，后续升级策略另行设计。

本地演示：点击“初始化合成工作区”（仅空空间可用），选择 Generic / HDSP / ICE 项目；新建 Run，填写标题、模块类型和可选目标后保存。详情可写观察、设运行状态/科研结果、点星标，再保存；Note 可新建和编辑。停止静态服务后这些操作仍在本地执行。同一profile关闭重开，记录、星标、待处理操作及历史保留。另一标签页提交同一记录后，旧版本保存会提示比较或另存草稿，不静默覆盖。保存失败时保留输入。

工作区及操作记录是明文合成 QA 数据。待处理操作始终未接入传输；本地版本不是服务器 revision，星标和 Note.body 等仍需 wire adapter。不要把这里的队列作为 SecureEnvelope 发送，也不要用个人科研数据测试。

救援演示：展开“诊断与合成草稿救援”，导出明文包；当前未保存输入会作为独立草稿保留。用另一个全新、专用 QA profile 在线加载应用（不要初始化项目），选择该文件，先看预览，再确认恢复。程序创建新 QA 身份，保留旧事件来源；重复同包不增加记录，同 ID 异内容或非空工作区拒绝覆盖。恢复出的未保存草稿需单独打开为新草稿并保存。密钥、nonce账本、Cookie和设备信任均不在救援包中。

诊断显示实际持久存储申请与用量估计；申请获准仍不是永不丢失保证。TEST ONLY 区域可模拟配额、持久化拒绝和无网络adapter失败，或请求真实IDB版本升级；升级阻塞时关闭持有旧连接的QA标签页再继续。不会自动删库或清空pending。配额模拟不是真实磁盘满，adapter失败不是TLS测试。

密钥能力演示：展开 TEST ONLY 密钥与 nonce 区域，显式创建随机 QA identity 并验证 AES-GCM 加解密。该 key 保存在独立实验数据库，**不会加密当前业务草稿**，也不能用于 Relay。完整固定wire向量与多标签/进程重开/耗号/损坏拒绝由 `npm test` 执行。探针通过不证明生产vault、完整HPKE、断电、驱逐、同源攻击或一致回滚防护；网络使用保持 BLOCKED。

组合接口：`src/main.tsx` 的 `QaShell({children})` 包含 `Workbench`；`Workbench.extension({snapshot,draft,dirty,refresh})` 用于本地诊断/救援扩展。`localCommands.snapshot()` 以同一只读事务返回一致快照。共享纯展示组件 `apps/web/src/components/presentational.tsx` 与纯翻译表可在浏览器导入；旧 `ui.tsx` 兼容reexport但仍包含服务端API调用，QA不得导入它。前端bundle由esbuild platform=browser及输入图禁止API/auth/Next依赖。所有Node imports只存在build/test/CLI工具中，不作为浏览器业务计算。

专用浏览器异常退出恢复：若 `browser-owner.json` 残留，先使用该文件记录的PID在任务管理器/`Get-Process -Id <pid>`核查控制进程，并检查是否仍有命令行指向 `storage/runtime/browser-local-qa/profiles/manual` 的Chromium进程。只要任一进程仍在，或无法确定归属，就不要删除owner文件，不要启动第二个浏览器；正常关闭该QA浏览器/控制进程后再检查。仅在确认控制进程和该专用profile浏览器均已退出后，删除 `storage/runtime/browser-local-qa/browser-owner.json` 再运行browser命令。保留profile内容，不删除个人浏览器锁、不终止未知进程。CLI默认拒绝残留owner，防止误入仍在使用的profile。

## Sprint 3B A2a 独立工作区与协议适配切点

本节记录 A2a 历史切点。3A 原有命令、3313、业务 IDB 和离线测试保持默认。3B 复用 `QaShell` / `Workbench`，由 `WorkbenchAdapter` 注入存储和命令；该阶段尚未提供 PC 服务，当前 A2b PC 3315 的使用见本文开头。

```powershell
cd H:\ResearchHub\apps\browser-qa
npm run build:sync
npm run start:sync       # 独立终端，http://127.0.0.1:3314
npm run browser:sync     # 独立终端，专用人工 QA profile
npm run browser:sync:stop
npm run stop:sync
```

专用数据：`storage/runtime/browser-sync-qa/`；业务 IDB `researchhub-browser-sync-qa-business-v1`；仅共享已安装 Chromium 可执行文件，不共享 profile/身份。启动不接管已有端口。静态页面明确“受控同步实验版 · 仅合成数据”。本地合成数据仍是明文。

正常 UI 仅能初始化未授权的合成项目、编辑和查看公共绑定预览。预览验证内容 hash、版本、ID 和 principal 映射，**始终是 UNVERIFIED 或 BLOCKED**；所提供 roots/chain 不是独立 pin，不建立信任。同名不同 UUID 不合并。owner 签名、独立 pin、真实配对、非空历史 bootstrap、PC 服务、密钥/nonce、Relay 传输、接收/冲突和3A救援导入均 **NOT IMPLEMENTED**。不能据此声称已加入或 G1/G2/G4 完成。

- `src/sync/binding.ts`：`PublicProjectBinding` 精确版本化结构，选中 principal 与完整 `principal_map`、owner/recovery roots、epoch/head/完整公共链位置。仅支持本轮 module schema 0.2.1。
- `src/sync/wire.ts`：使用 `packages/sync-protocol/src/browser.ts` 的标准浏览器 canonical/revision/digest；业务库 meta 中稳定 `mapping:<operationID>` 存 tx/change/audit/message IDs、`prepare_id=operationID`、token、绑定 generation/fingerprint、parents/dependencies、revision/digest、envelope 占位和独立传输/对端/科研状态。原 operation/audit 不改写。WebCrypto 在写事务外；提交 CAS 检查 token/绑定/本地 head/收到的 baseline。中断重入保留业务身份；已转换内容不重建。
- 3B 保存同时写 `operation-base:<operationID>`，快照捕获收到的 baseline。`local-wire-heads:<objectID>` 仅代表本地转换链；`received-heads:<objectID>` 留给未来接收服务。保存后收到 baseline 变化会 BLOCKED，不能把旧正文静默接到新远端 head。当前没有实际接收实现，不能凭此声明冲突已解决。
- 星标是独立命令：先读持久对象，再 CAS 保存星标字段。原子写对象/operation/audit/base；不提交/丢弃脏正文，不覆盖其他 tab 的较新正文。正式 highlight payload 仅三项星标字段；普通整表 save 使用 update。
- context 严格依据实际 snapshot 的 context_fields、run_forms 的 allowed 字段和 running/completed 必填规则，并匹配 Python workflow 的大小限制；当前只支持 string 类型。没有额外旧字段白名单：旧3A的 `generic.context`、`ice-sonocuring.experiment_conditions` 或不适用于所选 run_type 的字段会逐字段 BLOCKED，保留本地内容，不删字段或修改 snapshot/hash。`repository/config` 只在对应 run_forms 允许时转换。Note.body 映射 content，不修剪 Unicode/空白；Run scientific_outcome unknown 原样保留。
- 未来接收服务必须将 baseline/revisions/cursor 与对象工作副本、pending、dirty 编辑分开；`ReceivedBaseline` 仅契约，接收尚未实现。安全库必须独立，业务 IDB 不存密钥或 nonce。

显式测试构建（不是真实授权；页面标明 TEST ONLY，普通构建不包含注入接口）：

```powershell
$env:RH_QA_TEST_ONLY='1'
npm run build:sync
$env:RH_A2_ATTEMPT='unique-attempt-name'
npm run test:sync
Remove-Item Env:RH_QA_TEST_ONLY
npm run build:sync       # 恢复无 fixture 的普通入口
```

每次新 attempt 保存到 `storage/runtime/browser-sync-qa/a2/<attempt>/`，`retries=0`。基础验证覆盖实际 Chromium 156 的离线星标/多 tab CAS/Unicode/稳定身份/连续父链/准备中断/真实 IDB abort/并发 token/正常全进程关闭重开；binding 单元测试是 Node 结构测试，不能冒充配对或浏览器网络证明。截图为合成数据，移动 viewport 不等于实体手机。原3A测试仍用 `npm test`。

## B2 Linux 网络 QA 的账户目录隔离

`playwright.network.config.ts` 使用外部已启动的隔离服务。CI harness 为可信与不可信证书测试分别建立临时 OS 用户，经 `sudo --login --user` 运行；不修改 `HOME` 或全局环境。

RH036 的实际诊断发现：登录后继承的 `XDG_CONFIG_HOME` 指向该 QA 用户 home 外且访问被拒绝，随后 Chromium 的 Crashpad 缺少数据库目录并以 SIGTRAP 退出。这是浏览器子进程环境隔离问题，不是 TLS 验证通过或 TLS_001 已关闭的证据。

Harness 保留 `crashpadPathProbes` 的清理前观察，再仅对 QA 浏览器子进程用固定 `env -u` 名单移除 `CHROME_CONFIG_HOME`、`XDG_CONFIG_HOME`、`XDG_CACHE_HOME`、`XDG_DATA_HOME`、`XDG_STATE_HOME`，使目录选择回退到该 OS 用户真实 home，包括现代 NSS 默认 data 位置。`crashpadCleanPathProbes` 必须确认 HOME_FALLBACK、真实 home 内、可写以及临时目录创建后清理成功；浏览器使用同一清理后的环境。任一检查失败即保留首败并停止，不重试同一 attempt。

路径探针不输出环境值或路径、不写 home 外目录、不创建默认配置/Crash Reports 目录；只有 home 内最近实际父目录中的唯一空临时探针目录会被创建并删除。Crashpad、证书校验和网络断言均保持启用。每次修补后的完整浏览器结果仍须由新 SHA 的首次 Linux CI 验证。
