# SyncTransaction 与 QA Domain 边界

Sprint1采用独立QA schema/metadata，未部署生产同步。实际验收结果与限制见 [SPRINT_1_REPORT.md](SPRINT_1_REPORT.md)。

## 一个科研操作，一个批次

创建Run、6个Parameter、3个Metric及2份Artifact metadata可以组成一个12-change SyncTransaction；对象UUID预分配或由已有Domain service分配后，在提交前组成wire。large bytes不在该DB事务中。所有成员必须同project/device/actor/schema，changes业务顺序与ordered_change_ids一致。

Outbox路径：取得Kernel项目锁 → 已有v0.2项目锁 → `service.create_record`创建Domain及Audit（只有flush）→ 创建pending Artifact metadata/Audit → `apply_in_session(local_outbox=True)` → 同一Session提交。任一步异常，Domain、原Audit、revision、projection、Kernel Audit、Outbox、Inbox和cursor一并回滚。该adapter不被生产main导入，也没有生产HTTP入口。

Incoming路径：校验envelope和注册principal → 协议/冻结module/业务/父引用/人工grant → revision及heads → conflict及整批屏障 → accepted projection → Audit → Inbox receipt → received cursor/accepted watermark，全程同一PostgreSQL事务。

Domain adapter 在分配业务 UUID 前深拷贝原始命令，以 RH-C14N-1 计算 action_digest；Outbox 同事务保存这个不可变指纹。重复 transaction_id 必须同项目与同操作内容，不能换 Run/Parameters/Metrics/Artifacts 后仍返回旧回执。指纹不进入跨设备 wire。

锁顺序固定为Kernel Project → v0.2 Project → Run/Resource；所有同项目Kernel apply/resolve在数据库项目行锁下串行化，等待后刷新对象状态。不同项目无全局应用锁。并发证明必须用真实独立数据库连接与可观察等待，不能依赖Python mutex。

## 不可变历史与科研可见性

revision保存所属transaction与materialized candidate，heads单独索引。create无父，ordinary update一个父，resolve当前完整expected_heads；parent必须同project/object/type且已存在。已存在revision不能修改，合法新增只引用之前存在的父，所以拓扑插入与不可变约束共同防止DAG循环。缺失BASE拒绝并保留发送方待重试；不得拿当前值冒充BASE。

对象多head使所有涉及transaction成为CANDIDATE，撤回这些批次的全部accepted projection；原revision/Audit不删除。最小依赖包括显式transaction dependencies、parent revision来源及Run所属关系。失效沿依赖图递归传播；独立事务继续accepted。

关系检查还覆盖 Evidence/Artifact 引用与 Gate 内嵌 criteria 的 evidence_ids。物化 document 在继承父值/类型并应用 patch 后重新校验，禁止合法 patch 组合出非法科研值。

在线人工review必须覆盖被解决候选批次全部对象；非冲突成员也显式review并产生新revision，不能把未审成员自动批准。已暂停依赖需要新批次明确review/rebase；resolution不是自动追认旧科学来源。离线resolution仅proposal，两个proposal可留下RA/RB新heads；在线final仍需fresh人工grant。

## 精度与现有Domain映射

wire decimal保留`"1.600"`。v0.2 Parameter没有decimal枚举，QA adapter使用已有object JSON载体`{"value_type":"decimal","value":"1.600"}`，Domain列value_type记object；Outbox保留原decimal wire。Metric现有输入允许string，因此保存原decimal字符串，wire另保留value_type。不转float、不伪装已完成生产数值schema/UI迁移。

QA Domain记录验证真实已有service的事务组合；accepted科学视图由Kernel projection读取。迟到失效撤回Kernel视图，原Domain local-origin记录与Audit仍作保存来源，不称生产v0.2查询已接入同步屏障。未来接入现有API时须审查统一accepted查询hook，不能直接使用旧行作同步winner。

两份Artifact元数据各自拥有UUID；QA pending object_key只作合成占位，不声称MinIO存在bytes。verified_reference必须经同project/key_epoch/checksum/size的合成校验receipt。所有云传输、AEAD、OPFS均未实现。

## QA schema review、备份与撤回

运行`python scripts/sync-qa.py --init`只创建/启动带`researchhub.qa.scope=sync-kernel-s1`标签的loopback容器。`qa_engine()`要求显式HUB_SYNC_QA=1、精确数据库/角色及loopback地址，并再次检查服务端身份；不读取或回退产品DATABASE_URL。

schema通过显式QA initialize创建，生产Alembic 0001–0005不变。部署审查应核对新增表/索引/FK/append-only trigger、依赖与锁顺序；在生产批准前不得执行QA initializer到个人库。

若需要保留QA结果，先对`researchhub-sync-s1-pg`执行pg_dump（输出只放被忽略storage/backups），记录版本与校验值，再停止该明确命名容器。撤回方式为停止独立QA入口、保留或人工移除独立容器；不修改个人库，也不以删历史行实现回滚。生产迁移、备份恢复与协议压缩需未来单独审查，本Sprint未执行。
