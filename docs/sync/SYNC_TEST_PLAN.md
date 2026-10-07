# Sprint 0 一致性验收与正式不变量

状态：**DECIDED** 是规范；**PROTOTYPED** 是合成测试覆盖，不是生产验收。实际计数与命令见 [SPRINT_0_REPORT.md](SPRINT_0_REPORT.md)。

## Formal invariants

定义 E 为已通过身份/业务验证的 accepted 变化，T 为 committed 批次，Apply(D,t) 为设备 D 原子处理 t，Heads(o) 为对象 o 未被后继消费的 revision 集合。ACK 分 transport 与 domain，不含静默内容删除许可。

| 编号 | 不变量 | 检验方式/本轮边界 |
| --- | --- | --- |
| I01 | accepted(c) ⇒ 保留 c 的可恢复 revision/Audit 或经明确批准、可追踪的压缩快照；不得静默丢失 | 批次/恢复原型；跨故障域 durability 尚未证明 |
| I02 | Apply(Apply(D,t),t) = Apply(D,t)，对象、审计、游标相同 | duplicate pull/push 原型 |
| I03 | 同 BASE 的不同科学更新 ⇒ 所有非因果 heads 保留，不能自动单值覆盖 | pressure 1.6/1.8 与人工结论原型 |
| I04 | Audit ID 的内容不可更新/删除；相同 ID 异内容必须拒绝 | audit 去重/identity 测试；真实不可删数据库约束未来做 |
| I05 | verified(bytes) ⇒ sha256/size/manifest 均符合；失败不能 success | synthetic checksum 与 context dedup 原型；AEAD 未实现 |
| I06 | trash/edit 不自动 restore；purge 不通过普通 ChangeSet | 原型 lifecycle 负向测试；生产 purge 未实现 |
| I07 | project.module_snapshot 不随本地 registry 改变；解释绑定 hash | 设计及将来 module fixture，原型不证明真实模块 UI |
| I08 | Human-only accepted mutation ⇒ 可信 Human grant 绑定该 heads/operation | 合成 AI 拒绝测试只验证规则；真实 consent/signature 未实现 |
| I09 | Cloud/AI entry 的有效权限 ≤ 原 Domain AI scope；不得冒充 Human | 设计 + synthetic principal，真实 Remote MCP 未实现 |
| I10 | outcome 不依赖 Primary role 或 wall-clock 选胜者 | head-set 推导/双副本并发测试；没有生产 Primary 服务 |
| I11 | T 的所有 ChangeSet 可见性为全有/全无；无半个 Run/参数视图 | push-half/pull-crash 原型；业务 conflict 全批次待审查策略见实现说明 |
| I12 | cursor advance ⇒ 批次 inbox、结果/candidate/quarantine 与 Audit 已持久完成 | apply rollback 原型，不能跳未知依赖 |
| I13 | 同 transaction/change ID 不同 digest ⇒ reject，不改变历史/seq | 碰撞负向测试 |
| I14 | object UUID、revision 和 parents 绑定同 project/type；跨项目依赖不可用 | 类型/项目负向用例或代码复审，未声称完整生产 referential integrity |
| I15 | bytes dedup 仅 project/key epoch 内；不同 metadata ID/来源均保留 | same SHA/context 测试 |
| I16 | unresolved heads > 1 ⇒ conflict；resolution 消费指定完整 heads，新的解决分叉仍保留 | concurrent resolution 原型 |
| I17 | bootstrap 不覆写未 ACK local changes；log compaction 有验证快照与 tail | 设计；bootstrap/compaction 未实现 |
| I18 | Relay 无 plaintext project key，错误 key/nonce/signature 不能入 Domain | 设计；本原型无加密，不能宣称此项被运行证明 |

## 用户要求的十个核心案例

| CASE | 合成动作 | 必须观察的结果 |
| --- | --- | --- |
| 1 | A offline create Run，再 push，B pull | 同 UUID 的同业务 Run 出现 |
| 2 | A/B 各自离线新建不同 UUID Run | 两个都存活，合法分支不混成冲突 |
| 3 | 共同 pressure=1.4，A→1.6，B→1.8 | 两候选/head 保留，BASE 可查看，无 LWW |
| 4 | 同 transaction 重复 push | 原 receipt/seq，日志无新增 |
| 5 | 同页/批次重复 pull | 无多余对象、Audit 与 cursor 变化 |
| 6 | 多 ChangeSet push 一半故障，再 retry | 半批不可见，重试完整一次提交 |
| 7 | 同项目/epoch 相同 SHA 的两个 Artifact | metadata 分别保留，bytes 一份；其他 project/epoch 独立 |
| 8 | trash 与旧 BASE 离线 edit | 保留 edit candidate、不自动复活 |
| 9 | 同时编辑 Human Conclusion | 不自动文本合并/不选 latest |
| 10 | A/B 各自 Audit 后重复收发 | 两事件均存在、无重复 |

补充负向：identity collision、未知 schema/type、missing/wrong BASE、项目/设备越权、AI 人工字段、purge、checksum、客户端 apply 故障、并发解决、设备/队列重启持久性。测试命名映射实际测试文件，覆盖缺口须写报告；禁止用“18 不变量全部证明”代替逐项边界。

## 执行与 TDD

```powershell
.\.venv\Scripts\python.exe -m pytest tests/sync_prototype -q
.\.venv\Scripts\python.exe -m ruff check prototypes/sync_sprint0 tests/sync_prototype
.\.venv\Scripts\python.exe -m prototypes.sync_sprint0.demo
```

原型只用 tmp_path/TemporaryDirectory、合成标记和标准库 SQLite。先写失败用例、观察 RED 后实现，再运行全部 GREEN；具体失败/通过记录由本次实际工具结果写入报告。SQLite 原子性依据 [官方事务文档](https://www.sqlite.org/lang_transaction.html)，但进程故障注入不等于断电/磁盘故障/多节点耐久性验收。

Sprint 0 不重复将原型结果充当 PostgreSQL、MinIO、PWA、签名或真实账户测试。v0.2 真服务重新验收见 [RELEASE_V0.2.0.md](../RELEASE_V0.2.0.md)；本分支应以 git diff 确认 apps/infrastructure/migrations 不变。既有 GitHub CI 仍测稳定应用，未自动纳入原型测试，需单独报告本地原型命令。

Sprint 1（仅提议，未启动）：跨语言 protocol fixture、Domain 权限/事务与 outbox 的独立 QA 验证、故障注入扩大；待人工批准后才选实际网络/密钥实现，真实浏览器清理、长期离线、E2E 和备份恢复必须分别验收。
