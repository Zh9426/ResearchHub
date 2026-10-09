# Sprint 3A 实际页面与测试证据

2026-10-09，Windows 10.0.22631 x64 / Chromium 156.0.8078.4。固定 origin `http://127.0.0.1:3313`，全部为独立 profile 中的 SYNTHETIC 数据。图片由实际页面截图产生，未经绘图替换；根协调者已逐张查看。移动图只是 390×844 视口的 full-page 截图，不是实体手机验收；桌面视口 1280×900。

| 页面 | 图片 | SHA-256 |
|---|---|---|
| HDSP 桌面：失败、阴性、星标、观察与 pending | [hdsp-failed-negative-desktop.png](hdsp-failed-negative-desktop.png) | `24815fa46ea9c7916451069e1f2f4d3f126ac8477d1e81453e538aac2ce69e39` |
| HDSP 390px 移动视口 | [hdsp-failed-negative-mobile.png](hdsp-failed-negative-mobile.png) | `c5acfb2a30e694caba95176c101606b7ecb586855a1fa34c01a937479e77e1f0` |
| 已保存 Note 桌面 | [note-saved-desktop.png](note-saved-desktop.png) | `f5e3c4244e317b8118d4956a9a90a4a1feda85676711c1dad36d31d40fbd9a87` |
| 已保存 Note 390px 移动视口 | [note-saved-mobile.png](note-saved-mobile.png) | `f84afc3e8f9e443812bd14cf5586cb27f6b48b1330d24be591057fb9f6d2e135` |
| 新 profile 恢复、救援草稿与诊断桌面 | [rescue-desktop.png](rescue-desktop.png) | `3d7e45d430dda4508dfdf4da505f9e2ce57db01986f8f82d822c48f7bc44b0ce` |
| 救援与诊断 390px 移动视口 | [rescue-mobile.png](rescue-mobile.png) | `25a486444c9471081a9904507406050e25f1f226d584d47d750952f9a2bcbb9f` |

[脱敏测试摘要](test-summary.json)：最终完整 17 PASS、0 retry；237 固定 wire 检查。构建 JS+CSS SHA-256 为 `7f7b3c0cc1a50b241924a9bc1df9a556b826a7807d6420e55db9c71656b594c0`。

本机原始日志/JUnit/摘要保留在 ignored `storage/runtime/browser-local-qa/evidence/attempt-2/`；紧凑布局修改前的首轮17 PASS保留在 `attempt-1/`。此前清理失败RED的实际tool输出转录保留在 `red-observed-transcript.txt`，该文件明确不是重定向原始日志。它记录close抛错后服务未释放、5秒断言失败；补丁使全部自有资源均尝试释放，最后传播聚合错误。

复验命令（仓库根；首次环境先按[QA说明](../../../apps/browser-qa/README.md)安装依赖与专用浏览器）：

```powershell
npm --prefix apps/browser-qa run typecheck
npm --prefix apps/browser-qa run build
npm --prefix apps/browser-qa test
```

每次测试使用新合成profile，进程重开测试复用本次profile；retries=0。原始profile、CryptoKey、nonce账本、救援JSON、HAR及数据库导出均不入Git。CI按run_id/attempt上传白名单PNG/JUnit/摘要，不能用绿色结果关闭TLS-001。完整场景与限制见[验收报告](../../sync/SPRINT_3A_REPORT.md)。
