# Node → Browser 适配与字段边界

2026-10-09基线核查及Task4实现核对。真实浏览器结果见SPRINT_3A_REPORT；下表的生产阻塞不因探针通过而解除。

## 平台依赖

| 现有位置 | Node依赖/可复用部分 | Sprint3A适配边界 |
|---|---|---|
| sync-protocol/src/canonical.ts | node:crypto createHash；纯逻辑已移至canonical-core.ts | Node同步digest保留；browser.ts异步WebCrypto SHA256，原bytes/hash不变 |
| sync-protocol/src/protocol.ts | Node digest包装；exact schema已移至protocol-core.ts | Node/browser分别提供同步/异步revision与transactionDigest；payloadFields未放宽 |
| secure-sync/src/crypto.ts | node:crypto、Buffer DER、@hpke/core | 不打入正式本地记录UI；独立WebCrypto能力探针，不宣称完整HPKE适配完成 |
| secure-sync/src/envelope.ts | createHash、Buffer、NonceVault | 本轮不生成可向Relay发送的SecureEnvelope，不改变冻结schema |
| secure-sync/src/nonce.ts | node:sqlite、fs、path、createHash、fsync witness | BrowserNonceStore独立QA原型；IDB事务预约prefixBE4+counterBE8，不能宣称等价fsync witness |
| secure-sync/src/keys.ts | SQLite、fs/path/os/url、Node random与密钥材料 | 独立浏览器AES256-GCM non-extractable CryptoKey的IDB持久化探针已验证；不是现有完整keys.ts适配，不克隆旧设备、不存localStorage seed |
| secure-sync/src/pairing.ts | Node random/hash及trusted store | 本轮NOT IMPLEMENTED；真实授权/配对/撤销/恢复不进入浏览器UI |
| apps/api/researchhub/sync/kernel.py | SQLAlchemy/QA PG锁、DAG、grant、projection | 不搬入浏览器；本地工作内容和local version不是accepted projection/revision/server sequence |
| apps/web/src/components/ui.tsx | 展示组件与API编辑器混合 | 提取纯展示组件兼容重导出；QA只复用展示/CSS，不调用原API编辑器 |
| apps/web/public/sw.js | 离线提示页fallback，旧缓存清理范围过宽 | 不在QA origin注册旧worker；新静态壳严格资源范围，不删除未知cache |

浏览器构建必须失败于Node built-in导入；不使用静默polyfill，不通过服务器计算hash。原Node和Python固定协议测试继续执行。

## 本轮字段映射

已查 Python `apps/api/researchhub/sync/protocol.py`、TS `packages/sync-protocol/src/protocol.ts` 的ResearchRun/Note白名单，以及产品ResearchRun models与run-highlight组件。

| 本地字段 | 冻结wire v1 | 本轮处理 |
|---|---|---|
| ResearchRun title / run_type / objective / observation / status / scientific_outcome | 支持，仍需原类型/枚举检查 | 本地versioned操作保存；可用合成ChangeSet验证字段兼容，不冒称已生成授权交易 |
| Note title / body | wire使用title / content，body不是wire字段 | 独立Note UUID；本地body完整保存，未来adapter需显式转换到content；本轮不伪造转换成功 |
| is_highlighted / highlight_type / highlight_note | ResearchRun wire白名单不支持 | 本地持久化并完整救援；标记NEEDS_WIRE_ADAPTER，不丢字段、不直接塞wire v1 |
| highlighted_at / highlighted_by | 产品有这些字段，wire不支持 | 不伪造产品User身份/人工授权；本地audit/source标识独立记录，未来映射另审 |
| id / local_edit_version / source / local_format_version | local bookkeeping，不是payload权限 | 同事务CAS，base revision未知时null；不把本地版本当跨端revision |
| LocalOperation / LocalAudit | 不是SyncTransaction/SecureEnvelope/Kernel Audit | 全部保留本地pending及原来源，不生成receipt/ScientificAccepted |
| Project module_id/module_version/module_snapshot/module_hash | wire使用module_snapshot_hash | 本地module_hash是冻结JSON序列化的SHA256；不是直接可发送的wire hash。未来adapter须依wire canonical规则核验；快照刷新不覆盖，hash不赋予授权 |

浏览器互操作须读取原fixtures/sync/v1（26canonical、59protocol、3nesting、10场景20step）并核对固定预期；不能在测试时重生成期望。科学decimal保留字符串精度；未知/额外字段继续拒绝。

## 密钥与恢复限制

草稿明文IDB仅用于合成QA。密钥探针与业务数据分开；救援排除keys、nonce ledger、认证、HumanGrant和设备信任状态。新profile建立新QA身份，保留导入历史来源，不自动改成已签名新设备交易。

non-extractable不防同源恶意脚本调用；无硬件vault/真实解锁/生产Recovery Kit。本轮只实测AES-GCM，不将其写成Ed25519/X25519/HPKE完整浏览器适配。nonce预约后失败耗号；旧key状态缺失、损坏或旧导入拒绝清零。high-water镜像与ledger都在同一IDB，只检测局部ledger回退，不是外部可信witness；key/ledger一致回滚、整站一致回滚、驱逐、整机断电和实际移动设备持久性均未证明，网络启用前仍BLOCKED FOR NETWORK / PRODUCTION。

`TESTONLY-AES-GCM-v1`封装仅供能力实验，包含绑定的identity/action/digest/AAD/nonce/ciphertext，不是冻结SecureEnvelope。exact retry在校验完整结构和认证解密后复用已存封装；不重新加密或预约。预约后挂起加密、正常关闭全部浏览器进程再重开仍保留耗号和pending拒绝；这不是OS崩溃或断电实验。业务救援包在实际CryptoKey存在时仍排除该独立数据库，新profile恢复不会克隆key。
