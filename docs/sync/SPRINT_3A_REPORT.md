# Sprint 3A 浏览器离线工作台验收记录

状态：实施中，尚未完成核心本地工作流验收。以下仅记录已执行证据；最终报告在全部任务与复审后更新。

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
| 独立复审 | Task1规格PASS、质量补丁复审APPROVED | 浏览器启动失败清理为静态复核，尚无独立启动失败注入证明 |
| RH-022 精确提交CI | 4 jobs success | `08aafe4a1c1ff8123b3cf9f53d5887cf00c72628`，[37867406210 attempt 1](https://github.com/Zh9426/ResearchHub/actions/runs/37867406210)；20轮TLS诊断保存于 `ci-37867406210-attempt1/`，不关闭TLS-001 |
| 本地模型与工作台 | 4 tests PASS / 12.2s | `task2-delivery-verified.log`：服务停止后Run/Note/失败阴性星标；同profile进程退出重开后全snapshot相等；刷新不重灌；双tab CAS/另存/并行创建；写后abort全回滚 |
| 保存边界故障 | RED→GREEN | `task2-red-notification.log`、`task2-red-refresh.log`：通知失败或提交后读取失败不能否定已经提交的事务 |
| Task2 独立复审 | 规格PASS、质量APPROVED | 审查代码、测试和保留日志；审查者未重复执行浏览器，未将审查计为新测试 |

全部上述路径相对 ignored `storage/runtime/browser-local-qa/`。初始沙箱 ENOTCACHED/EPERM、构建扫描误匹配以及使用旧构建的中间测试均在 `task1-attempts.txt` 区分，未计入最终构建验收。所有浏览器测试 `retries=0`。

## 验收状态

| Gate | 当前状态 |
|---|---|
| G1 离线启动与进程重开 | 本地记录闭环已实测；最终完整验收待完成 |
| G2 对象/队列/审计原子性 | Task2实际IDB写后abort与snapshot全等通过，两阶段复审通过 |
| G3 双标签页保护 | Task2一成一拒、保留输入、比较/另存及不同记录并发通过，两阶段复审通过 |
| G4 星标、状态与救援恢复 | 星标/状态通过，救援待实现 |
| G5 浏览器协议、key/nonce边界 | 待适配与验证 |
| G6 隔离与TLS证据 | 已核对基线，最终复核待完成 |

## 交付分类

- **IMPLEMENTED IN BROWSER QA**：隔离静态应用壳、SW就绪检查、固定origin/专用profile CLI；三合成项目、Run/Note/星标、原子本地命令及CAS。
- **VERIFIED IN REAL DESKTOP BROWSER**：离线编辑、进程重开、直接详情导航、刷新、两标签页CAS、未知缓存保留、端口占用拒绝。
- **VERIFIED ON PHYSICAL MOBILE**：无；390px截图只是移动视口。
- **FAULT-INJECTED ONLY**：首次SW静态资源503安装失败与恢复；实际IDB写后abort；通知故障和提交后读取故障。不是物理磁盘满或断电证明。
- **DESIGNED ONLY**：尚未实施的后续步骤见实施计划，不作为验收。
- **NOT IMPLEMENTED**：真实Push/Pull、后台同步、完整DAG批准、配对/撤销/epoch恢复、相机/文件同步、生产Recovery Kit。
- **BLOCKED FOR NETWORK / PRODUCTION**：TLS-001 OPEN；完整浏览器安全适配、站点一致回滚、平台驱逐/断电保证、生产vault及真实授权均未证明。

启动和停止命令见 [浏览器QA说明](../../apps/browser-qa/README.md)。最终截图、A–L矩阵、完整回归及精确SHA/CI结果将在本报告补全；此阶段不宣布Sprint3A完成。
