# RH-C14N-1 Canonical Wire Specification

状态：Sprint 1 冻结规范，Python/TypeScript 独立实现与固定fixtures必须一致；生产加密/Relay尚未实现。标准依据：[RFC8785](https://www.rfc-editor.org/rfc/rfc8785.html) 的字符串、UTF-16 key排序及无normalization原则；本协议**限制数值输入**，不自称全binary64 JCS实现。

## 编码与值

UTF-8，无BOM/多余空白。对象key按UTF-16 code units字典序递归排序；数组保留业务顺序（parents/dependencies作为集合在schema中要求已排序、去重）。字符串保留原始Unicode scalar，不NFC/NFD normalize，拒绝lone surrogate/无效UTF-8。引号、反斜杠和U+0000–001F采用JSON固定escape；其他Unicode直接UTF-8。duplicate decoded key必须拒绝，不依赖JSON.parse/json.loads最后覆盖。

值嵌套上限64：根值depth=0，每次进入object value/array element加1，包括叶值；depth>64明确拒绝，绝不截断。两端encoder与strict decoder均遵守同一限制，避免语言递归栈不同造成可接受输入范围不一致。64层固定有效样例与65/600层拒绝样例验证边界。

null、true、false原样；空字符串、[]、{}与null各自不同。原生number只允许整数[-9007199254740991,9007199254740991]；禁止native float、指数/小数JSON number literal、native -0、NaN/Infinity。JSON严格decoder检查数字lexeme，不能先把1.00解析成1再掩盖精度。对象encoder面对内存JS Number1.0无法知道lexeme，wire入口必须走strict decoder；Python拒绝float对象。

科学数值用 `{ "value_type":"decimal", "value":"1.600", "unit":"MPa" }`，decimal grammar为`-?(0|[1-9][0-9]*)(\.[0-9]+)?([eE][+-]?[0-9]+)?`，保留原字符串。大整数用value_type=integer及canonical整数string（无+、无leading0、无-0）；native safe integer仅用于版本/计数等离散数据。科研未知值显式null与独立status，不伪造0。decimal长度最多1024、exponent绝对值最多100000；规范限制用于拒绝资源消耗，不截断科研数据。

1、1.0、1.00、1e0若以decimal string表达，数值比较相等但wire不同；1.60/1.600也产生不同revision，因为尾零表达用户精度，不自动丢失。科学相等函数按exact coefficient/exponent规范比较，绝不用binary64近似；比较不改变wire。单位/来源/uncertainty仍是业务语义，数值相等不能自动merge科学分叉。

UUID为lowercase canonical36字符，nil禁止；datetime为真实日历UTC固定`YYYY-MM-DDTHH:mm:ss.sssZ`（year0001–9999，禁闰秒/locale/offset）。digest为lowercase64hex，不加sha256前缀；enum严格白名单，未知字段/版本拒绝或隔离，不默默丢弃。

## ChangeSet（schema_version=1）

语义字段全集：change_id、audit_id、transaction_id、project_id、device_id、actor_id、actor_type（human/codex/chatgpt/system）、object_type、object_id、operation（create/update/archive/trash/restore/resolve）、parents、payload、schema_version、module_snapshot_hash、created_at。create parents=[]；普通操作一个parent；resolve消费全部expected_heads（至少一个，允许整批review中的非冲突成员）。field白名单和业务类型由protocol decoder再验证。

`revision = sha256(canonical_bytes(semantic_change))`。revision单独作为计算/校验值，不把自身放入语义payload。全部上述字段都绑定hash。Relay seq/retry/receipt/envelope nonce/signature/key_epoch不进入semantic digest；重试/重封装不改revision。

## SyncTransaction（protocol_version=1）

语义字段：transaction_id、idempotency_key（必须等于transaction_id）、project_id、device_id、actor_id、actor_type、protocol_version、schema_version、created_at、ordered change_ids、changes、dependencies（排序唯一transaction IDs）。所有ChangeSet身份/项目/版本/transaction/actor必须匹配；ordered change_ids精确等于changes的业务顺序，禁止重复object成员/变化ID和跨项目。state是本地账本状态，不进入wire语义；digest=SHA256上述canonical transaction（不含自身digest）；commit_marker=COMMIT是外层完整性标志。

外层Envelope预留signature/key_epoch/ciphertext metadata/nonce/receipt，仅QA mock；不能用mock签名声称来源已获密码学认证。grant不是payload权限：来自独立受信authorization context，绑定transaction/对象/操作/expected_heads等由apply检查。

## Fixed vectors 与兼容

fixtures/sync/v1保存input、expected canonical UTF-8（文本及hex）、SHA256，以及valid/invalid protocol案例。包含ASCII/中文/emoji/combining/UTF16排序差异、所有空值/布尔/整数/large整数/精度decimal/嵌套/数组/UUID/datetime、多changes/parents/modulehash。Python与TS独立测试同一预期，不互相调用encoder。遇到未知protocol/schema返回UPGRADE_REQUIRED/QUARANTINED，原始已接收内容可保留，但不能显示fully synced。
