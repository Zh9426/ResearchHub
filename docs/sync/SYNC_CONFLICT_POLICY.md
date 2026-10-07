# Research Hub 冲突矩阵与人工权限

状态：**DECIDED**（推荐）。一般科学值和生命周期分叉 **PROTOTYPED**；三方文本、OR-set、模块升级、真实权限及生产 Resolver **NOT IMPLEMENTED**。

## 判定顺序

先验证成员/签名/schema/项目/module binding、Actor 权限和业务约束，再判定 DAG 因果。重复 revision 不变；因果后继按业务规则应用；同一 object 多头保留全部，建立 SyncConflict。安全合并只限明确白名单，未知类型必须隔离。时间戳、Relay seq、Primary、AI 置信度均不参与科学值裁决。

| 现有对象/字段 | 自动合并范围 | 必须人工解决/拒绝的条件 |
| --- | --- | --- |
| Project metadata | 新 UUID 项目共存；非科学 description 可提供三方建议 | 同字段并发、项目状态、冻结模块绑定、权限更改 |
| ResearchRun | 不同 UUID/Child Run 共存，保留同一个 parent；不同 Artifact additions 有条件 union | 同 Run 科学字段、parent/来源、human_conclusion、生命周期分叉 |
| Parameter | 无自动科学字段合并；独立对象共存仍校验参数键唯一语义 | 同 base 改不同值/单位/来源；同 Run 参数键碰撞 |
| Metric | 新指标对象共存但检查业务键/来源 | 数值、单位、计算方式、validated 状态并发；不能按置信度选值 |
| Artifact metadata | 不同 UUID additions + 合法同项目 Run 可 union；bytes 单独去重 | 同 metadata 名称/归属/政策改变、checksum/size 矛盾、父 Run trash |
| Note | 不同 Note UUID 共存；普通正文可提供非重叠三方 merge 建议 | 重叠段落、关联变更、缺 BASE、任何 Human conclusion 内容 |
| Task | 不同 UUID Task 共存；独立集合 additions | 同状态、完成标记、关联及相互依赖并发，不擅自宣布完成 |
| Evidence | 独立合法 evidence additions 共存 | status、证明/反证关系、证据来源、validated 并发；仅 Human 确认 |
| Claim | 独立 UUID 保留 | 科研断言、支持状态、Evidence link 分叉；不可由 AI 自我批准 |
| Decision | 保留不同候选/草稿 | 内容/accepted 状态并发，必须 Human 选择或重新写结论 |
| Gate | 无自动 passed/failed 合并 | 状态、依赖、证据并发；人工门槛重新验证 |
| GateCriterion | 独立新 criterion 草稿仍检查定义 | 阈值/单位/通过条件/删除并发；不能自动放宽 |
| Tag set | 设计为 observed-remove set：add 带 UUID token，remove 只消费已观察 token | 名称/对象归属修改、未见 add 的 remove 不可删除它；不是时间戳 LWW |
| 关系集合 | 不同 link token 条件 union | 跨项目、类型/生命周期不合法、循环 lineage、key 冲突、Evidence 验证依赖必须拒绝或人工 |
| AuditLog | 按 audit_id 追加、同内容去重，不覆盖 | 同 ID 异内容报身份冲突；不能编辑或删除历史 |
| Activity | 根据验证过的事件重建，event ID 去重 | 不把 UI 顺序变成因果，不传播设备 hide_before/filter |
| Module version registry | 明确签名/摘要的不可变版本可共存 | 同版本号不同定义拒绝，不从本地 registry 覆盖项目 |
| Module snapshot | 冻结内容/hash 保留，不自动 merge | 两个升级事件分叉、旧版本客户端无法解释、snapshot 内容变更 |
| Archive | 因果 archive 保留读取限制 | archive 与科学 update 并发需候选审查，不利用 metadata update 改 active |
| Trash/Restore | 唯一因果、显式 restore 可经权限验证 | trash 对离线 edit、restore 对新 trash/永久删除均不得自动复活 |
| Purge | 不参与普通自动同步 | 普通设备/AI purge 一律拒绝；专门人工流程见下文 |

“独立对象共存”不是同一科学键可重复或同一对象任意字段 merge。比如两个新 Parameter UUID 都叫 pressure，仍需业务唯一性审查；两个 Artifact UUID 引用同一文件可分别保留说明与来源，bytes 去重不能删掉上下文。

## 三方文本评估

对普通 Note/Description/Observation 使用 BASE、LOCAL、REMOTE 计算非重叠文本修改建议，保留修改来源。纯文本段落不重叠也可能语义矛盾，Sprint 1 首版推荐显示 preview 并 Human 确认；未来自动范围需单独批准。重叠行/句、附件引用变化或缺 BASE 直接冲突。不直接执行 Git merge 去理解科研记录。Human Conclusion 即使文本能合并也必须人工确认；AI 只能建议，不能替人接受。

## 例子与解决

pressure BASE=1.4 MPa，A=1.6、B=1.8：两边收到相同 heads 后显示 BASE=1.4 与两个候选，不标任一为最新已确认值。Human 可选择 A/B，或写 1.7 并说明依据；新 revision 消费**完整** expected_heads，Audit action 为 resolve_sync_conflict。新的并发变化或同时两次解决会再分叉。UI 禁止一键静默保留电脑版本。

Run #043、#044 分别基于 Run #042 创建，保留两个 Child Run；不同 parameter exploration 是研究分支。它们的 parent ID、来源、module_snapshot 必须完整，不把数据摊平为最后一行。

## 生命周期与冻结模块

保留现有 archive/trash/restore/30-day retention 的语义，但 **30 天经过不等于可以永久删除**。trash 与旧 base 离线 edit：保存 edit 为 restore candidate，显示垃圾箱冲突，常规视图维持不可用；需要 Human 明确选择保持 trash 或 restore + 应用候选。不能自动 reject 后丢掉编辑。

Purge 设计要求 Primary、Human fresh confirmation、所有相关活跃设备 durable ACK/无 pending 编辑或显式撤销、保留窗口和备份检查。确认包含 object/head set 与相关设备列表；存在未知设备状态不得 purge。永久 tombstone/删除纪要保留以拒绝旧 revision 复活，purged bytes 只有外部备份才能恢复；restore vs purge 必须提示不可恢复或人工从备份复制为新对象。本轮无此实现。

Module upgrade 是有权限的独立业务批次：消费项目版本，携带原 snapshot hash、目标完整 snapshot、显式转换及 Human 审计。项目 UI 始终解释冻结 snapshot，新客户端不自动套新版 registry。并发升级/不兼容 schema 阻断写入并人工评审；旧 schema 写入保留候选，不能偷偷重新解释。

## Human 与 AI 边界

actor_type 来自受验证的身份上下文，不能相信 payload 的自称或设备签名就等于 Human。科学确认（Human Conclusion accepted、Evidence validated、Decision accepted、Gate passed、criterion/module upgrade）需要绑定具体对象/字段/完整 heads 的 Human 授权和审计；拟采用可信客户端 fresh user-presence，具体离线授权机制仍 **OPEN QUESTION**。离线草稿允许，不承诺离线最终确认。AI 入口只能原有允许的 proposal 字段；Sync、Relay、Remote MCP 不提供额外权限。

SyncConflict：合法 revision 分叉；AIReview：proposal 来源需要人看。解决前者不自动批准后者，批准 AI proposal 不自动消除未包含的冲突。
