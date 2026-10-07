# RH-C14N-1 QA protocol library

纯 TypeScript 库，不导入 React、HTTP 或 Python，不接生产同步。Node 24 可直接执行 TypeScript；无新增运行时依赖。SHA-256 使用 Node 标准 `crypto`。

`canonicalBytes` / `strictLoads` / `digest` 实现严格 JSON 与独立 canonical encoder。
科学 decimal 保留原始字符串，`scientificEqual` 只比较 exact coefficient/exponent，不修改 wire、不自动合并。
原生 JS Number 无法识别其历史输入是否写成 `1.0`，因此 wire 文本入口必须使用 `strictLoads`，不能先 `JSON.parse` 后验证。

`validateChange` / `revision` 和 `validateTransaction` / `transactionDigest` 严格检查语义字段。
事务格式包含 `ordered_change_ids`、按业务顺序的 `changes`（每项不包含 revision）和已排序唯一 `dependencies`。
计算得到的 revision、digest、`COMMIT` 以及传输封装不进入语义对象；推荐外层 `{ transaction, digest, commit_marker: 'COMMIT' }`。

`validateTransaction(tx, context?)` 可比对受信 `project_id`、`device_id`、`actor_id`、`actor_type`；context 中每个提供的字段均必须匹配。
这只是身份一致性验证，不能代替 principal、grant 或 Human 科研权限授权。

运行：`npm --prefix packages/sync-protocol test`；类型检查：`npm --prefix packages/sync-protocol run typecheck`。
测试独立读取 `fixtures/sync/v1` 的固定文本、UTF-8 hex、SHA-256 和 valid/invalid 协议用例。
`tests/sync_vectors/build_fixtures.py` 仅是 fixture 作者工具：canonical 字符串由固定手写 anchor 提供，绝不调用任一被测 encoder。
测试使用 `--test-isolation=none`，适用于本地 sandbox 不允许 Node test runner spawn 的场景。
