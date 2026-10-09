# Sprint 3A：浏览器离线工作台设计增量

2026-10-09。基线 `b882738916c320e1a8c6ef43e33ab27f3b128a9d`；开发分支 `codex/researchhub-v0.3` 与远端一致，工作树干净。稳定 main/v0.2.0 保持 `4a4db4a`。TLS-001 OPEN，原始记录、测试及诊断不变。

## 范围与实现选择

采用 `apps/browser-qa` 的 React 静态 QA 入口，复用现有 React、Lucide、CSS tokens 和纯展示组件。现有 Next 产品应用、API 与生产部署保持原状。独立 esbuild 只负责打包静态资源，运行时不依赖 Node、SSR/RSC、在线登录或API。相比把完整 Next 私密页面缓存起来，这一入口可明确枚举无敏感内容的应用壳；不另建一套领域引擎。

固定 origin `http://127.0.0.1:3313`（已检查无监听）。严格拒绝其他 origin；不混用localhost。专用浏览器profile位于ignored `storage/runtime/browser-local-qa/profiles/`，构建与日志位于同一QA目录。自动测试仅创建自己的profile，不访问个人Chrome/Edge状态。持续显示“浏览器离线实验版 · 仅合成数据 · 未接入跨端同步”。

React客户端 → LocalCommandService → 同一IndexedDB事务（对象、local edit version、LocalOperation、LocalAudit）。操作只在transaction complete后成功；短事务内CAS重验版本。密码、hash、文件读取等异步准备在事务外完成。BroadcastChannel只通知，不承担并发正确性。

明文QA草稿：Generic/HDSP/ICE冻结模块snapshot、Run/Note及星标。LocalOperation是versioned local格式，不是SyncTransaction/SecureEnvelope。无真实发送/接收、科学批准、配对或生产vault。新profile救援恢复使用新设备身份；包内保留原事件来源，不带钥匙、nonce、信任状态。

## 体验与失败行为

延续现有白底、灰色侧栏、深青色主按钮、44px控件和简体中文。项目列表/记录列表/渐进详情编辑/诊断救援页面；不使用巨大通用Modal。新建仅标题、模块类型、可选目标；观察、星标及可选说明在详情完成。科研状态默认未知/计划中，不自动生成结果。

本地保存、传输、review独立展示。事务失败保留当前输入并可导出草稿；CAS过期提示比较当前版本或另存。恢复先预览，摘要仅完整性校验，重复导入幂等、同ID异内容拒绝。存储拒绝/不支持/配额/升级阻塞明确提示，不deleteDatabase自动修复。

## 离线与安全探针

生成包含HTML/JS/CSS/图标的版本化应用壳；SW仅处理明确QA资源、使用自身缓存前缀，不清理未知缓存，不强制刷新未保存页面。初始化离线就绪后，停止QA静态服务再离线创建、关闭浏览器进程、同profile重开和直接详情导航。

协议纯逻辑从Node hash入口分离，浏览器WebCrypto异步SHA256验证原固定向量，Node/Python期望不变。星标未在wire v1白名单，保持LocalOperation待adapter。独立CryptoKey/nonce探针只验证当前Chromium：non-extractable key的IDB持久化，authority测试上下文prefix+事务预约counter，丢失/损坏拒绝旧key，不导入nonce状态。全站一致回滚、平台断电、驱逐、XSS及生产恢复仍BLOCKED FOR NETWORK / PRODUCTION。

## 实施与验收矩阵

1. 静态入口/离线壳/专用profile与真实浏览器启动：G1/G6。
2. 本地模型、CAS、事务、队列、审计：G2/G3。
3. Run/Note/星标及救援、错误状态：G4。
4. 纯协议适配、浏览器key/nonce诊断：G5。
5. 真实浏览器A–L场景、桌面/移动视口截图、既有回归/精确SHA CI：G1–G6。

遵循附件顺序交付可运行功能；代码任务先真实RED、实现后GREEN，任务间先规格复审再质量审查。仅一个实施worker写代码，避免并行修改共享文件。根协调者负责集成、证据与提交。最后报告区分真实浏览器、故障注入、未实现与生产阻塞；不自动进入3B。

## 官方依据与技能

- [IndexedDB事务生命周期](https://w3c.github.io/IndexedDB/#transaction-lifecycle)：成功以transaction complete为界，活跃事务不跨任意异步等待。
- [Storage Standard](https://storage.spec.whatwg.org/)与[MDN配额/驱逐](https://developer.mozilla.org/en-US/docs/Web/API/Storage_API/Storage_quotas_and_eviction_criteria)：persist是请求，拒绝与驱逐必须处理。
- [WebCrypto](https://www.w3.org/TR/webcrypto/)：实际浏览器探测CryptoKey能力，不把non-extractable解释为硬件或同源脚本防护。

已阅读本机frontend-app-builder与ui-ux-pro-max。以用户明确要求的现有设计语言为设计基准，不另做图像生成改版；采用其组件复用、真实页面检查、可访问性/触控/错误保留原则。隔离持久profile与进程重开验收使用Playwright真实Chromium，不使用个人IAB profile；移动视口不是实体移动验收。brainstorming/writing-plans用于此短增量，subagent-driven-development用于逐任务实现和独立两阶段审查。
