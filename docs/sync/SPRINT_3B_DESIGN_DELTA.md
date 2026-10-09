# Sprint 3B 设计增量：受控双向元数据同步

2026-10-09；基线 `187fdfd10f34027882ed7c0f52f472b66e78295c`，工作树干净、远端相等，基线CI37872337842五job成功。main/v0.2.0保持4a4db4a。用户明确授权loopback QA，TLS-001 OPEN；不授权生产、公网或个人数据。

## 拓扑与信任

- 3A保留 `http://127.0.0.1:3313`、原IDB/profile/测试，不原地升级身份。
- 3B浏览器B使用 `http://127.0.0.1:3314`、`researchhub-browser-sync-qa-*` IDB、独立 `storage/runtime/browser-sync-qa/` profile/key库。入口显示“受控同步实验版 · 仅合成数据”。复用React展示组件/CSS与离线壳机制，不调用PC接口保存B记录。
- PC A的受限QA业务UI/API固定 `http://127.0.0.1:3315`，复用同一工作台视图的PC adapter；命令经QA Domain/Kernel/Outbox，读取经ResearchReadService区分工作副本、projection、candidate和历史。只使用现有guard验证的 `researchhub_sync_kernel_qa`，additive QA表，不改产品API/MCP读取。
- Relay仍为 `https://127.0.0.1:38001`，沿用原ingress与独立Relay PG；只转存密文/公共授权/签名回执。B直接fetch此固定URL，credentials=omit、redirect=error，无Node密码代理。
- 真实HTTPS首选一次性Linux测试用户的独立HOME/NSS/profile导入QA CA；不改变个人Windows根库。Linux宿主/CI运行真实Chromium直达原loopback入口；若本地Windows无法隔离信任则Windows网络明确NOT VERIFIED。Docker容器网络namespace不能把宿主localhost当自身，也不能静默绕开ingress。必要不同拓扑须先补充ADR。

## A：项目加入、版本与因果

PC owner建立空合成项目，生成semantic/opaque ID、冻结module snapshot和规范digest、当前完整manifest链与独立pin roots。签名项目绑定含能力、principal映射；UI通过受信owner人工确认pin，不能从Relay自授权。浏览器生成自己的Ed25519/X25519密钥，沿原五分钟challenge/SAS、两私钥possession、owner消费、签名HPKE grant加入。仅加入当前epoch空基线，然后PC创建baseline让B真实拉取。非空旧历史需要可信bootstrap时明确BLOCKED，不跳cursor。

显式协议组合 `(protocol_version=2,schema_version=2)` 只为本轮Run/Note扩展；v1=(1,1)白名单/bytes/revision不变，混合(2,1)/(1,2)仍拒绝。SecureEnvelope外壳版本/suite/domain仍1，事务(2,2)仅transaction记录可用，header与内部版本严格一致且签名/AAD覆盖。旧端拒绝新版本，不丢字段降级。

| 本地 | 正式映射/边界 |
|---|---|
| Run/id/project | ResearchRun，ID不变；module schema校验context_data/run_type |
| Note.body | Note.content，中文/空白原样 |
| title/objective/observation/status/scientific_outcome/context_data | 无损；unknown/空值不伪造 |
| is_highlighted/highlight_type/highlight_note | 仅v2显式精确类型支持，不作为Tag |
| local_edit_version/local_format_version | 本地CAS/格式，与wire版本和revision分离 |
| module_hash | 先验证实际snapshot，本地JSON序列化hash保留来源；另算规范module_snapshot_hash |
| source/workspace/device | 来源映射独立存储；网络actor由已授权principal绑定，不信旧救援source |

每条local operation保留不变；独立mapping存tx/change/audit/object IDs、parents/deps、revision/digest、adapter版本、message/envelope与状态。稳定身份在准备时持久化；create后连续update/highlight接前一正式revision。已密封后编辑仅新增后继。已接收基线、未发后继、dirty表单分开；pull不覆盖后两者。旧3A包显式预览导入，不克隆身份/nonce；不支持字段给字段级BLOCKED原因。

## B：浏览器密码与权限

保持AES256GCM/Ed25519/HPKE-X25519-HKDFSHA256-AES256GCM。纯canonical/protocol可复用；现有Node fs/sqlite/Buffer包装不能进入bundle。浏览器原生WebCrypto生成non-extractable设备CryptoKeyPair，@hpke/core固定1.9.0只处理标准HPKE。若库默认extractable，显式传原生pair适配且真实验证；unwrap项目key短暂内存后导入non-extractable AES key，单独IDB持久，不入救援/日志。

authority永久唯一prefix + counterBE8；短IDB事务预约/镜像/准备token提交后加密，完整不可变envelope落盘后才发送。失败耗号；完整envelope已落盘只能exact retry。预约后但完整密封落盘前崩溃，恢复时先CAS替换准备token，再为同一不可变事务/message预约新nonce；旧计算token不得提交或发送，只能有一个最终持久envelope；缺失/损坏旧key或账本停写，保留业务内容；全部可信状态一致回滚不可检测，生产BLOCKED。

密钥解封的短暂raw阶段计算内部 `SHA256(key):prefix` 身份并与non-extractable CryptoKey持久绑定；相同key重新导入不能清零。key/nonce/token同vault IDB，业务mapping在另一IDB，明确不存在跨库原子事务。恢复顺序：业务先固化operation/tx/message/digest/prepareID；vault同prepareID预约nonce+token；密码运算后在同vault事务CAS token并永久写sealed完整bytes/digest，作为唯一密文提交点；业务再CAS复制对应sealed为ready。prepareID永久绑定业务身份、key fingerprint/prefix/epochs，不能重建。未seal崩溃可换token耗新nonce；已seal只能复制原字节；已ready只能相等幂等写，不一致则identity collision。发送只读ready并核对vaultsealed及当前trust/role/epoch；seal后信任变化保留密文BLOCKED，绝不自动reseal。任一库缺失/损坏均停写保留内容。此跨库顺序已独立设计复审PASS，尚待实现故障验收。

完整链另与持久pin的head epoch/digest核对，拒绝合法旧链截断或同epoch fork；checkpoint保留签名时历史creator公钥/epoch验证上下文，当前撤销不抹除历史验证依据。全profile可信状态一起回滚仍无法可靠检测。

验证完整pinned链、sender principal/role/epoch、signature/AEAD/canonical/digest/内部绑定。只开放Run/Note普通草稿，protected科学确认与模块升级无fresh Human grant拒绝。接收先事务外预验证，短事务CAS重验trust/head/token，再原子写修订/状态/receipt/cursor；整页失败不推进。

CORS精确允许 `http://127.0.0.1:3314`、GET/POST、`content-type,x-rh-proof`，不允许credentials；OPTIONS在proof之前处理，仅preflight响应，无业务读写或nonce消费。实际请求仍完整proof验证，错误响应也只向允许origin暴露。B的CSP固定 `connect-src 'self' https://127.0.0.1:38001`。

## C：传输、冲突与真实状态

单次手动“立即同步”，持久claim/CAS防双tab并发，退出释放/恢复；无隐藏无限重试。固定集合→稳定转换→持久封装→browser fetch→RelayStored记录；未知ACK结果保留原envelope供下次显式重送。HTTP proof可更新，业务身份不可更新。

新增独立版本的device-signed应用回执，绑定项目、sender/target、原message/envelope/transaction digest、epochs与stage。应用回执只从durable接收结果产生，拒绝/隔离不签KERNEL_APPLIED；公共Relay只校验存取，不裁决科学结果；B验证目标签名后才显示PC已应用，冲突状态另列。旧v1 ACK不改义。

B仅实现本轮Run/Note所需保守DAG/整批屏障，使用相同向量与Python Kernel差异验证；不移植完整产品内核。并发同BASE保留全部head，三方BASE/本地/远端按字段展示，用户选择/手填，expected_heads CAS拒绝过期解决。新resolution revision/audit，不改历史。普通冲突采用原offline_proposal语义：显示“冲突解决提案已同步，待人工批准”，始终CANDIDATE，不推进AcceptedProjection。发送/接收的受信QA策略仅对整个v2 Run/Note普通resolve事务选择该模式，检查结果/parents/当前heads均未protected、锁内expected_heads精确相等，不能由payload选权限；不修改原Kernel离线历史heads契约。禁止LWW，回显不创建新local operation。接收先完成principal与txid/raw/digest幂等识别，已应用相同事务直接返回持久结果，再对新resolve检查exact-head；否则自己的解决提案回显会被错误判stale。晚分叉递归使争议事务及Dependency后代成为CANDIDATE，按事务撤回整批AcceptedProjection，不能仅隐藏冲突对象。业务Kernel序列与Relay cursor分别持久，不合并为一个watermark。

浏览器DAG优先抽取sync-protocol纯record-kernel-core，独立对照Python相同v2 transcript；共享严格payload校验，不复制字段表。依次完成principal/幂等、冻结module、parent/change/audit身份、完整物化、权限、依赖、heads/common BASE、晚冲突整批/依赖撤回、状态/审计/序列。BASE是唯一最大共同祖先，不能按时间选；offline proposal永远CANDIDATE。页内先在staged snapshot顺序计算，末尾短IDB CAS一次提交；任一步失败无半页。接收的transaction当前state与初始receipt_state分开，旧ACCEPTED回执不能覆盖晚冲突后的CANDIDATE。差异向量覆盖到达顺序、同BASE、独立对象、缺parent/dependency、身份collision、批次+后继撤回、resolution重复回显/过期拒绝、页失败与预验证后CAS变化。

已保存Run星标单击独立字段命令：读持久记录+CAS，只改显式星标字段，dirty正文保持；列表/详情/队列一致。正文/星标/对端状态的机器细节在诊断抽屉。

## Gate、失败与依据

A项目/版本/因果→B真实浏览器密码/TLS→C双向网络/冲突/故障，依次复审；安全前置失败对应Gate BLOCKED且总体INCOMPLETE，不明文替代。测试按附件A–P，retries0，真实PC UI和B UI编辑；逻辑PC停消费不等于宿主断电。保留TLS原测试/参数/失败/诊断，新的失败独立run/attempt归档。Relay DB/BYTEA/files/logs做正文与key marker扫描及正对照。精确实现SHA CI后报告STOP，不3C。

参考[IndexedDB事务](https://www.w3.org/TR/IndexedDB/)、[WebCrypto](https://www.w3.org/TR/webcrypto/)、[Fetch CORS](https://fetch.spec.whatwg.org/)；库官方支持与实测版本在B阶段补录。已读frontend-app-builder/ui-ux-pro-max，用户要求延续现有界面而非重新生成视觉方案；真实隔离profile要求优先于个人IAB默认。UX检索未找到精确冲突反馈匹配，采用现有错误保留/可见label/44px规范，不声称检索已证明该交互。
