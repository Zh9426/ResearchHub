# Sprint 3B 设计增量：受控双向元数据同步

2026-10-09；基线 `187fdfd10f34027882ed7c0f52f472b66e78295c`，工作树干净、远端相等，基线CI37872337842五job成功。main/v0.2.0保持4a4db4a。用户明确授权loopback QA，TLS-001 OPEN；不授权生产、公网或个人数据。

## 拓扑与信任

- 3A保留 `http://127.0.0.1:3313`、原IDB/profile/测试，不原地升级身份。
- 3B浏览器B使用 `http://127.0.0.1:3314`、`researchhub-browser-sync-qa-*` IDB、独立 `storage/runtime/browser-sync-qa/` profile/key库。入口显示“受控同步实验版 · 仅合成数据”。复用React展示组件/CSS与离线壳机制，不调用PC接口保存B记录。
- PC A的受限QA业务UI/API固定 `http://127.0.0.1:3315`，复用同一工作台视图的PC adapter；命令经QA Domain/Kernel/Outbox，读取经ResearchReadService区分工作副本、projection、candidate和历史。只使用现有guard验证的 `researchhub_sync_kernel_qa`，additive QA表，不改产品API/MCP读取。
- Relay仍为 `https://127.0.0.1:38001`，沿用原ingress与独立Relay PG；只转存密文/公共授权/签名回执。B直接fetch此固定URL，credentials=omit、redirect=error，无Node密码代理。
- 真实HTTPS首选一次性Linux测试用户的独立home/NSS/profile导入QA CA；通过新OS用户的实际home隔离，不重赋当前用户HOME或CODEX_HOME，也不改变个人Windows根库。Linux宿主/CI运行真实Chromium直达原loopback入口；若本地Windows无法隔离信任则Windows网络明确NOT VERIFIED。Docker容器网络namespace不能把宿主localhost当自身，也不能静默绕开ingress。必要不同拓扑须先补充ADR。

## A：项目加入、版本与因果

PC owner建立空合成项目，生成semantic/opaque ID、冻结module snapshot和规范digest、当前完整manifest链与独立pin roots。签名项目绑定含能力、principal映射；UI通过受信owner人工确认pin，不能从Relay自授权。浏览器生成自己的Ed25519/X25519密钥，沿原五分钟challenge/SAS、两私钥possession、owner消费、签名HPKE grant加入。仅加入当前epoch空基线，然后PC创建baseline让B真实拉取。非空旧历史需要可信bootstrap时明确BLOCKED，不跳cursor。

最小真实加入路径使用新的专用3B profile，不调用三项目演示seed；现有seed及pending完整保留，不按名字迁移或重分配UUID。空工作区完成独立设备生成、owner pin和配对后，加入PC指定semantic UUID与真实snapshot。vault先持久已验证grant/key，业务库再短事务写project、VERIFIED binding与join marker；中间状态显示加入未完成，同一receipt幂等补齐，不能提前发送。正常加入UI需要与本地演示初始化分开；若未来支持同profile多个同模块项目，必须先改为UUID或唯一alias路由，不能复用generic别名混淆身份。owner在成员加入后签目标设备专用binding，principal_map覆盖合法发送者；同设备actor身份不可因刷新静默改写。绑定按已pin的manifest/head单调CAS更新，旧转换与跨epoch pending保留，不自动换身份重签。此加入接口方案已只读复核，B阶段实现。

**RH040 AMENDED — 授权安装顺序。** 上述早期“vault先持久、业务后写”的顺序由统一协调器替代：事务外校验完整签名binding/chain，业务短事务先写BLOCKED、递增generation与固定transition token，再安装vault pin/grant，最后短CAS写READY绑定与公共授权镜像。业务镜像是接收/转换/发送提交时的授权门槛；不声称跨数据库原子性。中断仅允许恢复同一transition；完整相同receipt重试不增generation，缺镜像的旧绑定保持BLOCKED。正常join、链安装、撤销共用此路径，显式TEST_ONLY密码fixture与正常入口分开。PC命令与交接统一Trust→Project→Work锁序。测试范围见本轮报告。

B2采用文本复制的标准challenge/SAS/双私钥proof/HPKE grant；复用pairing.consume而非新造认证。PC受会话/Origin/CSRF限制的配对协调器持久journal：固定session/recipient双公钥/role/prefix/principal、旧head、exact challenge/receipt/candidate和phase。CHALLENGE_READY→SQLite OWNER_COMMITTED→HTTPS Relay membership确认→PG_COMMITTED（同事务Trust链、principal/map、journal）→B_INSTALLED；每步崩溃从同session已存receipt恢复，不能重新consume或生成grant。READY启动前先核验并恢复已有journal，不因任意SQLite新head自动覆盖PG；未知第三head或缺失journal BLOCKED。PC binding从已提交PG状态重构签名，不继续用启动时旧快照。

Relay bootstrap仅受控QA setup调用原pin_bootstrap；/v1/hello不是项目创建。发布采用原/v1/membership及/v1/membership/receipt，专用恢复helper仅允许journal已验证的旧/候选manifest签这些固定路径。ACK未知时先查candidate receipt，旧授权查询确认仍为old才重送exact candidate；网络错误不能推断已提交或未提交。此处有意不使用/v1/pairing/complete：现有接口在SQLite已consume但Relay未提交且五分钟过期时无法恢复，不能放宽过期规则。保留PcProjectBinding原wrapper；每个manifest head固定一份canonical principal_map，已有device→actor不改，若未来需同epoch修改map才另增版本链。B完成独立安装并真实HTTPS hello确认当前head/空sequence后，再创建baseline；本轮不支持任意历史初始化。

challenge准备必须先提交PG RESERVED journal的session/recipient/旧digest/issued_at，再由专用create-or-load helper按精确session读取或创建SQLite challenge；不改变原create_challenge默认随机API。SQLite写事务内再次查重和manifest CAS，并发输家返回赢家已提交字节，不换session。重入校验全部journal绑定，不重置attempts/used/expiry；已used按旧pin链校验后恢复原receipt，不能用已推进的current去误验旧challenge。未创建即过期不生成新challenge，必须显式新session。项目活动journal唯一约束及统一PG→SQLite锁序，不能仅依赖3315端口锁或扫描猜测pending。

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

B1已查阅[core浏览器用法](https://github.com/dajiaji/hpke-js/blob/main/packages/core/README.md)、[recipientKey参数](https://dajiaji.github.io/hpke-js/docs/interfaces/RecipientContextParams.html)和[支持环境](https://github.com/dajiaji/hpke-js#supported-environments)。本轮传完整原生CryptoKeyPair，库直接使用其publicKey，不要求从non-extractable私钥导出公钥。安装core1.9.0/common1.10.1；真实Chromium156.0.8078.4独立Python双向验证，库支持声明和Node通过均不替代浏览器证据。

authority永久唯一prefix + counterBE8；短IDB事务预约/镜像/准备token提交后加密，完整不可变envelope落盘后才发送。失败耗号；完整envelope已落盘只能exact retry。预约后但完整密封落盘前崩溃，恢复时先CAS替换准备token，再为同一不可变事务/message预约新nonce；旧计算token不得提交或发送，只能有一个最终持久envelope；缺失/损坏旧key或账本停写，保留业务内容；全部可信状态一致回滚不可检测，生产BLOCKED。

密钥解封的短暂raw阶段计算内部 `SHA256(key):prefix` 身份并与non-extractable CryptoKey持久绑定；相同key重新导入不能清零。key/nonce/token同vault IDB，业务mapping在另一IDB，明确不存在跨库原子事务。恢复顺序：业务先固化operation/tx/message/digest/prepareID；vault同prepareID预约nonce+token；密码运算后在同vault事务CAS token并永久写sealed完整bytes/digest，作为唯一密文提交点；业务再CAS复制对应sealed为ready。prepareID永久绑定业务身份、key fingerprint/prefix/epochs，不能重建。未seal崩溃可换token耗新nonce；已seal只能复制原字节；已ready只能相等幂等写，不一致则identity collision。发送只读ready并核对vaultsealed及当前trust/role/epoch；seal后信任变化保留密文BLOCKED，绝不自动reseal。任一库缺失/损坏均停写保留内容。此跨库顺序已独立设计复审PASS，尚待实现故障验收。

完整链另与持久pin的head epoch/digest核对，拒绝合法旧链截断或同epoch fork；checkpoint保留签名时历史creator公钥/epoch验证上下文，当前撤销不抹除历史验证依据。全profile可信状态一起回滚仍无法可靠检测。

B1永久prepare marker与预约行同时绑定身份、token、nonce、sealed状态及摘要；密封后清空其中一项被视为损坏，不重新加密。meta复合索引按key/prefix与nonce读取最高保留预约，在读取、预约、密封提交及READY检查counter不得低于该值；两本counter局部一致降低仍拒绝，不自动修复。使用一次反向索引cursor和一次预约读取，无全表扫描。旧缺索引或缺失vault明确BLOCKED，不迁移/克隆旧发送身份；本轮仅合成新profile。

验证完整pinned链、sender principal/role/epoch、signature/AEAD/canonical/digest/内部绑定。只开放Run/Note普通草稿，protected科学确认与模块升级无fresh Human grant拒绝。接收先事务外预验证，短事务CAS重验trust/head/token，再原子写修订/状态/receipt/cursor；整页失败不推进。

CORS精确允许 `http://127.0.0.1:3314`、GET/POST、`content-type,x-rh-proof`，不允许credentials；OPTIONS在proof之前处理，仅preflight响应，无业务读写或nonce消费。实际请求仍完整proof验证，错误响应也只向允许origin暴露。B的CSP固定 `connect-src 'self' https://127.0.0.1:38001`。

B2复核[Chromium Linux证书文档](https://chromium.googlesource.com/chromium/src/+/HEAD/docs/linux/cert_management.md)：M146起默认使用实际用户目录下 `.local/share/pki/nssdb`，已有旧 `.pki/nssdb` 时仍用旧库。本轮新OS用户显式创建新版NSS库，仅可信用户加入公开QA CA；通过sudo login选择真实账户，不改HOME。整个runner runtime设为0700，浏览器程序位于公共只读目录；browser用户不能读取PC/Relay运行配置。证书是否实际生效仍须通过真实Chromium正负例证明，静态脚本审查不计TLS通过。

Linux网络验收由CI runner启动原Relay、PC3315和静态3314；两个新OS用户分别运行可信CA和错误CA浏览器，使用各自实际home/NSS/profile，浏览器测试不启动PC或读取其配置/私钥。只复制公共ca.crt，不开放TLS目录、Relay state或env；源码/依赖/浏览器二进制仅rX，只有所选profile/results目录可写，必要时父目录仅增加专用用户traverse ACL，不整仓chown。独立网络lifecycle采用外部服务模式，原3A helper含义不改。CA/hostname负例使用真实浏览器顶层导航到原127入口或https://localhost:38001，断言HTTP之前明确CERT信任/名称错误；不受3314的connect-src影响，不新增诊断页或放宽CSP。不能把401、IPv6连接拒绝、超时或CORS失败当证书验证。报告区分导航证书负例与3314 fetch/preflight/proof正例，普通页面仍仅连接原127入口。验收后关闭实际Chromium进程并分别owned stop，失败证据保留；临时用户由一次性CI环境回收。此段为待实施harness方案，不是已执行证明。

## C：传输、冲突与真实状态

单次手动“立即同步”，持久claim/CAS防双tab并发，退出释放/恢复；无隐藏无限重试。固定集合→稳定转换→持久封装→browser fetch→RelayStored记录；未知ACK结果保留原envelope供下次显式重送。HTTP proof可更新，业务身份不可更新。

新增独立版本的device-signed应用回执，绑定项目、sender/target、原message/envelope/transaction digest、epochs与stage。应用回执只从durable接收结果产生，拒绝/隔离不签KERNEL_APPLIED；公共Relay只校验存取，不裁决科学结果；B验证目标签名后才显示PC已应用，冲突状态另列。旧v1 ACK不改义。

PeerApplyReceipt v1设计字段固定为version/opaque_project_id/sender_device_id/target_device_id/message_id/sequence/envelope_digest/semantic_transaction_digest/membership_epoch/key_epoch/manifest_digest/stage/state_at_commit/signature，签名域ResearchHub/PeerApplyReceipt/v1\0；stage复用KERNEL_APPLIED，state_at_commit仅ACCEPTED/CANDIDATE，描述历史提交事实而非当前科研状态。新POST/GET /v1/peer-receipts，旧ack不改；Relay以message+target为不可变身份，核对对应message全部绑定和当前目标签名，exact retry幂等。GET仅原sender/target授权读取。客户端先从durable Received+Kernel生成并持久缓存回执，后发送；QUARANTINED/异常不签。Browser按本地缓存envelope及等待的特定PC目标验证完整pin链/signature/epoch/digest，不接受其他成员代签。旧epoch回执只作历史确认、撤销后不升级当前状态；晚冲突后的UI读当前DAG，不把旧ACCEPTED回执当当前projection。此为DESIGNED ONLY，C阶段实现与测试。

B仅实现本轮Run/Note所需保守DAG/整批屏障，使用相同向量与Python Kernel差异验证；不移植完整产品内核。并发同BASE保留全部head，三方BASE/本地/远端按字段展示，用户选择/手填，expected_heads CAS拒绝过期解决。新resolution revision/audit，不改历史。普通冲突采用原offline_proposal语义：显示“冲突解决提案已同步，待人工批准”，始终CANDIDATE，不推进AcceptedProjection。发送/接收的受信QA策略仅对整个v2 Run/Note普通resolve事务选择该模式，检查结果/parents/当前heads均未protected、锁内expected_heads精确相等，不能由payload选权限；不修改原Kernel离线历史heads契约。禁止LWW，回显不创建新local operation。接收先完成principal与txid/raw/digest幂等识别，已应用相同事务直接返回持久结果，再对新resolve检查exact-head；否则自己的解决提案回显会被错误判stale。晚分叉递归使争议事务及Dependency后代成为CANDIDATE，按事务撤回整批AcceptedProjection，不能仅隐藏冲突对象。业务Kernel序列与Relay cursor分别持久，不合并为一个watermark。

浏览器DAG优先抽取sync-protocol纯record-kernel-core，独立对照Python相同v2 transcript；共享严格payload校验，不复制字段表。依次完成principal/幂等、冻结module、parent/change/audit身份、完整物化、权限、依赖、heads/common BASE、晚冲突整批/依赖撤回、状态/审计/序列。BASE是唯一最大共同祖先，不能按时间选；offline proposal永远CANDIDATE。页内先在staged snapshot顺序计算，末尾短IDB CAS一次提交；任一步失败无半页。接收的transaction当前state与初始receipt_state分开，旧ACCEPTED回执不能覆盖晚冲突后的CANDIDATE。差异向量覆盖到达顺序、同BASE、独立对象、缺parent/dependency、身份collision、批次+后继撤回、resolution重复回显/过期拒绝、页失败与预验证后CAS变化。

当前本地对象表只支持UUID单键；正式内核仍支持类型+UUID身份。同UUID多类型或与已有本地项目/类型冲突时，接收整页明确BLOCKED且不推进游标，不通过重分配ID或丢投影迁就本地模型。未来复合键支持需显式迁移设计。

已保存Run星标单击独立字段命令：读持久记录+CAS，只改显式星标字段，dirty正文保持；列表/详情/队列一致。正文/星标/对端状态的机器细节在诊断抽屉。

## Gate、失败与依据

A项目/版本/因果→B真实浏览器密码/TLS→C双向网络/冲突/故障，依次复审；安全前置失败对应Gate BLOCKED且总体INCOMPLETE，不明文替代。测试按附件A–P，retries0，真实PC UI和B UI编辑；逻辑PC停消费不等于宿主断电。保留TLS原测试/参数/失败/诊断，新的失败独立run/attempt归档。Relay DB/BYTEA/files/logs做正文与key marker扫描及正对照。精确实现SHA CI后报告STOP，不3C。

参考[IndexedDB事务](https://www.w3.org/TR/IndexedDB/)、[WebCrypto](https://www.w3.org/TR/webcrypto/)、[Fetch CORS](https://fetch.spec.whatwg.org/)；库官方支持与实测版本在B阶段补录。已读frontend-app-builder/ui-ux-pro-max，用户要求延续现有界面而非重新生成视觉方案；真实隔离profile要求优先于个人IAB默认。UX检索未找到精确冲突反馈匹配，采用现有错误保留/可见label/44px规范，不声称检索已证明该交互。
