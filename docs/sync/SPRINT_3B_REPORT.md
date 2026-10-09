# Sprint 3B 实施记录（进行中）

本文件在本轮验收完成前不代表封版。`SPRINT_3B_QA_INTEGRATION = INCOMPLETE`；`TLS-001 = OPEN`；`PRODUCTION_READY = NO`；`PHYSICAL_MOBILE_VERIFIED = NO`。

## 基线与隔离

2026-10-09，从干净工作树 `187fdfd10f34027882ed7c0f52f472b66e78295c` 继续 `codex/researchhub-v0.3`，当时远端一致。用户明确授权受控 loopback QA；仓库保持用户指定公开状态。main/v0.2.0 均保持 `4a4db4a4bd54a598f640d7de99281c15bd46e3b9`。仅合成数据，不连接生产数据库或个人浏览器 profile。

3A 保留3313；3B浏览器3314、PC入口3315、既有Relay HTTPS38001；业务QA PostgreSQL35433和Relay35434独立。详细边界见 [设计增量](SPRINT_3B_DESIGN_DELTA.md)。

## 已完成的内部迭代

### A1 — RH-028 / 1fd6a0fbaa263ceb024fff965acf02a05438d51c

`IMPLEMENTED`：显式(2,2) Run/Note协议、Run星标精确字段、Kernel版本物化、内外Envelope版本绑定及能力声明。原v1向量/套件不变。独立规格、质量审查PASS。

- 本机Python完整sync_vectors+secure_sync初轮221PASS；后续扩展v2定向28PASS、tmp_path修正后安全8PASS；Node协议初轮26PASS、扩展v2定向25PASS、安全51PASS；两包typecheck通过。
- 本机真实隔离QA PostgreSQL旧Kernel/Domain/Outbox回归132PASS，23.88s。
- [精确SHA首次CI37875621054](https://github.com/Zh9426/ResearchHub/actions/runs/37875621054)，attempt1，五job全部success。Linux Chromium156.0.8078.4旧3A17项PASS、retries0；旧TLS固定20轮通过。这不是3B浏览器安全或双向网络Gate证据，也不关闭TLS-001。
- CI归档在被忽略的 `storage/runtime/browser-local-qa/ci-37875621054-attempt1/`；TLS zip SHA256 `93d72922d0f662f6ac6deba72258acfef85e3d47df5b3d99558bab578a9f6469`；browser zip `3d33a45d60fc21d0d62d274be5944fc5450e13f0e6efbc61fb6bb4f5753b1a81`。
- 原v1/secure-v1八文件hash保持；TLS调查记录hash保持 `abd49c88a84a7460cfcab2a0d77d547e5bb991b69f2c1144ddcc535eb148e075`。

### A2a — RH-029 / 独立工作区与稳定转换

`IMPLEMENTED / VERIFIED_IN_REAL_BROWSER`：3314独立origin/业务IDB/运行目录；复用工作台adapter；单击星标CAS、脏正文保留、离线工作、正常关闭全部进程重开；稳定mapping/父链/prepare token及真实IDB abort。正式转换仅显式TEST ONLY授权夹具测试，普通入口没有此注入，真实owner pin/配对尚未实现。

最终 `final-context-identity` 共4项PASS（2项Node纯结构/规则测试，2项真实Chromium测试），11.02s、retries0。另无fixture普通构建入口 `normal-build-a2a` 1项PASS；星标额外字段拒绝且整个IDB snapshot不变定向1项PASS。真实Python workflow.validate_context 7个纯函数对照场景通过，不是Domain/PG端到端验收。原3A完整17项最终51.6s通过，证据 `storage/runtime/browser-sync-qa/a2/final-3a-regression/`；后续仅sync专属补丁未重复该回归。typecheck/build通过。

Windows / Chromium156.0.8078.4；普通构建 `549a40efe012b388`，最终TEST ONLY构建 `379833083b415b18`。实际页面：[桌面](evidence/sprint3b/a2a-desktop.png)、[390px移动视口](evidence/sprint3b/a2a-mobile-viewport.png)。图中故意触发另一tab更新后的CAS拒绝，未保存中文正文仍在；不是实体移动验收。

`NOT_IMPLEMENTED`：PC服务、真实配对/密钥/nonce/网络/接收冲突、3A救援导入。绑定内容预览只返回UNVERIFIED/BLOCKED，未建立信任。不支持的旧语境字段按冻结模块明确BLOCKED并保留，不隐式改快照或删除内容。

## 失败保留

本轮第一次Relay初始化使用PATH中的Anaconda Python，缺少psycopg；被既有就绪检查包装为QA_PG_UNAVAILABLE。独立诊断定位在驱动导入、未到SQL/TLS。保留首次输出及诊断；改用项目.venv后单次受guard数据库连接和--start通过，未改源码/超时/证书。证据 `storage/runtime/browser-sync-qa/init-attempt1-transcript.txt`、`init-failure-analysis.md`、`pg-diagnostic-venv.json`、`start-venv-attempt2.log`。

A1所有RED、错误解释器、受限临时目录、Node工作目录/导出/对象原型测试错误及明确修正后结果分别保留在 `storage/runtime/browser-sync-qa/protocol/`，不覆盖原失败，不以重跑关闭未知问题。

A2a独立复审修复了nil UUID、null principal与模块额外字段错误接受；保留审查转录、RED和修正后记录。最终规格与质量复审PASS。

## 当前 Gate

| Gate | 当前状态 |
|---|---|
| G1 项目与协议一致 | INCOMPLETE；仅版本契约已验证，同项目加入/操作映射尚在实施 |
| G2 浏览器安全接入 | NOT VERIFIED |
| G3 本地可靠性 | INCOMPLETE；3A回归通过不替代3B |
| G4 实际双向传输 | NOT VERIFIED |
| G5 冲突与幂等 | NOT VERIFIED |
| G6 人类体验与状态 | INCOMPLETE |
| G7 隔离与回归 | INCOMPLETE；A1回归已通过，后续改动待验收 |

仍在按A→B→C实施。最终A–P矩阵、实际截图、启动停止命令和最小往返步骤将在真实验收后补充；未进入Sprint3C，也未发布生产版本。
