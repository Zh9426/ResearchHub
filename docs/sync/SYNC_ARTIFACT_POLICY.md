# Artifact、Relay 保留与 Bootstrap

状态：**DECIDED**；合成 bytes 的同项目/epoch 去重及校验 **PROTOTYPED**，生产上传/retention/快照均 **NOT IMPLEMENTED**。

| policy | 同步元数据 | 同步 bytes | 推荐示例与含义 |
| --- | --- | --- | --- |
| local_only | 默认不离开本设备；分享需显式改变 policy | 禁止自动上传/按需远取 | 极敏感或严格本地记录；其他端最多知有未共享项目内容的统计 |
| metadata_only | 加密 eager metadata | 不上传 Relay | 大 MAT/NPY/NPZ、raw acoustic/imaging fields；Primary 持有 bytes |
| encrypted_sync | 加密 eager metadata | 显式批准的小文件、客户端先加密后暂存 | config.json/metrics.json/小 PNG；不是任意类型都可自动上云 |
| on_demand | 加密 eager metadata | 授权用户请求后从在线 origin/Relay 懒加载 | 大但偶尔需查看的派生文件；请求不更改 local_only |

每条 metadata 独立 UUID，带 run_id、文件名、size、SHA-256、category、origin_device UUID、policy、availability；文件名/原始 SHA 在密文内部。不同 Artifact metadata 即使 bytes 相同也保留各自 Run 和来源。Primary 记录 `AVAILABLE_ON_PRIMARY_PC` 是位置声明，不保证电脑在线或磁盘可靠。

例如 acoustic_field.mat，7.8 GB，metadata_only：手机只获得加密解密后的说明、checksum、size 和“文件在主电脑”，不触发自动下载。on_demand 只有明确请求/预算允许才传输；断点块需校验和最终完整 checksum。未来自动小文件阈值、移动流量/磁盘额度由用户批准，不能按扩展名绕过 size/敏感分类。

## 去重与校验

明文相同内容按 SHA-256 + size 校验；生产 blob address 拟用 project-scoped keyed digest（例如 HMAC），并按 key_epoch 隔离，避免公开跨项目内容探测。Artifact 随机 DEK 和 authenticated manifest 描述分块/顺序/长度/hash，chunk AEAD AAD 绑定项目、artifact、epoch、chunk index。元数据指向已校验 receipt 前不能称文件已同步。不能接受只匹配文件名或只看 Relay 返回 success。

同项目/同 epoch 的同 bytes 可以复用 blob，metadata ID 不折叠；跨项目/epoch 不复用。删除一个引用不能删除另一个 Artifact 的唯一 bytes。真实加密后的 dedup、防探测、refcount 与 rotation 迁移均待安全工程验证，原型明文 hashlib 不是证明。

## Relay retention

| 配置 | 约束 |
| --- | --- |
| retain_until_ack（默认推荐） | 所有所需活跃设备已 durable apply/retain ACK，Primary 已接收并有备份，才可清理暂存 |
| 7 days / 30 days | 是期望保存期限，未 ACK/唯一副本不自动硬删除；到期显示阻塞，人工撤销旧设备或延长 |
| metadata only | 不存 bytes；保留加密 metadata 日志/快照以供设备理解与恢复 |

Primary 已校验 bytes 并登记长期副本/备份后可删除 Relay ciphertext，其他设备以后从 Primary 按需取；UI 明示“需主电脑在线”，不能在离线时承诺下载。metadata/changelog 不能跟 bytes 一起删。Audit 完整历史由 Full Node 持久保存；密文快照包含去重与审计状态，压缩不能改变审计内容。

快照由有权完整节点生成，签名 manifest 绑定项目、snapshot cursor、heads/冲突、module_snapshot、tombstones、schema/key epoch 与完整性。Relay 不生成或解释科研快照。至少一份经验证快照与 490001+ tail 同时可取，才可压缩 490000 前日志；断电期间不得出现二者都不存在的窗口。恢复验证及密钥缺失都不能清空旧本地状态。

设备离线几个月可能 cursor 早于 floor：先保护/export 本地 pending，再 bootstrap；缺失 BASE 的离线编辑转人工候选。项目取消同步需处理未 ACK 队列、保留或显式安全清理缓存，不以 deselect 删除原科研对象。手机选择 ICE/HDSP metadata、平板选择更多项目，均采用每项目 cursor，metadata eager / binary lazy，不能用全局 cursor 跳过未选中流。

**OPEN QUESTION**：默认小文件阈值、Relay 预算、ACK 参与设备与离线 lease、快照周期/备份冗余、撤销时唯一副本检查。Sprint 0 不实际删除/上传任何个人文件。
