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
| RH-023 精确提交CI | 4 jobs success | `e88519429b8ce98284e4b99539c6e658c1670ed6`，[37868749984 attempt 1](https://github.com/Zh9426/ResearchHub/actions/runs/37868749984)；TLS20轮诊断归档 `ci-37868749984-attempt1/` |
| 救援与存储 | 完整7 tests PASS；adapter补丁后3 PASS /16.6s | `task3-full-attempt1.log`、`task3-transport-green.log`；实际下载→新profile文件预览/恢复、幂等、冲突、严格字段/摘要、原来源/新身份、未保存草稿、真实导入abort和升级阻塞/失败 |
| 非空pending故障 | 1 PASS /10.4s | `task3-nonempty-pending.log`；先保存Note并断言pending非空，quota与TEST ONLY adapter拒绝后完整快照和dirty输入不变 |
| RH-024 精确提交CI | 4 jobs success | `906a83fa8cbb66a36d75feb84a630a72a6b877ec`，[37869813951 attempt 1](https://github.com/Zh9426/ResearchHub/actions/runs/37869813951)；TLS20轮诊断归档 `ci-37869813951-attempt1/` |
| 浏览器wire与安全探针 | 全部11 tests PASS /35.6s；追加2 PASS /4.5s | `task4-browser-final.log`、`task4-browser-interruption.log`；原26/59/3/10场景20step共237检查；AES-GCM key重载、双tab/刷新/重开、exact retry、耗号、损坏/缺失/旧导入拒绝及实际key救援排除 |
| 关联安全回归 | Node48、Python191 PASS | `task4-node-security.log`、`task4-python-security.log`，Python21.91s；protocol Node7及两包typecheck通过；原fixtures及TLS调查文件哈希未变 |

全部上述路径相对 ignored `storage/runtime/browser-local-qa/`。初始沙箱 ENOTCACHED/EPERM、构建扫描误匹配以及使用旧构建的中间测试均在 `task1-attempts.txt` 区分，未计入最终构建验收。所有浏览器测试 `retries=0`。

## 验收状态

| Gate | 当前状态 |
|---|---|
| G1 离线启动与进程重开 | 本地记录闭环已实测；最终完整验收待完成 |
| G2 对象/队列/审计原子性 | Task2实际IDB写后abort与snapshot全等通过，两阶段复审通过 |
| G3 双标签页保护 | Task2一成一拒、保留输入、比较/另存及不同记录并发通过，两阶段复审通过 |
| G4 星标、状态与救援恢复 | 真实新profile救援、幂等/冲突/未保存草稿通过；Task3规格PASS、质量APPROVED |
| G5 浏览器协议、key/nonce边界 | 237固定检查与受限AES-GCM/key/nonce探针通过；Task4规格PASS、质量APPROVED，网络仍BLOCKED |
| G6 隔离与TLS证据 | 已核对基线，最终复核待完成 |

## 交付分类

- **IMPLEMENTED IN BROWSER QA**：隔离静态应用壳、SW就绪检查、固定origin/专用profile CLI；三合成项目、Run/Note/星标、原子本地命令及CAS；明文救援预览/恢复、存储风险与故障提示；纯wire browser入口及独立AES-GCM/key/nonce探针。
- **VERIFIED IN REAL DESKTOP BROWSER**：离线编辑、进程重开、直接详情导航、刷新、两标签页CAS、未知缓存保留、端口占用拒绝；新profile文件救援、key持久重载/加解密、nonce跨tab和完整封装重试、固定wire向量。
- **VERIFIED ON PHYSICAL MOBILE**：无；390px截图只是移动视口。
- **FAULT-INJECTED ONLY**：首次SW静态资源503；实际IDB写后abort、导入中止与升级中止；通知/提交后读取故障；模拟QuotaExceededError、persist拒绝/不支持与TEST ONLY adapter拒绝；加密拒绝/挂起和局部IDB损坏。真实升级阻塞已触发并解除；加密挂起后正常关闭全部浏览器进程，不是崩溃、物理磁盘满、断电或TLS证明。
- **DESIGNED ONLY**：尚未实施的后续步骤见实施计划，不作为验收。
- **NOT IMPLEMENTED**：真实Push/Pull、后台同步、完整DAG批准、配对/撤销/epoch恢复、相机/文件同步、生产Recovery Kit。
- **BLOCKED FOR NETWORK / PRODUCTION**：TLS-001 OPEN；完整浏览器安全适配、站点一致回滚、平台驱逐/断电保证、生产vault及真实授权均未证明。

启动和停止命令见 [浏览器QA说明](../../apps/browser-qa/README.md)。最终截图、A–L矩阵、完整回归及精确SHA/CI结果将在本报告补全；此阶段不宣布Sprint3A完成。
