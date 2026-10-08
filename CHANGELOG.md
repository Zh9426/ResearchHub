# 迭代日志

每次提交均需更新本文件，按最新迭代在前记录。日期采用 Asia/Shanghai。

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
