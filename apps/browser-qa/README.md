# 隔离浏览器离线工作台

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
