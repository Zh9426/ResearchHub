# TLS-001：并发首次 GET 的 TLS 握手 EOF

**状态：OPEN，根因未确定。** 此次修改是诊断和固定复现补丁，不是已验证的故障修复。未更改密码套件、证书验证、超时、连接/请求配额、快照或事务语义。未进入 Sprint 3。

## 原始失败证据

- GitHub [run 37789245245，attempt 1](https://github.com/Zh9426/ResearchHub/actions/runs/37789245245/attempts/1)，HEAD `c3a6dd7c0773f4a8a4e3308b4f7ad6d4fd410cb4`。
- 创建 `2026-10-08T14:02:46Z`，完成 `14:07:15Z`，conclusion=`failure`。真实网络步骤：**1 failed / 54 passed / 170.49s**。
- 失败用例：`tests/secure_relay/test_network.py::test_concurrent_first_get_snapshots_original_response`。
- 本地独立保留于 ignored `storage/runtime/s2-tls-incident-37789245245-attempt1/`，不上传原始日志或运行时材料到公开仓库：

| 文件 | SHA-256 |
|---|---|
| `original-attempt1-logs.zip` | `a3a5e6329c7f2831f7a7d68b150bcd5df7d5852ca2cf6b19a3b1bf234430692b` |
| `original-failed-step.log` | `2a8b4df149426aca85e3a07e4a8d9d63dc576da06709ed4f5daf359604a7e32e` |
| `prepatch-original-30.xml` | `2fec293897c63c22adc7307018212867868b36d6a1933411d90948ab34ee0cce` |

归档通过 GitHub `/actions/runs/37789245245/attempts/1/logs` 获取，使用 exclusive create 保留原件；`attempt1-metadata.json` 保存明确的 run/attempt/head/conclusion。另有 `manifest.json` 保存最初步骤日志指纹。后续成功重跑属于 attempt 2，**不覆盖或关闭 attempt 1 的失败**。

脱敏关键栈：

```text
test_concurrent_first_get_snapshots_original_response
  ThreadPoolExecutor.map -> ProjectClient.send -> httpx.Client.request
  httpcore.HTTPConnection._connect -> stream.start_tls
  httpx.ConnectError: [SSL: UNEXPECTED_EOF_WHILE_READING]
```

## 已定位到的阶段与证据缺口

TCP 建连已返回，失败出现在**新连接的 TLS 握手**；该连接尚未开始发送 HTTP 请求。因此目前没有证据把此失败归因于签名、immutable GET、Relay receipt 或 PG 事务。堆栈是 `_connect/start_tls`，不能直接解释为复用了失效的 TLS keepalive。

原入口将网络异常统一关闭且未记录原因。原 CI 已清理容器，无法恢复当时入口方向、上游连接结果或 TLS 服务端状态。入口容量拒绝、上游建连失败、转发方向关闭/超时仍是候选，**没有一个已被证明为原始根因**。30 秒连接寿命、5 秒方向空闲期限和 3 秒上游建连期限保持原值；不能因它们存在就推断此次超时。

## 最小补丁

1. 入口仅输出固定事件/原因枚举、两个方向的字节计数、耗时、时间和 active 数量；不输出地址、数据、异常文本或任何凭据。失败连接仍关闭，不重试。Docker 原有两份 1 MiB 日志轮转限制保持不变。
2. 原用例保留 pooled 调度，新增 fresh 调度；每种固定 **10 轮 × 4 并发 GET**。fresh 每次建立新 CA/hostname 验证连接。所有响应必须 HTTP 200、四份相同，随后 push 与原 GET 重放仍验证不可变快照。任一异常/断言失败直接令用例失败，不继续下一轮。
3. trace 只允许 TCP/TLS/HTTP 发送与接收的固定阶段事件，绝不保存 httpcore 的 `info` 对象。`finally` 仅保留证据、不改变结果；记录失败发生于 concurrent_get / comparison / push / replay 的哪个操作。
4. 每组证据含格式校验的服务 run、trial、invocation、cohort、case_id、轮次。入口导出先验证真实 QA topology，再验证固定字段 schema，按 run+UUID 独占写入，不覆盖旧快照。
5. CI 无论成功失败，均在清理之前导出和上传这些固定字段 JSON。artifact 名包含 GitHub run_id/attempt，保存 30 天。导出失败返回非零，不能悄悄略过。

原因码描述**观察到的终止状态**，不是对因果先后的保证。双方向同次唤醒 EOF 为 `multiple_directions_eof`。字节数说明转发了多少字节，不等价于 TLS 握手已经成功；必须与客户端 trace 一起判断。

## 固定验证记录

| 验证 | 实际结果与边界 |
|---|---|
| 未改原用例，固定 30 次 | 30 passed / 14.26s；真实 TLS+PG，未复现 |
| 初版诊断，固定 30 次×10轮 pooled | 30 passed / 41.54s；300轮/1200 GET 全部通过，但 trace 仅3个新 TLS 握手，不能当作1200次握手验证 |
| 增加 fresh 后完整 test_network.py | 7 passed / 13.07s；两种调度各10轮，其余网络断言保留 |
| 关联运行标识后，固定两种调度各10次×10轮 | 20 passed / 28.28s；200轮/800并发GET；实际trace核对fresh为400次TCP complete +400次TLS complete，pooled为400次GET和3次TLS complete，均无failed事件；invocation=`0973eb20-e578-44ae-b36a-5b69b7c0d6a2` |
| 诊断边界单测 | 13 passed / 0.56s；连接/方向/寿命/容量分类、双EOF、拒绝额外敏感字段；新增原用例握手错误传播、首轮失败即停止、info不入证据负例；这些是单元故障输入，不冒充真实服务验收 |
| 独立复审 | APPROVED，仅针对诊断补丁；独立单测12 passed / 0.32s，无未关闭Critical/Important；原始EOF仍OPEN |
| 最终完整实际网络回归 | Relay **56 passed /284.26s**，client **75 passed /43.83s**，两cohort真实PG/dump/bytea/files/log隐私扫描均 **0 hits**，无skip/deselection；完整runner退出0 |

完整回归 service run=`06ce73e3-3b7f-4b18-8cb6-a3ff27db0d9b`，trial=`e0c250d2-9b99-409d-8a90-eb79a5be9dfc`；aggregate/collection/JUnit/隐私报告均在ignored runtime。入口快照160条记录，包括37次上游建连错误、9次客户端读取超时，来自完整故障/拒绝验证的受控环境；它们证明诊断可观察真实网络终止，**不能倒推原CI的关闭原因**。其余109次客户端EOF、4次上游EOF、1次同次唤醒双EOF。最终提交CI须另行核对，任何绿色结果均不关闭本事件。

重复方法：在明确 `HUB_RELAY_QA=1` 且已由 `scripts/secure-relay-qa.py --init` 启动的隔离环境运行以下 pytest plugin。该 fixture 每次创建独立合成 project，固定 10 次，不按结果重试；原测试内部每次10轮，另有pooled/fresh两个参数。所有pytest失败都保留并使进程返回非零。

```python
import pytest

class FixedMatrix:
    def pytest_generate_tests(self, metafunc):
        if metafunc.function.__name__ == "test_concurrent_first_get_snapshots_original_response":
            metafunc.parametrize("project", range(10), indirect=True)

raise SystemExit(pytest.main([
    "tests/secure_relay/test_network.py::test_concurrent_first_get_snapshots_original_response",
    "-q", "--tb=short", "--junitxml=storage/runtime/tls-matrix.xml",
], plugins=[FixedMatrix()]))
```

## 结案条件

当前只完成“定位到握手阶段、保存失败、增加可关联观测和固定复现”。关闭 TLS-001 需要可复现的同类失败及阶段证据，或足以解释原始事件的外部证据；如涉及代码，须最小修复并以针对性 RED→GREEN 及完整网络回归确认。后续任意一次或多次绿色 CI 都不单独满足这个条件。

下一次若出现 EOF：先保存该 attempt 的 artifact 和日志；以 case_id/operation/时间窗口对齐客户端 TLS 事件与同 run 入口快照，区分上游建连拒绝、两个转发方向及服务端关闭，再决定是否需要服务端诊断。禁止 skip、关闭证书验证、增加吞错/重试或放宽网络限制来结案。
