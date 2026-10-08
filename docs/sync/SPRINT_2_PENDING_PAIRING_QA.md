# Sprint 2 PENDING 配对修复 QA（2026-10-08）

边界：仅 SYNTHETIC LOOPBACK QA。该记录是最终审计 Important/P2 修复的交接，不替代独立复审或完整 Sprint2 网络 Gate。未提交/推送、部署、修改可见性或操作个人/生产服务。

## Finding 与最小修复

Python/Node consume 在验证合法 proof 后无条件 add，已有 PENDING UUID 触发 PREFIX_OR_DEVICE_COLLISION，无法完成激活。两端现在从事务内完整 pinned history 验证后的 current manifest 查该 UUID；不存在则沿用 add，存在则要求原状态 PENDING 且 challenge.recipient 完全等于原 member 仅将 status 改为 ACTIVE。匹配后调用现有 activate。role、双公钥、fingerprint、nonce_prefix、granted_at、revoked_at 均不能顺带变化；ACTIVE/REVOKED 拒绝。membership_epoch 仅加1，key_epoch 不变，原 prefix 不变。

attempt 计数、proof验证、同事务 manifest/challenge/receipt 持久提交、单次消费、重启 immutable receipt、旧授权链及撤销逻辑保持原实现。没有更改 keys 或 wire schema。

## 实际 RED

- Python `pytest tests/secure_sync/test_pairing.py -k pending -q --basetemp storage/runtime/s2-pending-red2`：3 failed / 7 passed / 13 deselected；三个成功/崩溃边界正例均因 PREFIX_OR_DEVICE_COLLISION 失败。首次 sandbox WinError5 是环境失败，未记作有效RED；随后限定合成命令经自动审批执行。
- Node `E:/node/node.exe --experimental-strip-types --test --test-isolation=none --test-name-pattern='Node PENDING pairing' test/lifecycle.test.ts`：1 failed，同一冲突。首次默认 test isolation spawn EPERM 是环境失败；改用项目既有 none 模式后取得有效RED。

## 覆盖与实际 GREEN

新增 Python 12 项、Node 10 项：exact activation、before/after commit crash 重启/receipt/replay、ACTIVE/REVOKED/role/prefix/双keys/granted_at 七类合法签名身份变更拒绝，及真实 SQLite AFTER INSERT manifests / AFTER UPDATE receipt trigger 故障。故障后全部状态回滚，attempt=0/used=0/receipt=NULL；重开并移除trigger后可正常完成。身份变更失败记录一次attempt、无receipt且manifest不变。新增解包断言以 boolean 比较避免失败诊断打印原始key；Device私有字段维持redacted，参数化仅公开case名称。

执行结果：

- `.venv/Scripts/python.exe -m pytest tests/secure_sync -q --basetemp storage/runtime/s2-pending-crypto-full`：174 passed in19.99s，含两项TLS材料测试（不冒充网络测试）。
- 最终配对及独立 Python↔Node interop 定向 `pytest tests/secure_sync/test_pairing.py tests/secure_sync/test_lifecycle_interop.py -q --basetemp storage/runtime/s2-pending-final-target`：26 passed in2.82s。独立双方 HPKE/manifest/snapshot/chunks 仍执行真实crypto。
- `E:/node/node.exe --test --test-isolation=none test/crypto.test.ts test/lifecycle.test.ts`：48 passed；`E:/node/node.exe ../../apps/web/node_modules/typescript/bin/tsc -p tsconfig.json`：PASS。
- 三个Python变更文件 Ruff check/format-check：PASS；变更 diff whitespace：PASS。

## 真实 HTTPS / PostgreSQL 定向

取得 root 分配的专用网络QA锁后执行：

`HUB_RELAY_QA=1 pytest tests/secure_relay/test_security.py::test_pending_pairing_exception_is_own_session_only -q --basetemp storage/runtime/s2-pending-network`

1 passed in8.70s。既有测试从手工challenge改为可信本地 bootstrap + accept PENDING + create_challenge，完整通过 own challenge GET、拒绝其他session、submit、trusted consume、HTTPS complete、receipt、grant GET、客户端独立 HPKE unwrap。激活前 pull=401，激活后 reader pull=200；reader push和membership修改仍401。确认完整member除status外一致，membership_epoch+1/key_epoch不变。

同进程 fixture teardown 实际隐私扫描：private_material_count=9、canary_count=7、unique_pattern_count=111、scanned_bytes=169657、bytea_column_count=11、bytea_value_count=19、bytea_decoded_bytes=15298、hits=0；PG dump与driver decoded bytea均扫描，Relay/ingress文件分别13/1。结果只记录计数，无密钥或凭据。网络锁已释放。

## 交接

实现范围仅 Python/TS pairing、Python pairing tests、Node lifecycle tests、Relay security该测试及本记录。其余文档/CI/提交由root负责；未重复130网络suite。冻结交同一最终安全审计员独立重测，通过后root再运行完整最终回归。
