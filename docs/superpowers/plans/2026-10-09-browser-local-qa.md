# Sprint 3A Implementation Plan

> 使用 superpowers:subagent-driven-development 逐任务实施；每项先规格、再质量独立审查。用户已授权附件范围与顺序，无须重复设计审批。

**Goal:** 隔离真实浏览器中可离线保存、关闭进程重开并救援恢复的合成科研工作台。
**Architecture:** 独立固定QA origin；React静态应用壳；同库IDB原子命令/CAS；纯协议适配和隔离key/nonce探针，无真实传输。
**Tech Stack:** 现有React19/Lucide/CSS，esbuild0.28.2，Playwright1.64.0真实Chromium，TypeScript/IndexedDB/WebCrypto。

## Task 1：隔离入口与离线壳
- [x] 创建apps/browser-qa/package.json/build.mjs/server.mjs、index.html、src/main.tsx、SW生成器及tests/shell.spec.ts。
- [x] 优先写失败的真实浏览器壳测试；固定127.0.0.1:3313，profile仅storage/runtime/browser-local-qa下；端口占用拒绝，不终止未知服务。
- [x] 复用globals.css与提取的纯展示组件；不引入API/auth/Next运行时。构建枚举静态资源并拒绝node:*进入浏览器bundle。
- [x] 明确点击初始化后等待SW控制与离线资源就绪；停止静态服务后同profile浏览器进程重开/直接本地路由通过。未知Cache保留，SW更新不强刷。
- [x] 规格→质量复审，根协调者检查暂存/CHANGELOG并提交推送。

## Task 2：本地命令与最小工作台
- [x] src/local/{model,db,commands,seeds}.ts：冻结三模块snapshot/hash；空空间显式种子初始化；稳定UUID及新workspace/device身份。
- [x] IDB事务内get→CAS→object+operation+audit+local_version写入；resolve只在oncomplete；注入写后abort实证全部回滚。
- [x] Run/Note详情、星标/筛选、本地保存/未连接传输/review状态独立；过期编辑保留输入、比较/另存；BroadcastChannel仅通知。
- [x] 真实浏览器验证离线核心闭环、两tab不同ID并存/同版本一成一拒、保存失败输入保留。规格→质量复审后提交。

## Task 3：救援与存储错误
- [x] src/local/rescue.ts与storage.ts：完整明文合成包，strict schema+canonical摘要，排除key/nonce/信任；预览、原子恢复、重复幂等、碰撞拒绝、新身份、保留事件source。
- [x] 当前未保存输入另存到救援草稿；quota/abort/persist拒绝/升级blocked可见，不删库；真实IDB abort与模拟quota区分记录。
- [x] 独立空profile恢复/重复/冲突、草稿恢复、无key克隆；规格→质量复审后提交。

## Task 4：浏览器协议与受限安全探针
- [x] packages/sync-protocol提取纯canonical/schema与Node digest包装，browser入口异步WebCrypto；原vector bytes/hash/error不变。BROWSER_ADAPTER_MATRIX列Node-only与星标差异。
- [x] src/probes：独立non-extractable QA CryptoKey持久化/重开，固定合成authority prefix+同事务counter预约及缺失/损坏fail-closed；exact retry保存完整封装，不导入ledger。
- [x] 实际Chromium执行固定向量、双tab nonce竞争与耗号/刷新/重开；遗留平台保障标BLOCKED FOR NETWORK USE。规格→质量复审后提交。

## Task 5：完整验收与停止
- [ ] 真实browser A–L、进程终止/重开、静态server停止、桌面/移动截图并view_image检查；不得seed重灌模拟恢复。
- [ ] 相关Node/Python协议/安全、前端回归；新增browser-local-qa CI，artifact仅截图/脱敏结果，不上传profile/key/HAR/dump。TLS失败独立归档，不重跑到绿。
- [ ] SPRINT_3A_REPORT.md及演示说明/证据索引：G1–G6、七状态分类、浏览器/OS/命令/真实与注入边界。最终审查、聚焦中文四段RH递增提交、remote精确SHA/CI核对。
- [ ] STOP；仅列3B候选，不启动同步/生产迁移/公网部署，不移动稳定标签。
