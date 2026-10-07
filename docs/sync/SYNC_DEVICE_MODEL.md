# 设备、移动存储与本机 Domain Layer

状态：**DECIDED** 为推荐；合成 UUID/SQLite 本地状态 **PROTOTYPED**。手机/平板 PWA 引擎、PC Sync Domain Layer 和系统 vault **NOT IMPLEMENTED**。

## 设备模型

设备 UUID 首次在本地生成后持久保存，恢复已有设备状态不重新分配；hostname/device_name 可变，不能用它当唯一 ID。设备 role 为 FULL_PRIMARY / LOCAL_CLIENT；只有存储与备份职责不同。每个选中项目保存 cursor、applied watermark、last_successful_sync、pending count、outbox、inbox、domain state、audit、conflicts、snapshot anchor、artifact cache index。项目级 device membership/epoch 控制选择和访问。

当前研究电脑保持 PostgreSQL/MinIO/Codex；不替换数据层，也不把数据库文件拷到手机。未来 PC 服务层需要 domain + changelog + audit 的同一事务边界、只读取 Outbox 的 worker 和批次 inbox。依据 [PostgreSQL 事务内 trigger 文档](https://www.postgresql.org/docs/current/sql-createtrigger.html) 可分析约束与原子边界，但不推荐从任意 row trigger 反推科研语义；从当前 Domain service 显式产生业务事件更清楚。

## 移动存储比较与推荐

| 技术 | 合适对象 | 限制与结论 |
| --- | --- | --- |
| IndexedDB | 结构化 metadata、revision、outbox/inbox、Audit/cursors/conflicts | 同库事务可保持 apply 原子性；推荐核心元数据存储 |
| OPFS | origin 私有文件与加密 Artifact cache | 适合 staged bytes/流式操作；与 IndexedDB 无跨库共同事务，推荐可恢复 cache |
| Cache Storage | PWA app shell/静态资源 | Request/Response 缓存，不承担 domain log/主文件库；不默认缓存登录 API 研究正文 |
| localStorage | 极少量非敏感 UI 设置 | 同步字符串、无事务结构，不存科研状态/密钥/待发队列 |
| 浏览器 PostgreSQL | 不采用 | 不移植 PC 数据库，不同步物理数据库文件 |

依据 [IndexedDB](https://developer.mozilla.org/en-US/docs/Web/API/IndexedDB_API)、[OPFS](https://developer.mozilla.org/en-US/docs/Web/API/File_System_API/Origin_private_file_system) 与 [浏览器配额/驱逐](https://developer.mozilla.org/en-US/docs/Web/API/Storage_API/Storage_quotas_and_eviction_criteria) 官方文档，浏览器存储存在配额、用户清除和默认 best-effort 驱逐。`persist()` 是请求，不保证所有设备批准。PWA 安装不等于数据永久保存。

元数据与 pending queue 必须在同一 IndexedDB 事务完成；quota 错误停止新写入，提示导出加密 rescue bundle/同步，不能显示“已保存”后丢记录。未 ACK changes 不纳入自动 cache 淘汰。OPFS 先写临时加密文件、校验后提交 DB manifest，异常只留下可清理 orphan，不能提交假 ready。原始 7.8 GB MAT 不自动进手机缓存；大文件下载需预算及用户意图。

## Keys 与平台限制

Device/project keys 拟由 [Web Crypto](https://developer.mozilla.org/en-US/docs/Web/API/Web_Crypto_API) 支持的 CryptoKey/vault 承载，优先 non-extractable device key + 加密 vault，unlock/user-presence 设计单独审核。non-extractable 不阻止同 origin 恶意脚本调用 key；需 secure origin、CSP、依赖控制、会话锁定及 XSS 防护。手机丢失和清理网站数据仍可毁掉唯一未同步内容/keys，必须明确告知恢复途径。Safari/iOS/Android 实机持久化、OPFS、CryptoKey 保存与后台限制仍未验收，不宣称所有平台一致。

浏览器后台任务和锁屏不保证持续运行；Sprint 1 首先设计前台手动同步和可恢复队列，后台 sync 属于后续，不使科研保存依赖 service worker 被唤醒。hide_before、filters、文件缓存预算暂时 device-local；未来用户若选择跨端偏好需独立 preference revision，不修改 Audit。

## 选择/撤销与迁移

选择项目后 bootstrap metadata，再 lazy bytes；撤选先提示未 ACK 更改和缓存保留策略，不删除项目。设备重装作为新 UUID，凭 trusted pairing 重新加入；旧设备被撤销而不是使用相同 hostname 自动冒充。client schema 更新只在本地 store 迁移并备份 pending，不能修改冻结 module_snapshot；未知 project schema 只读或要求升级。
