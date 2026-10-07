# Failure Mode Analysis

状态：**DECIDED** 为恢复规范。注明“原型”的机制仅在合成 SQLite 验证；真实网络、E2E、快照、撤销、移动端均未实现。

| 故障 | Detection | Recovery | Data-loss risk | User-facing behavior |
| --- | --- | --- | --- | --- |
| Push interrupted | 无 durable receipt；批次数量/digest 不完整 | 原 transaction ID 重试；staging 不可见（原型） | 未 ACK 本地队列须保留；仅 staging 不算保存 | 待发送、重试中，不全绿 |
| Pull interrupted | page 未完成/游标不连续 | 从持久 cursor 重拉完整批次 | 若提前 cursor 会丢；协议禁止 | 已接收数量/待拉取明确 |
| Duplicate Push | transaction/change ID 已有且 hash 相同 | 返回原 receipt，不新增 seq（原型） | 同 ID 异内容被拒，不能覆盖 | 已接收或身份冲突 |
| Duplicate Pull | inbox revision/batch 已存在 | 幂等应用，不多对象/Audit（原型） | 正确去重无损；键碰撞报错 | 接收进度不重复计数 |
| Client crash during apply | 未完成本地事务/故障注入 | domain/inbox/audit/cursor rollback 重拉（原型） | DB/磁盘损坏仍依赖备份 | 恢复后保持旧有效状态 |
| Relay crash | committed receipt 或仅 staging | ACID 恢复，客户端按 receipt ID 查询/重推 | 单磁盘且无副本不能保证 durable ACK；需部署冗余 | Relay 暂不可用，保留本地 |
| Clock skew | display time 与观测不一致 | DAG parents 判断因果，seq 传输；不按时间选值 | 只影响排序显示，不能改科研结论 | 时间异常标记 |
| Device offline for months | cursor 低于 compaction floor/成员过期 | 保护 pending、加密 snapshot + tail，missing BASE 人工审查 | 被驱逐的未 ACK 唯一数据可能丢，提前提醒/export | 要求恢复/配对，禁止重置本地 |
| Schema mismatch | Hello/decoder 不支持版本、字段/module hash | 只读或升级，持久 quarantine，不丢 raw envelope | 跳过未知事件会丢语义，协议禁止 | 项目需升级，cursor/applied 分开 |
| Missing Artifact | metadata receipt 指向 bytes 不存在 | 降级 ABSENT，向 origin/备份请求 | 唯一 origin 丢失则 bytes 不可恢复 | 文件位置/需电脑在线/已缺失 |
| Corrupt Artifact | AEAD tag/长度/manifest 失败 | 删除坏 cache 的引用状态，保留诊断，重取 verified 副本 | 唯一副本损坏可能永久丢失 | 明确损坏，不打开为科研输入 |
| Checksum mismatch | SHA-256/size 不符（原型） | 拒绝 READY，隔离并重传/查源 | 不接受未证实 bytes，元数据仍可保留 | 校验失败，不标“同步成功” |
| Revoked Device | membership_epoch/签名 grant 不合法 | 拒新 envelope，隔离旧 pending，人工导出审查/rotate keys | 旧端已读数据无法收回 | 设备撤销、待审查更改 |
| Wrong encryption key | AEAD decrypt/tag 失败 | 找正确 epoch/可信配对恢复；绝不明文 fallback | 所有 keys 丢失不可恢复 | 密钥缺失或消息损坏，非正常 schema 错 |
| Concurrent conflict resolution | expected_heads 已改变/多个 resolve heads | 保留全部解决候选，再次 Human 确认（原型） | 不覆盖任一依据，保留审计 | 冲突再次产生 |
| Module upgrade conflict | 项目 snapshot parents 分叉 | 项目暂停写入，人工选转换/目标 snapshot | 自动 registry 解释会毁语义，协议禁止 | 升级冲突、冻结定义可查看 |
| Trash vs edit | edit base 位于 trash 前且非因果后继 | 保存 restore candidate，Human 保持 trash 或显式恢复（原型） | 丢弃候选会丢编辑，禁止 | 垃圾箱冲突，无自动复活 |
| Restore vs purge | permanent tombstone/删除纪要 | 拒绝复活；有备份则人工恢复为新对象 | 无 bytes 备份不可恢复 | 已永久删除及可恢复来源 |
| Primary PC disk failure | DB/MinIO 校验、健康检查/读失败 | 从已验证 PG/MinIO 备份恢复，再 sync；Relay metadata 不能替代大文件备份 | local_only/metadata_only 唯一未备份 bytes 会丢 | 备份恢复入口，标记缺失文件 |
| Cloud relay unavailable | 超时/连接失败 | 继续本地允许操作，指数退避+手动重试，保留 outbox | 本地也坏且未 ACK/备份则丢失 | 离线状态与待同步计数 |
| Duplicate identity with changed payload | digest/change ID 碰撞 | 拒绝并记录诊断，不能改写历史（原型） | 蓄意混淆不能变 accepted | 消息身份错误 |
| Browser quota/eviction | quota exception/启动完整性检查 | 停写、同步或导出；重新 bootstrap 不能覆盖唯一 pending | 用户清除/驱逐会损失未同步数据 | 明确本机风险与最后成功 receipt |
| Partial snapshot/cursor gap | signed manifest/序列连续性失败 | 保留旧 store，重新下载缺段/快照 | 原子切换保证旧状态仍在，真实盘损另算 | 恢复未完成，不宣称已同步 |

## 恢复责任

Relay durable ACK 的部署承诺必须定义 fsync、事务、备份/副本与故障域；SQLite 事务故障注入仅验证进程/应用 rollback，不能证明掉电、硬件损坏或恶意 Relay 永不丢 ACK。Primary 保存完整业务与 bytes 并执行独立备份；浏览器本地存储不是备份。任何清理都需证明没有唯一未确认副本，失败时停止清理。

同步 conflict UI 必须展示 BASE、两个/多个候选、device/actor/source、模块与文件缺失状态，用户 action 再验证当前 heads。Error 与 activity 从安全的错误码派生，不写密钥/原始 payload 到 Relay logs。个人数据恢复流程沿用 v0.2 备份工具，不由此原型操作。
