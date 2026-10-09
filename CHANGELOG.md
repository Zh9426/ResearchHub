# 迭代日志

每次提交均需更新本文件，按最新迭代在前记录。日期采用 Asia/Shanghai。

## RH-039 — 2026-10-09 — 浏览器记录内核与独立PG差异验证

### 完成内容

- 新增无IO的Run/Note v2记录内核与窄QA接收策略，保留原Kernel、v1向量和权限规则。
- 同BASE分叉保留候选，晚冲突撤回整批及依赖后继的可信投影；解决提案仍为候选，重复回显保持幂等。
- 固定合成事务分别通过实际Chromium和真实QA PostgreSQL，逐步比较完整状态；独立profile/构建，不覆盖工作台。
- RH038首次CI七job通过，实际Linux配对、严格TLS/Fetch/CORS证据及脱敏页面归档。

### 验证结果

- 本机最终24场景完整浏览器/PG快照一致，3组历史DAG共同BASE对照通过；状态固定项目和模块。
- 协议59项、新增PG1项、类型检查通过；保留最初失败及各定向修补记录。
- 两个runner阶段超时故障明确FAIL且实际浏览器清理通过；子进程helper两项通过，未改业务网络超时。
- C1只验证纯staged snapshot，不冒充IDB原子提交或双向网络；新提交首次CI待执行。

### 后续工作

- C2接入实际IDB接收、稳定离线父链、手动同步、签名设备回执、冲突界面和完整失败验收。
- TLS-001/PC013仍OPEN，整体INCOMPLETE，不进入3C、main或生产。

## RH-038 — 2026-10-09 — 修复配对界面的规范请求编码

### 完成内容

- 实际隔离浏览器复现配对start返回422；只将三个配对POST改用共享canonical编码，保留后端严格校验。
- 增加独立owner界面回归，保留新节点/profile的原失败和修补后证据。
- 归档RH037首次CI：启动隔离修复已实际验证，网络仍在OWNER_START失败，没有覆盖或重跑原失败。

### 验证结果

- 本机实际Chromium配对1项通过，start/confirm均200，B原生密码证明；类型检查与普通PC构建通过。
- 清理异常4项、owned启动4项通过并纳入CI；就绪前失败仍回收本次子进程，异常不吞掉。
- Windows浏览器Relay Fetch未验证，新提交Linux完整安全接入待首次CI；TLS-001与PC013仍OPEN。

### 后续工作

- 完成B2实际网络验收后继续C双向传输、冲突、回执与失败验收；整体INCOMPLETE，不进入3C或生产。

## RH-037 — 2026-10-09 — 隔离浏览器继承的配置目录环境

### 完成内容

- RH036首次CI实际观察到继承XDG_CONFIG_HOME指向新QA账户home外且EACCES，Chromium随后Crashpad缺数据库参数并SIGTRAP；原证据保留。
- 针对该目录隔离缺口，只清理QA浏览器子进程继承的CHROME/XDG目录覆盖，使用账户真实home默认目录，保留清理前后固定字段诊断。
- 不改HOME、全局环境/ACL、浏览器启动安全参数或TLS；不能把环境修补当作原TLS-001根因修复。

### 验证结果

- Python环境/诊断回归7项、Node目录探针5项通过，保留RED→GREEN；新提交首次Linux Chromium网络验收前保持INCOMPLETE。

### 后续工作

- 完成B2真实安全接入后继续C双向业务、冲突、回执与失败验收；TLS-001/PC013保持OPEN，不进入3C或生产。

## RH-036 — 2026-10-09 — 定向诊断 Crashpad 默认目录选择

### 完成内容

- 根据 Chromium 官方目录选择源码，增加同一隔离OS账户下的启动前探针，仅输出配置来源、实际home内外、访问与临时目录创建/清理状态。
- 不输出路径或环境原文；home外只读，home内仅使用唯一空临时目录，不覆盖环境、不创建默认Crash Reports目录、不改变浏览器flags/TLS。
- 保留RH035首次失败与SIGTRAP证据，区分已通过的账户清理和未修复的浏览器启动；记录标准Git连接失败后以相同对象/提交SHA完成API同步。

### 验证结果

- 定向探针与白名单过滤测试保留RED→GREEN，实际Linux目录选择仍待新提交首次CI；不将源码推断或Node文件系统探针当作Chromium网络验收。

### 后续工作

- 根据实际目录诊断定位Crashpad初始化失败，完成B2后继续C。TLS-001/PC013仍OPEN，整体INCOMPLETE，不进入3C或生产。

## RH-035 — 2026-10-09 — 清理隔离账户会话并采集浏览器退出诊断

### 完成内容

- RH034首次CI将失败收窄到BROWSER_LAUNCH/BROWSER_CLOSED，尚未进入TLS；保留完整失败归档及摘要，具体关闭原因仍UNKNOWN。
- 明确释放本次新建UID的systemd登录会话并要求进程归零；未知或浏览器残留仍记FAIL。增加实际HOME与OS账户home一致性检查，不重写HOME。
- 启动错误仅提取有界退出码/信号、经官方源码核对的固定分类，不上传原日志、参数或环境，不改变启动flags或证书验证。

### 验证结果

- 进程分类及竞态4项、启动退出诊断3项纯测试通过，保留RED→GREEN；浏览器类型检查通过。实际Linux清理与网络尚待新提交首次CI。
- RH034首次CI六个既有job通过、新网络job失败；原TLS固定20轮通过不抵消此次失败。

### 后续工作

- 依据新诊断定位启动关闭原因，完成B2后再进入C；整体INCOMPLETE，TLS-001与PC013仍OPEN，不进入3C或生产。

## RH-034 — 2026-10-09 — 保留浏览器网络首败并细化启动诊断

### 完成内容

- 归档 RH033 首次 CI 37907069953 attempt1 的失败日志、网络和 TLS 证据及 SHA-256；明确网络验收未完成，不以其余六个 job 成功覆盖失败。
- 增加浏览器启动阶段和安全错误分类/hash，以及本次新建 QA 账户的进程类别/父进程/状态快照；不输出命令参数、错误原文、凭据或科研内容。
- 保留启动失败和残留进程的失败判定，不改变证书验证、原 TLS 固定用例、业务实现或重试次数。

### 验证结果

- 独立 Windows Chromium 156.0.8078.4 无网络探针确认 persistent context 的 browser() 有效、worker索引字符串0为真；仅排除这两个假设，不证明 Linux 网络通过。
- 新进程白名单分类单元测试 2 项、错误摘要纯测试 2 项通过，后者保留 RED→GREEN；浏览器包类型检查通过。证据分别在 `b2-local/harness-diagnostics-20261009-01` 与 `launch-diagnostics-{red,green,final}-20261009-01`；均不计 Linux 网络验收。

### 后续工作

- 用新提交的首次 Linux CI 定位原启动失败；B2 网络 Gate 保持 FAIL / INCOMPLETE，随后才进入 C 双向业务同步。TLS-001、PC013 仍 OPEN；不发布生产或进入3C。

## RH-033 — 2026-10-09 — 接入浏览器配对与隔离网络验收入口

### 完成内容

- 复用B/PC工作台加入公钥、信任根/SAS独立核对、配对证明和完成回执界面；浏览器验证完整授权与模块内容，先持久密钥授权，再以正式hello确认空基线后建立业务绑定。
- 新增原生浏览器请求签名与有界Fetch，Relay只允许3314的窄CORS，保持原证书、身份和权限校验。
- 新增一次性Linux OS用户/NSS/profile网络验收，公开CA与服务私钥分离，只上传阶段、退出状态、日志hash与合成遮罩截图。

### 验证结果

- 本机CORS单元3项、secure-sync Node规则56项、类型检查与普通构建通过；最终真实Chromium本地UI2项通过，其中绑定显示为明确的合成状态注入，不是真加入。
- 保留绑定显示RED→GREEN及各独立attempt。早期UI固定输出目录可能覆盖部分Playwright产物，控制台错误仍在执行记录；后续拒绝复用目录，不补造首败文件。
- RH032精确首次CI六job成功，原TLS20轮/3A17项/B1密码10项归档。本迭代Linux浏览器严格TLS和实际Fetch尚待首次CI，不计运行通过。

### 后续工作

- 完成B2真实网络验收后继续C双向记录、冲突、回执、失败矩阵与3A显式导入。TLS-001和PC013仍OPEN，Windows浏览器TLS未验证；不进入3C或生产。

## RH-032 — 2026-10-09 — 持久化 PC owner 配对与中断恢复

### 完成内容

- PC 配对 journal 固定 challenge、接收者、授权前后 head 与 receipt，复用原 SQLite consume 和 Relay membership 路径；未知 ACK 查询原候选，不重复授权。
- 动态公共绑定保留完整 principal 映射与 canonical snapshot；完成态仍验证当前授权，空项目加入与业务写入互斥，未知 head 阻断。
- 提供受限 setup CLI 与 session/CSRF 配对 API；同步构造、数据库、HTTPS 和关闭整体进入线程池，已知环境缺失返回明确错误。

### 验证结果

- P2 修补前完整协议/内核/PG/安全集合 403 项通过；修补后五个完整 PC 文件 43 项通过、独立原入口严格 HTTPS 配对 1 项通过，均 exit 0、无 skipped。
- 保留 RED11 的事件循环阻塞与配置异常证据；中间测试 Windows 时钟同 tick 误判改为事件顺序断言，失败记录不覆盖。Docker 中断的未完成运行不计通过。
- RH031 精确首次 CI 六 job 成功，浏览器密码 10 项、原3A 17项及 TLS 固定20轮归档；本提交 CI 待推送核验。

### 后续工作

- 浏览器真实加入 UI、严格 TLS/CORS、双向传输与冲突失败验收仍待完成。TLS-001 与 PC013 保持 OPEN，Sprint3B 仍 INCOMPLETE，不进入3C或生产。

## RH-031 — 2026-10-09 — 浏览器正式密码与不可变密文持久化

### 完成内容

- 抽取共享Envelope/membership/checkpoint规则，保留Node兼容入口；真实浏览器WebCrypto与固定HPKE库处理正式v1/v2，原向量和套件不变。
- 独立non-extractable密钥IDB、授权永久标记、原子nonce预约/高水位检查、准备token与sealed摘要镜像；实际Run/Note/星标映射经过可恢复跨库密封，不允许已sealed内容重新加密。
- 损坏或身份不一致保留业务和密文并BLOCKED；普通构建排除TESTONLY授权/故障入口；CI新增真实Chromium密码job，仅上传白名单summary。

### 验证结果

- 最终真实Chromium密码/互通/持久化负例10/10通过，无skip、retries=0；普通构建1/1、原A2工作区5/5、Node安全54/54、Python原安全182/182；两包typecheck/diff检查通过。
- 010 sealed丢失、011局部counter回滚均先保留实际RED再最小补丁；不能以最终通过覆盖首败或宣称识别整个profile一致回滚。
- 原v1与TLS调查文件hash未变；RH030首次CI五job全部成功，原3A17项与TLS固定20轮归档。B1精确提交CI将在推送后核验。

### 后续工作

- B2真实owner加入、严格HTTPS/CORS；C双向传输、冲突、失败验收与3A显式导入。TLS-001和PC013保持OPEN；Sprint3B仍INCOMPLETE，不进入3C或生产。

## RH-030 — 2026-10-09 — 建立独立 PC QA 业务节点与可操作界面

### 完成内容

- 新增3315受限PC入口，复用工作台；Run/Note/星标经独立QA PG的Domain、Kernel、Outbox原子写入，稳定命令重试、工作版本与heads双CAS。
- 读取分列工作副本、可信投影、候选与历史；owner/recovery/self-grant/nonce持久化，丢失关键状态停写，公开绑定只预览不自授权。
- 精确loopback Host/Origin、会话/CSRF、owned启动停止；受限合成node slug供三模块隔离验证，产品API与生产配置不接入。
- 复审修复会话重启后保留脏输入并显式重试、模块语境字段错配、保存后刷新竞态；保留失败证据与确定性退出竞态回归。

### 验证结果

- PC与Domain/Outbox真实QA PG最终34项通过、0 skipped；最终完整PC套件6项通过（3模块实际UI、重启恢复、Run/Note/dirty-star、确定性退出竞态），retries=0。
- 产品后端108项、原3A浏览器17项、3B工作区5项通过；typecheck/build及两阶段独立复审PASS。
- PC attempt013退出超时与Windows连接重置仍OPEN，后续成功不关闭；TLS-001原失败、固定用例和调查保持。
- RH029精确首次CI37877406718五job成功，原TLS/3A证据归档；本迭代网络与真实配对尚未实现，不计G2/G4通过。

### 后续工作

- B浏览器正式密码/vault/加入与严格TLS，C双向传输/冲突/失败验收、3A显式导入；Sprint3B仍INCOMPLETE，不进入3C或生产。

## RH-029 — 2026-10-09 — 建立独立同步工作区与稳定操作转换

### 完成内容

- 新增3314隔离profile/IDB/构建，复用原工作台adapter，保留3313；专门星标命令CAS、脏正文隔离与原子operation/audit/base。
- 公共项目绑定仅严格预览、不自授权；v2操作稳定身份/父链/prepare token/修订映射；hash事务外、提交CAS，收到新基线后旧操作明确阻塞。
- 星标wire仅三字段，冻结模块规则与Python对齐，旧未知字段和对象/项目错配明确BLOCKED，原内容保留。
- 补实际截图与进行中报告、安全跨库恢复及DAG边界设计；完整Sprint3B仍INCOMPLETE。

### 验证结果

- 最终专项4项PASS（2 Node规则、2真实Chromium），11.02s；无fixture普通入口1项与星标夹带字段原子拒绝定向1项PASS；typecheck/build通过。
- Windows Chromium156.0.8078.4，正常全进程关闭重开/离线/CAS/IDB abort；原3A最终17项51.6s通过。Python模块规则7场景纯函数对照通过。
- 独立规格与质量审查发现nil UUID、null principal、冻结模块绕过问题，均最小修复并复审PASS；保留原失败与每个attempt。
- RH028精确首次CI37875621054五job全部成功，TLS20轮与旧3A17项证据归档；TLS001仍OPEN。

### 后续工作

- A2b PC业务服务/受控读取，B真实配对/浏览器安全，C双向传输与冲突失败验收；3A导入待实现，不进入3C或生产。

## RH-028 — 2026-10-09 — 建立 Sprint3B 显式 Run/Note v2 契约

### 完成内容

- 新增 (2,2) Run/Note 版本分派及 Run 三项星标精确类型；原 v1 白名单、固定向量与 revision 保持不变。
- Python/TS、Kernel 物化与公共 Envelope/Relay 能力一致；内外版本受签名/AAD 保护且严格绑定，密码套件不变。
- 新增独立 v2 固定向量与负例、ADR-029、Sprint3B 设计增量和连续实施计划。

### 验证结果

- Python sync_vectors + secure_sync 221 项通过；追加负例后 v2 定向 28 项、临时目录修正后安全 8 项通过。
- Node 原协议与初始 v2 共 26 项、扩展 v2 定向 25 项、安全 51 项及两包 typecheck 通过。
- 真实隔离 PostgreSQL 内核/Domain/Outbox 回归 132 项通过（23.88s）；冻结 v1/secure-v1 八文件与 TLS 调查记录 hash 不变。
- 初次 QA Relay 初始化因 Anaconda 缺 psycopg 失败；保留证据，项目 .venv 单次受 guard 连接与启动通过，未改变源码或证书校验。
- 独立规格与质量审查通过；本阶段未验证实际浏览器加密或双向网络同步，TLS-001 仍 OPEN。

### 后续工作

- 继续 A2 同项目工作区/因果适配、B 浏览器安全接入、C 双向与故障验收；不进入3C、不发布生产。

## RH-027 — 2026-10-09 — 归档 Sprint3A 最终验收并停止迭代

### 完成内容

- 完成SPRINT_3A_REPORT的A–L场景、G1–G6、七类状态、截图/测试/CI证据与未覆盖边界。
- 记录最终规格、质量及全实现复审结果，实施计划全部完成；保留当前分支与稳定标签，不进入Sprint3B。

### 验证结果

- 精确实现8e6200d首次CI37871775036五job全部success；Linux Chromium17项通过35.03s，0失败/跳过/重试，构建hash与Windows17项50.6s一致。
- TLS20轮诊断与浏览器白名单artifact下载校验；原始TLS失败三份证据、冻结fixtures/调查记录hash不变，TLS001 OPEN。
- 此次仅文档归档，未重复本机全套测试；本提交CI随正常推送触发，不关闭既有风险。

### 后续工作

- Sprint3A已停止。正式wire迁移、浏览器授权/恢复及完整跨设备同步仅为候选，需后续明确启动；生产和网络使用仍BLOCKED。

## RH-026 — 2026-10-09 — 完成浏览器离线工作台验收与 CI 证据

### 完成内容

- 补齐缓存封装 identity/action/AAD/digest 独立错绑定负例；拒绝后不重复加密或耗号，恢复原缓存仍可 exact retry。
- 测试启动与清理统一释放自有资源；真实目标浏览器启动失败会关闭来源浏览器与服务，关闭失败仍尝试释放服务并传播错误。
- 独立 browser-local-qa CI 使用固定依赖和专用 Chromium，仅上传白名单合成截图、JUnit 与脱敏摘要；原 TLS 用例和诊断保留。
- 收紧已就绪面板与小屏换行，交付桌面/移动视口的实际记录、Note 与救援截图。

### 验证结果

- Windows 10.0.22631 x64 / Chromium156.0.8078.4，最终完整17项通过50.6s，retries=0；237原固定wire检查保留。QA typecheck/build通过。
- 清理失败用例先观察RED，再最小修补；原始输出转录与每次完整验收日志/JSON/JUnit独立保留。四类错绑定与真实启动失败定向6项通过。
- RH-025精确提交8a38e9a首次CI四job成功，20轮TLS诊断已归档；TLS-001仍OPEN。
- 实体手机、OS崩溃、断电及全站一致回滚未测试，不扩大为生产安全保证。

### 后续工作

- Task5规格与质量审查通过；核对本提交首次CI及全实现复审，补全最终报告后停止Sprint3A；不进入Sprint3B，不接入真实传输或生产数据。

## RH-025 — 2026-10-09 — 验证浏览器协议与受限密钥 nonce 探针

### 完成内容

- 提取canonical/protocol纯core，保留Node同步API；新增WebCrypto异步browser入口，原wire exact schema及固定向量未改。
- 独立TEST ONLY数据库保存随机non-extractable AES256-GCM CryptoKey；合成authority分配prefix，短事务提交counter/high/pending后才加密。
- 完整QA封装exact retry核验身份/动作/摘要/AAD及认证解密，复用已存密文，不再预约或加密；missing/corrupt/pending/旧ledger/overflow拒绝。
- 明确局部ledger镜像不是外部witness；一致回滚/断电/驱逐/恶意同源/完整HPKE/生产vault未证明，BLOCKED FOR NETWORK USE。

### 验证结果

- 实际Chromium全11 tests PASS /35.6s；追加中断/损坏key两项PASS /4.5s。原固定26/59/3/10场景20step共237检查，含decimal/Unicode/strict rejection/revision与highlight拒绝。
- 双tab、刷新、PID全部退出重开、key解密、nonce不重复、耗号、sameaction并发、完整retry、真实key存在时救援排除及新profile无key clone通过。
- 加密人为挂起后正常关闭所有浏览器进程，重开pending拒绝与counter不退；不是OS crash/断电证明。独立identity/action/AAD错绑定尚未单测，仅代码校验。
- Node protocol7、secure-sync48及typecheck通过；Python sync17+secure174=191通过21.91s。原fixtures/TLS调查hash未变；规格PASS、质量APPROVED。

### 后续工作

- 最后执行完整A–L及截图/浏览器CI/交付报告；整理测试启动失败清理。保持TLS-001 OPEN，不启用真实发送、不进入Sprint3B。

## RH-024 — 2026-10-09 — 增加合成草稿救援与存储失败处理

### 完成内容

- 明文合成救援包包含冻结项目、记录/星标、pending操作、审计及未保存草稿；严格schema/引用/历史/摘要校验，排除身份授权、密钥和nonce状态。
- 文件预览后原子恢复到空工作区，生成新QA身份、保留来源和独立恢复审计；重复幂等、ID内容冲突整包拒绝。
- 持久化申请/估计及拒绝、不支持、配额/升级失败提示；错误保留输入和已有pending，提供草稿导出；无自动删库。
- 明确TEST ONLY拒绝adapter测试失败显示，实际transport始终not_configured，不接TLS或Relay。

### 验证结果

- 原4+新3真实Chromium完整7项通过；adapter补丁后救援3项通过16.6s，非空pending加强用例一次通过10.4s。QA build/typecheck通过。
- 实际下载→独立新profile文件导入、星标/Note/HDSP与ICE高级语境、空标题草稿、新身份/原来源、幂等/冲突及摘要/额外字段拒绝通过。
- 真实IDB恢复写后abort整库仍空；真实跨tab升级阻塞/解除与升级中止可恢复。quota/persist/API不支持/adapter拒绝为模拟，非物理低磁盘或TLS验收。
- RED日志及后续失败截图保留；初期RED只有日志/上下文，无截图，未冒称有。实际桌面/移动视口页面已查看；密钥排除目前仅白名单与dummy，真实key探针留下一步。

### 后续工作

- 完成本轮浏览器协议、CryptoKey/nonce受限探针、完整A–L验收与最终报告；TLS-001 OPEN，不进入Sprint3B或生产网络。

## RH-023 — 2026-10-09 — 实现本地科研记录与原子版本保护

### 完成内容

- 三种 SYNTHETIC 项目仅空库显式初始化；保存冻结模块快照、本地哈希及隔离工作区/设备标识。
- Run/Note 正常页面渐进编辑、观察、独立星标与筛选、高级语境；未知科研结果保持未知。
- 对象、local edit version、LocalOperation 与 LocalAudit 在同一 IndexedDB 短事务提交；持久 CAS 拒绝旧版本，冲突保留输入、可比较或另存。
- 本地保存/未配置传输/review独立；通知或提交后读取失败不否定成功提交。所有操作仍 pending/NEEDS_WIRE_ADAPTER。

### 验证结果

- Chromium156真实浏览器4 tests PASS /12.2s：停服离线创建、进程退出重开完整快照相等、刷新不重灌、双tab不同对象并存/同版本拒绝、写后真实abort全回滚、星标筛选及三模块unknown。
- QA build/typecheck通过；桌面与移动视口截图已实际查看。广播异常和提交后读取错误均保留RED→GREEN证据。
- 首轮重开断言失败已定位为implicit label包含textarea文本；保留诊断并改用语义textbox角色，未修改持久化逻辑以迎合测试。
- RH-022精确提交08aafe4的CI37867406210四job通过，20轮TLS证据已归档；不关闭TLS-001。

### 后续工作

- 本轮继续救援包、存储故障UX、浏览器wire/key/nonce探针及完整验收报告；无实际传输、生产科研数据或Sprint3B。

## RH-022 — 2026-10-09 — 建立隔离浏览器离线应用壳

### 完成内容

- 新增固定 127.0.0.1:3313 的 React 静态 QA 入口、专用 Chromium profile、静态资源 Service Worker 与仅限自身的启动停止工具。
- 提取并复用现有纯展示组件和样式；补充 Sprint3A 短设计、实施顺序、Node/Browser 与星标 wire 边界。
- 离线初始化失败可见并可重试；等待有界、资源缓存完整性确认后才显示就绪。保留未知缓存，不强制刷新页面。

### 验证结果

- 真实 Chromium 156.0.8078.4 / Windows 10.0.22631：2 tests PASS / 5.3s，包含静态服务停止、浏览器进程全部退出、同 profile 离线详情导航/刷新、真实503注入后恢复；retries=0。
- 现有前端46 tests、前端与QA类型检查通过；QA构建与owner-token服务停止通过。桌面/390px移动视口截图已查看，非实体手机验收。
- 原Node协议7项/Python17项基线通过；固定向量与TLS记录哈希已留存。规格PASS、质量补丁复审APPROVED。
- 初始sandbox启动EPERM与构建扫描误判、503 RED均保留，未冒充通过。浏览器启动失败清理为静态复核，尚未独立故障注入。

### 后续工作

- 实现本地模型/原子保存/CAS、Run/Note/星标、救援与浏览器安全探针；本提交仅应用壳，不代表Sprint3A完成。
- TLS-001仍OPEN；不启用真实传输、不进入Sprint3B、不移动main/v0.2.0。

## RH-021 — 2026-10-08 — 保留 TLS 失败证据并补充固定复现与阶段诊断

### 完成内容

- 独立保留 CI 37789245245 attempt 1 的失败日志、原始归档与SHA-256；新增 TLS-001 调查记录，并将最终验收报告更新为稳定性事件 OPEN。
- 原并发首次GET用例保留连接池路径，增加每次新建且验证证书的连接路径；每种固定10轮×4，所有请求必须HTTP200且快照不可变，首个失败直接传播，不加入重试。
- 客户端保存固定阶段事件和运行/调用/用例标识；入口记录固定关闭原因、方向字节数和时长。严格schema导出，CI清理前上传仅这些诊断JSON，保留30天；不保存请求、密钥或异常文本。

### 验证结果

- 修改前原用例固定30次：30 passed /14.26s。初版诊断固定300轮pooled通过，但只有3次新握手，明确不冒充握手压力验证。
- 两种调度各10次×10轮：20 passed /28.28s，实际trace确认400次fresh TCP/TLS握手与400次pooled并发GET通过；尚未复现原失败。
- 诊断边界与失败传播单测13 passed /0.56s，验证失败不进入下一轮且敏感info不写证据；Ruff通过。独立复审APPROVED限于诊断补丁，原事件仍OPEN。
- 最终完整实际Relay56 passed /284.26s、client75 passed /43.83s，两cohort真实隐私扫描0/0 hits，完整runner退出0；stage诊断160条已保存。提交CI另行核对，不能作为原故障已修复的证明。

### 遗留事项

- 原故障已定位到新连接TLS握手阶段，上游具体关闭原因缺少原始观测，根因仍未确定；不能以本次重复通过或CI绿色结案。
- 保持原超时、证书验证和网络/配额限制，不skip或吞错继续；不进入Sprint3，不移动main/v0.2.0。

## RH-020 — 2026-10-08 — 完成 Sprint2 八项安全 Gate 与验收报告

### 完成内容

- 最终30主题报告与A–Z验收映射，更新协议、状态机、威胁边界、故障恢复及测试计划；八项Gate全部PASS，仅限合成loopback QA。
- 记录完整独立安全审查、PENDING配对和Linux权限/故障注入修复、失败CI与成功重跑，明确运行时密钥扫描和各类测试边界。

### 验证结果

- RH019实现提交982c6ef的四job GitHub CI全部success；安全job实际Python174、Node48/typecheck、lifecycle6、Relay55/client75及最终清理通过，无skip/deselection冒充成功。
- 本地审计后Python原型+secure208、Sprint1向量/内核/实际PG149、backend/MCP/release137；Node48与协议7、前端46/typecheck、隔离Docker生产构建通过。
- 完整本地Relay55/client75通过，实际dump/bytea/files/log七编码扫描98,143,940/4,733,490 bytes，0/0 hits，包含14泄漏正对照。最终helper补丁复审后另重跑原型34、真实v0.2服务21、备份恢复1、服务重启持久性1，均通过。
- 最终独立审查及补丁复审APPROVED，无未关闭Critical/Important。文档30主题/相对链接、diff及凭据检查通过；本提交仅文档，提交后的精确远端SHA和CI另行核对。

### 遗留事项

- 按要求STOP并等待人工审查；不启动Sprint3、不合并main、不移动v0.2.0。
- 生产vault、真实user-presence、完整split-view/key transparency、所有可信材料一致回滚防护、全量bootstrap/GC、移动与公网/真实科研同步仍NOT IMPLEMENTED。

## RH-019 — 2026-10-08 — 修复 Linux TLS 初始化权限与故障注入证据

### 完成内容

- 仅离线短命TLS复制helper增加DAC_READ_SEARCH，精确校验CHOWN及该只读cap；保留源只读、key0600及Relay/入口cap-drop ALL。
- 生命周期测试必须实际到达指定故障点并匹配操作错误码；新增更早helper失败不能冒充后续故障的回归，以及Linux foreign-UID 0600 sentinel实测。

### 验证结果

- 实际Linux内核复现CHOWN-only读取0600 foreign-UID文件PermissionError；添加只读DAC能力后成功且直接写入仍拒绝。更早错误假通过的两个回归均有效RED→GREEN。
- 实现者lifecycle6 passed/59.25s、TLS材料2项、真实初始化及HTTPS1 passed/8.61s，终点privacy0；实际服务无额外cap，目标key0600/UID10001。
- 独立安全复核APPROVED，无未关闭Critical/Important：自行执行6项lifecycle/sentinel通过（59.09s）、恢复初始化成功、真实TLS1项通过（8.20s），核验运行服务无额外cap和key0600/UID10001。完整远端LinuxCI需推送后验证，既有失败运行不计通过。

### 遗留事项

- 等待修复后四job CI及最终报告；不扩大生产权限、放松私钥权限或启动Sprint3。

## RH-018 — 2026-10-08 — 初始化全新 CI checkout 的测试目录

### 完成内容

- 在安全CI密码测试之前显式创建被Git忽略的storage/runtime父目录，使pytest能建立指定basetemp。

### 验证结果

- RH017首次Linux安全CI真实失败：14 failed、9 passed、151 errors；首个异常为Path.mkdir(parents=False)遇到缺失父目录的FileNotFoundError，未进入Relay网络测试，不能算通过。
- 已核对实际调用栈，最小修复仅新增mkdir -p；修复后的完整LinuxCI需此次推送后重跑。

### 遗留事项

- 等待新CI完整结果及正在运行的审计后本地回归，再填写最终八Gate与报告。不改变密码或权限规则。

## RH-017 — 2026-10-08 — 完成待配对设备激活并接入安全回归 CI

### 完成内容

- 最终独立审计发现并修复Python/Node的PENDING配对完成缺口：严格匹配已锚定身份、公钥、角色与nonce前缀后激活，保留单次challenge与membership/grant/receipt原子性。
- 两端新增替换/重放/持久提交失败负例，并补实际HTTPS完整配对链、独立grant解包和激活后角色权限验证。
- 新增独立secure-relay-qa CI job，使用临时client PG、运行时随机钥匙、loopback TLS Relay、完整两组测试和always清理；保留原有三job。

### 验证结果

- 两端均先有效复现PREFIX_OR_DEVICE_COLLISION，再取得GREEN；实现者Python安全测试174项、Node48项及类型检查通过；实际HTTPS定向1项通过且终点privacy0命中。
- 最终独立安全复审APPROVED，无未关闭Critical/Important；原Python/Node探针GREEN、配对互操作26项、Node身份替换/原子性10项、真实HTTPS完整链1项及privacy0通过。root Ruff/diff与三份QA服务凭据精确扫描通过。
- 新增Linux CI尚待推送后实际运行。不能以静态工作流解析替代远端执行。

### 遗留事项

- 审计批准后重跑全部Sprint0/1、安全传输、backend/MCP/release、frontend/隔离构建及v0.2实际备份/恢复回归，完成八Gate报告。
- 限于合成loopback QA；生产vault/presence、完整split-view、真实科研同步和移动/公网部署仍未实现。

## RH-016 — 2026-10-08 — 可信客户端原子接收与端到端故障验证

### 完成内容

- 实际固定验证TLS客户端、PG不可变密文outbox与fresh签名proof；严格专用client PG守卫和完整签名会员历史。
- 整页签名/AEAD/chain/semantic预验证，outer receipt/cursor/checkpoint与既有Kernel同事务；跨wrapper幂等、历史隔离、独立HumanGrant和持久receipt ACK。
- 真实客户端提交前/后强制退出、晚Kernel错误全页回滚、实际HTTPS属性调度、100 push/pull及128KiB Artifact测量。
- 两组串行QA保留既定配额，独立隐私证据与collection/JUnit交叉核验，拒绝子集/跳过/过期证据；修复PYTEST_ADDOPTS漏测及httpx重聚合延迟body deadline检查，均有实际RED→GREEN。

### 验证结果

- 独立spec PASS：55+75项、无失败/skip/deselection，privacy0/0；独立quality/security APPROVED：55 passed/264.47s、75 passed/47.68s，无未关闭Critical/Important。
- root独立核对最新完整aggregate/collection/JUnit/privacy：两组扫描98,115,591/4,730,640 bytes，0命中。客户端75项包含明确的单元边界，不能全部称为网络测试。
- root本地依赖220 passed/26.35s、Node38/typecheck通过；最新Ruff/diff及三份QA服务凭据精确扫描通过。运行证据与超时界限见SPRINT_2_TASK3B_QA.md。

### 遗留事项

- Task4最终全系统独立安全审查、其后完整旧版本回归、新增Linux secure-relay CI与八Gate报告尚待完成。
- 仅合成loopback QA；生产vault、真实presence、全量bootstrap/GC、完整split-view/可信状态一致回滚防护未实现。不进入Sprint3，main/v0.2.0保持冻结。

## RH-015 — 2026-10-08 — 隔离 HTTPS Relay 与持久传输回执

### 完成内容

- 独立非 root Relay、固定 TCP 入口与专用 PostgreSQL；实际网络、端口、挂载、权限与资源校验，临时 CA/证书、严格 TLS 验证及部分初始化 journal 清理。
- 严格签名请求绑定当前会员、双 epoch、HTTP 路径/查询/正文与有效期；当前授权先于不可变响应缓存，撤销后旧凭据不能重用回执。
- PostgreSQL 项目锁内原子保存完整密文、连续 sequence/chain、nonce uniqueness、实际容量和原回执，提交后才返回 RELAY_STORED；受限 pairing/recovery、设备签名 ACK/checkpoint 与 opaque chunk 接口。
- 真实请求/容量/缓存/限流上限、TLS 断线与 Relay/PG/入口强制退出恢复；实际 HTTP Hypothesis；session 终点扫描 PG dump、全部 bytea 原值、应用/挂载文件与日志。
- 隐私扫描七种编码与 14 种真实数据库泄漏对照；错误诊断脱敏。保留并如实记录两次 QA 诊断泄漏、凭据失效/新材料重跑及旧扫描假阴性，未保存秘密值。

### 验证结果

- 独立规格复审 PASS：完整网络55项通过（284.64s），原隐私漏检及两项布尔/整数混同均实际 RED→GREEN；自行重放非法 chunk/query 返回400/401且 PG 无副作用。
- 独立 quality/security APPROVED：完整网络55项（288.64s）、部分初始化清理3项、TLS材料2项通过；12项额外未认证配对畸形输入统一401，无未关闭 Critical/Important。
- root 提交前完整网络55项通过（284.98s）；隐私v2扫描98,100,447 bytes、11个bytea列859个值、289项私密库存与七种编码，0命中。本地依赖Python220项（含TLS材料）、Node38项、TypeScript类型通过；20个Python文件Ruff/格式、暂存29文件凭据形状扫描及新旧QA服务密码精确扫描均通过。

### 遗留事项

- 本提交仅 Task3A；Task3B不可变客户端 outbox、整页可信验证与 Kernel/transport 同事务、客户端真实进程故障和网络性能仍待实施。
- Linux secure-relay CI job、最终全系统安全审查/回归、Sprint2报告与八项Gate尚未完成。本地合成测试不等于生产服务验收。
- 不包含生产密钥库、真实科研同步、手机/公网部署、全量bootstrap/GC或Sprint3；main及v0.2.0冻结基线不变。

## RH-014 — 2026-10-08 — 可信设备生命周期与持久安全锚点

### 完成内容

- Python/Node独立实现设备和项目密钥、完整authority-signed membership历史、HPKE grant、单次配对、撤销轮换及高熵Recovery Kit；Relay不持有这些私钥。
- 配对挑战、失败次数、会员变更和原wrapped receipt持久事务；所有权威读取重新验证完整会员链，SQL索引列与signed body逐项交叉核对，损坏历史不计配对尝试或写入。
- Recovery Kit公共journal/head持久加载；manifest/checkpoint/journal/head同事务，真实重启和SQLite COMMIT失败整体回滚，seed-only不能恢复freshness。
- checkpoint双epoch与cursor/chain单调、BOOTSTRAP/SIGNED显式类型、持久公共验证上下文及每次读取真实验签；局部签名/body/context损坏拒绝且不覆写原锚点。
- 小Artifact fresh DEK、AESKW内置加密manifest、64KiB分块及严格顺序/size/hash/tag校验；签名加密snapshot原型，双端独立互操作。

### 验证结果

- 最新实现交接：Python secure162与合并220（各含root未纳入本提交的TLS材料2）；root排除TLS独立合并218通过，Node38及严格类型通过，Ruff/格式/diff通过。
- 真实子进程Kit恢复、SQLite deferred-FK COMMIT失败、配对异常事务、Hypothesis生成grant/epoch/chunk负例通过；没有以替身宣称PG/网络验收。
- 已发现的历史授权、checkpoint双epoch及持久旧签名损坏均有有效行为RED→GREEN；独立spec最终复审PASS，两语言各11类额外损坏探针拒绝且无副作用；quality/security APPROVED，两语言各22个额外负例检查通过，无未关闭Critical/Important。本结论仅限本轮本地合成QA。

### 遗留事项

- 继续Task3真实隔离HTTPS Relay/PG、不可变outbox、客户端与Kernel同事务、故障/隐私验收及最终八Gate；本轮本地库测试不等于网络验收。
- Node CheckpointStore.get与pairing.retryReceipt改为async，仓内调用方全部await；旧无验证信息的QA SQLite格式fail closed，不自动降级或迁移。
- 生产keystore、真实presence、Kit导出UX、完整bootstrap/split-view/GC、移动/公网/Sprint3均未实施。完整可信本地材料一致恶意回滚仍有明确限制。

## RH-013 — 2026-10-08 — Sprint 2 Crypto / Envelope / Nonce

### 完成内容

- Python cryptography50.0.2与Node WebCrypto/@hpke/core1.9.0各自实现AES256GCM、Ed25519、RFC9180 Base HPKE和AESKW；锁common1.10.1，无自研primitive。
- 独立publicwire仅canonical/公共验签；SecureEnvelope全部字段绑定AAD/signature，严格canonicaldecoder与semantictransaction映射/digest/device/deps验证，包裹不改变revision。
- Python/Node共格式SQLite FULL/BEGIN IMMEDIATE与fsync witness预约nonce，提交后才加密，缺失/坏尾部/回滚/溢出fail closed，真实跨进程并发和退出窗口。
- 公开TEST ONLY primitive及完整canonicaltransaction/envelope固定向量，双向独立seal/open/sign/verify/wrap/unwrap；非法decryptedparser错误归一为INVALID_PLAINTEXT。

### 验证结果

- Root及独立规格/质量复审均实际通过：Python39、Node6、严格类型；Root合并Sprint1wire/property59通过，Ruff/diff检查通过，无skip。
- 六个真实Python/Node进程120唯一nonce、重启121/122；四个实际强制退出窗口、九种账本损坏双端拒绝；Hypothesis50 freshkey roundtrip/mutation与30nonce schedules。
- 独立审查P2缺fixedcanonicaltransaction向量已RED→GREEN修复并复审PASS/APPROVED；parser numeric secret token泄漏也行为RED→GREEN修复。
- 100×1KiB本地均值seal8.566ms/open1.007ms/verify0.636ms，含nonce fsync，非网络性能。本机default sandbox临时文件权限失败不作为功能失败，实际escalated合成QA重跑通过。

### 遗留事项

- 本提交仅Task1；生命周期、配对/撤销/恢复、真实HTTPS Relay、immutable network outbox、网络故障/隐私及完整八gate待后续迭代。
- 无生产keystore、真实用户presence/科研传输、产品migration、移动/公网/Sprint3。所有随机运行时key仅内存/忽略QA文件，Git固定key是明确公开TEST ONLY例外。

## RH-012 — 2026-10-07 — Sprint 2 安全设计与密码库 gate

### 完成内容

- 保存Secure Relay完整72节需求、实施计划、安全设计增量、标准密码库官方调查与SecureEnvelope契约；新增ADR016–025，不修改Sprint1 canonical identity和科研权限规则。
- 独立设计审查修订membership旧状态授权/CAS、recovery可信anchor、旧epoch历史隔离、client cursor/Kernel原子提交、nonce witness严格恢复与pairing持久幂等；明确recovery唯一authority例外。
- npm实际查询core1.9.0/MIT/common^1.10.0，选cryptography50.0.2/WebCrypto/HPKE标准组合；无自研primitive，不把HPKE Base称sender认证。

### 验证结果

- 独立安全设计最终PASS；这是设计审查，不是密码/网络验收。
- 本轮开始前Sprint1 HEAD334e6c0与远端/CI success核对一致；main/v0.2.0保持4a4db4a。
- 实际Relay专用QA PostgreSQL17.11/loopback35434已启动并核对DB/role；其启动脚本待后续Relay迭代提交。
- crypto/interop/nonce/TLS/fault本提交尚未验收，正在实现，八项最终gate均未声明PASS。

### 遗留事项

- 完成双语言crypto、设备生命周期、真实HTTPS Relay、故障/隐私/property验收及独立实现安全审查。
- 本提交只包含设计文档；完整Sprint2尚未完成。无生产migration、真实科研传输或Sprint3。

## RH-011 — 2026-10-07 — Sprint 1 QA Sync Protocol Kernel

### 完成内容

- 不可变 PostgreSQL revision DAG、transaction/member/dependency、N-head conflict、整批科学屏障与独立 accepted projection；晚到冲突撤回原批及递归依赖，完整人工重审产生新来源。
- 注册 principal 与精确一次性五分钟 grant，复用既有 Human/AI Domain authority；current heads 保护、离线 proposal/在线 resolution 分离、lifecycle 和冻结 module/schema 隔离。
- 真实现有 Domain service 同 Session 组合 Run+6 Parameter+3 Metric+2 pending Artifact、Audit、Inbox/Outbox/cursor；action_digest 防同 ID 换动作，保留科学数字字符串，不迁移个人数据。
- 六点故障注入、真实两连接并发/锁等待、Hypothesis 属性、10 个跨语言固定 Kernel 场景、独立 QA CLI 与 PostgreSQL CI job；完整23主题报告及协议/状态/模型/ADR更新。

### 验证结果

- 实际 PostgreSQL 最终 Python149（17 vectors、7 pure/kernel boundary、125 PG）全部通过且无skip；TS7、严格类型、Ruff及diff检查通过。Hypothesis300编码+53数据库属性案例通过。
- v0.2 后端/MCP/Release137、前端46及typecheck通过；独立Compose真实23项通过，包含MCP/权限并发、PG/MinIO备份恢复和四服务重启持久性；API/Web Docker构建通过。
- 原生Next构建因个人运行进程占用目录遇EBUSY，未停止个人服务，采用隔离Docker生产构建验证。未运行生产同步、真实E2E、手机/平板/ChatGPT验收。
- 1000对象/10000修订实际apply基准139.277s；heads平均0.782ms；100个冲突整批4.474s；最终10200修订。仅本机QA观察，非分布式性能承诺。
- 规格PASS、质量APPROVED；重放操作、继承数值类型、Gate内嵌Evidence依赖三项审查P2均RED→GREEN修复。六Gate PASS，证据与边界见SPRINT_1_REPORT.md。

### 遗留事项

- 完成Sprint1后STOP，等待人工审查；不进入Sprint2/Secure Relay，不部署生产同步表或accepted查询hook。
- 真实用户presence/keys/签名/E2E、网络transport、移动存储、bootstrap/压缩、完整source/Tag关系图、三方文本/OR-set与生产数值迁移未实现。
- GitHub同步与本次CI在提交推送后核对，最终交付消息记录实际状态；不预先称远端成功。

## RH-010 — 2026-10-07 — Sprint 1 Canonical Identity

### 完成内容

- 冻结RH-C14N-1：UTF-16 key排序、UTF-8、Unicode不归一化、严格数字lexeme与重复key拒绝；科研decimal/integer字符串保留原始精度。
- Python/TypeScript分别实现canonical encoder、strict decoder、change revision与单项目transaction校验，不互相调用编码器。
- 26个独立固定bytes/hash样例、59个协议fixture（7有效、52拒绝）与3个嵌套边界；保存Sprint1原始需求、design delta、执行计划及ADR011–015。

### 验证结果

- 实际先RED后GREEN；Python7个测试方法、TS6项、严格类型检查与Ruff通过，样例对齐全部预期bytes/hash。
- 规格复审发现TS稀疏数组补偿键绕过；质量复审发现两语言递归容量差异。均新增失败回归后修复，嵌套限额冻结64；规格复审PASS、质量复审APPROVED。
- 同轮现有后端/MCP/Release137、前端46及类型通过；本机build遇到运行中目录文件锁，隔离Docker前端生产build成功。未把这些结果当PG Sync验收。

### 遗留事项

- 本提交仅交付wire identity，事务屏障、真实PG并发、Domain Outbox与fresh Human grant在下一迭代实现；Sprint1尚未完成。
- 不启用生产同步，不实现Relay/真实E2E/配对/移动客户端，不操作个人数据库。

## RH-009 — 2026-10-07 — v0.3 Sync Architecture Sprint 0

### 完成内容

- 从已发布的v0.2.0创建codex/researchhub-v0.3；稳定main/tag冻结，生产应用、迁移、部署及个人数据不变。
- 交付docs/sync的12份协议/架构文档、概念ER、22主题报告、ADR-001–010和原始需求；推荐immutable revision DAG、无key Relay、保守科学冲突、四文件政策和trusted pairing。
- 独立Python/SQLite两副本与Relay，合成数据验证CASE1–10及身份/依赖/恢复/权限负向；清楚区分设计、原型和生产实现。

### 验证结果

- 原型34项通过，Ruff通过，临时演示两副本一致、BASE pressure1.4与1.6/1.8候选均保留；先红后绿，具体命令与限制见SPRINT_0_REPORT.md。
- v0.2分支/main/tag三次封版CI均success；本分支既有CI只覆盖稳定产品，未自动纳入原型测试，本地结果单独登记。
- 规格审查PASS；质量审查发现并修复actor/principal不一致导致ACK后不能重放的P2，两项新回归先红后绿，复审PASS。远端同步结果在本轮最终交付消息记录。

### 遗留事项

- 生产Sync、真实E2E/签名/配对/撤销/keys、bootstrap/retention、移动引擎、Remote MCP均未实现。
- 原型未实现跨对象科学冲突整批批准屏障、模块/真实人机权限与跨语言JCS，事务ID仅在batch；不冒充生产验收。
- 完成Sprint0后STOP；须人工确认ADR、文件/云/缓存预算、设备/恢复/保留策略和ChatGPT共享取舍，才进入Sprint1。

## RH-008 — 2026-10-07 — 正式封版 v0.2.0

### 完成内容

- 重新验收当前v0.2应用，冻结为Modular Research Workspace，准备稳定main、v0.2.0标签和GitHub Release。
- 尊重用户最新公开仓库决定，修正文档与只读可见性检查；移除自动改变可见性行为，新增10项回归并纳入CI。
- 保留历史v0.2报告，增加docs/RELEASE_V0.2.0.md，明确未来同步/ChatGPT Remote MCP/完整科学软件Agent尚未实现。

### 验证结果

- 当前HEAD后端/MCP127、Release检查10、前端46、真实服务23项重新通过；类型、Ruff、原生/Docker构建和新空PG 0001–0005迁移通过。
- 真实Codex客户端七工具、结构化读回、codex/mcp审计及临时令牌撤销通过；隔离QA重启和备份恢复通过。
- 个人PG/MinIO已新备份，40表145原记录原始列保留，个人服务与电脑入口恢复；没有导入QA或修改生产科研数据。
- 两阶段审查通过。具体命令范围、警告与未验收边界见Release报告；发布后核对稳定SHA、tag、Release及CI。

### 遗留事项

- 实体设备/PWA、ChatGPT远程连接、插件安装与完整真实UI模块升级仍未验收；v0.3须从v0.2.0开始，仅完成架构Sprint0后等待人工审查。

## RH-007 — 2026-10-07 — v0.2 Sprint 3 真实连接与交付

### 完成内容

- 18 个语义 MCP 与 3 个兼容别名、聚合分页和范围权限；同项目已有文件安全注册。
- 0005 可空代码来源列，项目仓库与 Run 分支/完整 SHA/Issue/PR；独立中文编辑与来源链接。
- 本机 Codex 连接脚本、Plugin/Skill 包、配置示例与 ChatGPT 安全连接评估；最终 v0.2 报告。

### 验证结果

- 后端/MCP 127、前端 46、真实 PostgreSQL/MinIO/API/MCP/并发/重启/恢复 23 项通过；类型、生产构建和 Ruff 通过。
- 真实 Codex 完成七工具调用及读回，合成零值/未知单位、笔记与星标保存，审计 codex/mcp，临时令牌撤销成功。
- 个人迁移前备份，40 张原表、144 条原记录原始列保留；电脑入口恢复。浏览器实际代码来源保存、桌面/手机视口 PNG 上传通过。
- 规格/质量复审通过；验收边界和未验证部分见 docs/V0.2_REPORT.md。推送后核对私有状态、远端 SHA 和 CI。

### 遗留事项

- ChatGPT 实际接入、宿主 Plugin 安装、实体设备/PWA/真实视频尚未验证；OAuth/Tunnel 运行服务未实现。
- 手机/平板独立部署暂缓；长期个人 Codex 连接需按 CONNECTIONS.md 配置。GitHub 目前登记代码来源，不自动读取远端内容。

## RH-006 — 2026-10-07 — v0.2 Sprint 2 研究理解与模块界面

### 完成内容

- 分页参数/指标历史与完整父子差异，谱系、证据正反向追踪、降级影响预览和指标完整来源。
- 模块 0.2.1 驱动导航、表单、组件和专属视图；旧项目冻结定义保留。实际数值时间序列按单位分组，不虚构最佳结果。
- 研究记录渐进编辑、独立 AI/人工结论和中文移动快速采集；增加受限视频文件支持及 0004 迁移。

### 验证结果

- 后端/MCP 116、前端 41、真实 PostgreSQL/MinIO/Docker/MCP/恢复 20 项通过；类型、生产构建和 Ruff 通过。
- 个人数据库备份后迁移，39 张原表、47 条原记录原始列保留；本机服务与电脑入口恢复正常。
- 实际浏览器首屏/差异/谱系/合成移动实验与 390px 布局检查；规格/质量复审通过。具体范围见 docs/SPRINT_2_REPORT.md。

### 遗留事项

- Sprint 3 MCP、实际 Codex/ChatGPT 和 GitHub 代码来源关联继续开发。
- 浏览器照片选择器全流程、实体设备/PWA 尚未验证；API 文件字节验收已通过。

## RH-005 — 2026-10-06 — v0.2 Sprint 1 人优先研究工作流

### 完成内容

- 新增七类能力、四字段轻量创建、模块分组表单、克隆与文件引用、独立星标、标签及数据库分页筛选。
- 分组保存保留 null/零/实际单位/来源，新增独立工作表查询防止分页遗漏覆盖；已有分页之外的关系编辑仍保留。
- Activity 隐藏与不可变 Audit 分开，项目 ZIP/Markdown/审计导出，Bundle 校验预览与人工原子确认及失败对象清理。
- 补齐文件与回收站/人工 GC 界面、新 0003 迁移、可按迭代命名的个人备份和逐行保留检查、合成 Bundle 示例与打包工具。

### 验证结果

- 后端/MCP 99、前端 31、真实 Docker PostgreSQL/MinIO/MCP/PG 并发 18 项通过；类型、生产构建与 Ruff 通过。
- 个人备份后迁移至 0003，30 张原表、47 条原记录原始列保持；本机服务与电脑入口恢复正常。
- 实际浏览器创建/分组保存/负结果/星标/克隆/参数差异/Bundle 预览确认及移动视口检查；两阶段审查修复并复审通过。范围见 docs/SPRINT_1_REPORT.md。
- RH-004 远程 CI 已成功；本轮推送后核对 private、远端 SHA 和 CI。

### 遗留事项

- Sprint 2/3 尚未交付；自定义参数/指标及完整差异分页在下一迭代完成，当前明示截断并保护分组保存。
- 实体设备和实际 Codex/ChatGPT 连接仍未验证；协议通过不能替代。

## RH-004 — 2026-10-06 — v0.2 Sprint 0 数据保护与恢复基础

### 完成内容

- 从 RH-003 建立独立 v0.2 分支；0001 保持不变，新增 0002 冻结历史模块定义、增加生命周期与对象清理 outbox。
- 项目冻结 module_version/module_snapshot，人工升级必须查看差异并提交版本和目标摘要；写入校验使用项目快照。
- 限制 AI 令牌的科研确认、人工结论、已审阅证据/指标/决策和已通过关卡修改；解析后的布尔值也再次授权。
- 实现归档、回收站、恢复、30 天后人工永久删除，以及拥有范围和活动引用保护的可重试文件清理；上传失败与丢失响应均保留清理意图。
- 项目优先写锁及状态刷新，避免恢复/删除、AI 写入/人工确认、Run 创建/模块升级竞争；同一项目写入串行化。
- 增加中文数据管理、各类对象恢复入口、项目名称二次确认；升级 Vitest 修复已安装依赖审计问题。
- 添加 GitHub CI、隔离 Compose QA、个人备份与逐行迁移验证、真实 PG 并发和备份恢复测试。

### 验证结果

- 后端/MCP 71 项、前端 21 项通过；TypeScript、生产构建、Ruff 和 diff 检查通过。
- 真实 Docker PostgreSQL/MinIO/API/Web 构建并健康启动；实际服务与 PG 并发 15 项、容器重启持久化 1 项、恢复到全新数据库/桶 1 项通过。
- 个人数据库已备份并迁移至 0002：29 张原表、47 条原记录的原始列逐行保持；本机服务恢复，电脑入口幂等检查通过。
- 实际浏览器完成 Run 归档和恢复、模块升级预览；390px 手机视口无横向溢出。截图及范围见 docs/SPRINT_0_REPORT.md。
- 规格审查与质量审查发现的问题修复并复审通过。GitHub 已只读确认 private=true；远程 CI 结果在推送后核查。

### 遗留事项

- Sprint 1–3 尚未交付；永久删除/GC 暂提供人工 API，界面入口随数据管理迭代补齐。
- 实体手机拍照/PWA 安装、实际 Codex 宿主与 ChatGPT 连接尚未验证；协议测试不能替代。
- pytest 两项依赖弃用/类型警告、Vite 配置扩展名警告不影响本轮通过结果。

## RH-003 — 2026-10-05 — 简体中文界面与电脑快捷入口

### 完成内容

- 保留功能、导航和 Core/Module 结构，将系统预置导航、页面、表单、状态、来源类别、研究类型与模块阶段名称统一为简体中文。
- 显示中文但保留 API/数据库枚举及模块标识；不自动改写已有科研记录。新增演示预置文字也使用中文并保留 DEMO/SYNTHETIC 标识。
- 提供桌面 Research Hub 快捷方式和仓库内打开ResearchHub.cmd：启动已有本地环境，服务已运行时直接打开，启动失败给出提示。
- 原生服务健康检查兼容 Windows PowerShell 5.1；桌面快捷方式只面向本机个人环境，保留数据与首次注册。
- 按用户要求暂不打包部署手机/平板入口。

### 验证结果

- 后端/MCP 40 项、前端 18 项、TypeScript 检查和生产构建通过；PowerShell 脚本语法检查通过。
- 实际检查中文首页、ICE 阶段/关卡与研究记录编辑器，枚举选项显示中文。
- Windows PowerShell 实测启动入口；桌面快捷方式目标、参数、工作目录和图标核查通过；已运行时再次打开不重复启动服务。
- 将 PostgreSQL、MinIO、API 和 Web 全部停止后，实际运行桌面 .lnk，四项服务恢复，API/Web 均返回 200，仍使用个人数据库。

### 遗留事项

- 原有 Docker 完整验收与外部 MCP 连接限制仍在；手机/平板部署按本轮要求暂缓。

## RH-002 — 2026-10-05 — 实现并运行科研 Hub v0.1 主体

### 完成内容

- 建立 Next.js/FastAPI/PostgreSQL/MinIO 独立系统，29 张应用表与冻结 Alembic 迁移。
- 实现账户、Core CRUD、父子 Run、参数来源、Metrics、Artifact SHA256、Evidence/Claim 关联、Task/Milestone、Note/Decision/Risk、Stage/Gate 与审计。
- Generic/HDSP/ICE manifest 共用 Core；ICE 依据指定路线图保留 A–E/G0–G5，HDSP 保留固定目标面打印边界。
- 证据删除或降级使失去有效支持的已通过 Gate/Criteria 自动失效，并在同一事务审计。
- 实现响应式桌面/手机页面、PWA 静态离线说明、九个受范围控制的本地 MCP 工具、Compose 与备份恢复脚本。
- 准备真实原生服务供当前电脑使用；QA 数据独立且明确 SYNTHETIC。保留个人首次账户创建体验。

### 验证结果

- 后端/MCP 40、前端 18、真实 PostgreSQL/MinIO 集成 8、真实 MCP 2、服务重启持久化 1、空目标备份恢复 1，合计 70 项通过；环境与限制见 docs/V0.1_REPORT.md。
- Next.js 生产构建、Ruff、pip check、PowerShell 语法、三种 Compose config 与迁移检查通过。
- 实际浏览器桌面/平板/手机视口操作和截图，worker ready 与停服务后的静态离线回退均已验收。

### 遗留事项

- Windows 虚拟化组件等待电脑重启：Docker 完整构建启动、容器网络/命名卷、LAN HTTPS 与 Compose 恢复封装尚未运行。
- 实体手机访问/拍照与 PWA 安装、外部 ChatGPT/Codex 连接未验证；按用户标准尚未完整验收。
- 搜索分页/标签关联、对象垃圾回收、应用内 GitHub 进度读取与远程 MCP 尚未实现。

## RH-001 — 2026-10-05 — 建立 GitHub 私有仓库连接

### 完成内容

- 创建 `Zh9426/ResearchHub` 私有仓库，通过 GitHub 插件确认可见性为 `private`。
- 配置本地 `origin` 为 `https://github.com/Zh9426/ResearchHub.git`。
- 推送初始提交 `08dc717`，建立 `main` 到 `origin/main` 的跟踪关系。
- 更新项目说明、同步操作说明与开发路线，记录已完成的仓库连接。

### 验证结果

- 首次 `git push -u origin main` 成功。
- 本地与远程 `main` 初始提交 SHA 均为 `08dc717c1c90eb51a32ba9a762f788481cdb50e9`。
- 本次只更新连接状态和文档，不包含应用代码，无应用运行测试。

### 遗留事项

- 确定首版科研进度管理功能、使用方式与技术栈。
- 应用内读取科研项目的 GitHub 进展尚未实现。

## RH-000 — 2026-10-05 — 仓库与开发规范初始化

### 完成内容

- 初始化本地 Git 仓库，主分支为 `main`。
- 创建项目说明、开发约定、提交规范、提交模板和后续路线。
- 规定每次提交都包含提交详情、迭代说明、验证结果与后续工作。
- 配置常见构建产物、凭据及个人运行时数据的忽略规则。

### 验证结果

- 本次为文档与仓库初始化，不包含应用代码，无应用运行测试。
- 提交前检查文本差异与暂存文件清单。

### 遗留事项

- 创建并验证 GitHub 私有仓库，完成本地初始提交的推送（已在 RH-001 完成）。
- 确定首版功能、使用方式与技术栈。
