# 隔离浏览器 QA 应用壳

固定 origin：`http://127.0.0.1:3313`。只在此地址启动；不要用 localhost。服务启动遇到端口占用会失败，不终止原监听者。全部构建、浏览器二进制、profile、截图与日志存于 ignored `storage/runtime/browser-local-qa/`，不得上传 profile。

从仓库根运行：

```powershell
npm ci --prefix apps/browser-qa
npm run install:browser --prefix apps/browser-qa
npm run build --prefix apps/browser-qa
npm start --prefix apps/browser-qa
```

另一终端打开专用 Chromium：`npm run browser --prefix apps/browser-qa`。手动 profile 固定为 `storage/runtime/browser-local-qa/profiles/manual/`。首次点击“初始化离线资源”，等待“离线资源已就绪”，再运行 `npm run stop --prefix apps/browser-qa`。`npm run browser:stop --prefix apps/browser-qa` 关闭该工具启动的浏览器，再运行 browser 命令即可在服务停止时离线重开。停止CLI只使用QA运行目录的随机owner token，不按端口杀进程、不访问个人profile。

测试：`npm test --prefix apps/browser-qa`；类型检查：`npm run typecheck --prefix apps/browser-qa`。测试要求先build，自动在固定3313启动/停止自己的静态服务。workers=1，retries=0。每次测试使用独立profile，重开阶段复用该profile。CDP取得当前浏览器进程ID；context.close后用OS进程存在性检查确认全部退出，再启动新的persistent context。此证明不是操作系统断电或浏览器崩溃恢复证明。测试截图390px只是移动视口。

可支持路由：`/`、`/diagnostics`、`/projects/{generic|hdsp|ice}` 及其 `/runs/{id}`、`/notes/{id}`（id为字母数字或连字符）。SW只缓存枚举HTML/JS/CSS/icon，拒绝其他origin，不缓存API；不删除未知缓存、不skipWaiting强刷页面。旧版本缓存暂保留，后续升级策略另行设计。

后续组合接口：`src/main.tsx`导出 `QaShell({children})`，在children接入浏览器LocalCommandService工作台。当前空壳不创建项目/记录、不调用数据库/API；三个项目链接只是合成模块入口。共享纯展示组件 `apps/web/src/components/presentational.tsx` 与纯翻译表可在浏览器导入；旧 `ui.tsx` 兼容reexport但仍包含服务端API调用，QA不得导入它。前端bundle由esbuild platform=browser及输入图禁止API/auth/Next依赖。所有Node imports只存在build/test/CLI工具中，不作为浏览器业务计算。

专用浏览器异常退出恢复：若 `browser-owner.json` 残留，先使用该文件记录的PID在任务管理器/`Get-Process -Id <pid>`核查控制进程，并检查是否仍有命令行指向 `storage/runtime/browser-local-qa/profiles/manual` 的Chromium进程。只要任一进程仍在，或无法确定归属，就不要删除owner文件，不要启动第二个浏览器；正常关闭该QA浏览器/控制进程后再检查。仅在确认控制进程和该专用profile浏览器均已退出后，删除 `storage/runtime/browser-local-qa/browser-owner.json` 再运行browser命令。保留profile内容，不删除个人浏览器锁、不终止未知进程。CLI默认拒绝残留owner，防止误入仍在使用的profile。
