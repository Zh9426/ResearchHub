# Linux TLS helper 权限与初始化故障注入修复 QA

2026-10-08；仅 SYNTHETIC LOOPBACK。对应 Linux CI run 37785421799 的 QA_DOCKER_START_FAILED 调查。此处记录本机 Docker Linux 内核实测，不宣称 GitHub Linux runner 已通过；需 root 提交后重新跑 CI。未修改 workflow、Git、生产迁移、个人服务或专用 PG 数据配置。

## 根因证据与有效 RED

原 helper 为 UID0、cap-drop ALL、只恢复 CHOWN；host 上 generate_certificates 写出的 server.key 为 host UID 所有、mode0600。Linux root 在缺 DAC capability 时不能仅凭 UID0 读取其他 UID 的0600文件。Windows host bind 映射未暴露该差异。

使用唯一命名、明确 label 的独立 Docker volume，写入公开 SYNTHETIC_PUBLIC_SENTINEL，设置 UID1000、mode0600；使用现有 QA Relay image、network none、readonly rootfs、source readonly、no-new-privileges。捕获stderr仅判断固定类型，未输出rawstderr/Env/密钥：

- caps=[CHOWN]：returncode=1，PermissionError=true。
- 只增加 DAC_READ_SEARCH：returncode=0。
- 结束后核对卷名及label，精确删除；未使用真实TLS key作探针。

这是有效行为 RED/对照实验，证实读取权限根因，非从错误码猜测。

另对实际生命周期回归增加 earlier_failure 场景：要求 ingress_create/ingress_connect 测试发现较早helper失败。修复前执行 `HUB_RELAY_QA=1 pytest tests/secure_relay_lifecycle/test_partial_init.py -k earlier -q --basetemp storage/runtime/s2-tls-earlier-red`，两项 **2 failed / 3 deselected in18.19s**，均为 DID NOT RAISE AssertionError；原广义 QA_DOCKER_ 捕获确实误把helper失败当作后续注入成功。两次真实失败资源均走原owned清理。

## 最小实现

scripts/secure-relay-qa.py 增加唯一 TLS_COPY_CAPABILITIES=(CHOWN,DAC_READ_SEARCH)，仅短命TLS复制helper使用。guard要求规范化CAP_前缀后精确双cap，缺少或额外cap拒绝。helper仍无网络、readonly rootfs、source bind readonly且仅server.crt/server.key、target唯一owned volume、no-new-privileges；没有授予DAC_OVERRIDE，未降低任何key权限。

故障测试记录实际执行的注入点，先完成exact cleanup再断言恰好命中一次；进一步要求对应 START/CREATE/NETWORK 固定错误。较早故障必须失败。覆盖标准三处故障和两处earlier helper negative。

新 test_tls_dac.py 使用相同QA helper cap配置在真实Linux volume读取UID1000/0600公开sentinel。CHOWN-only拒绝、QA双cap成功；即使sentinel mount暂为RW，双cap也不能直接写另一个UID的0600文件，随后确认内容、mode与owner未变，精确核label删除卷。该测试需已有QA镜像；当前完整目录执行顺序先test_partial_init构建镜像，再test_tls_dac。单独调用前需先运行生命周期构建步骤。

CAP_兼容、缺cap与额外DAC_OVERRIDE拒绝通过修改inspect返回的公开HostConfig副本验证，这是guard逻辑检查；不称为真实容器新增/撤销cap实验。实际Linux DAC实验由独立sentinel测试完成。

## 最终验证

- `HUB_RELAY_QA=1 pytest tests/secure_relay_lifecycle -q --basetemp storage/runtime/s2-tls-dac-final`：**6 passed in59.25s**，包括原3处故障、2处earlier negative、1个真实Linux DAC测试。每个partial用例清理后验证PG原ID保留并readiness成功。
- `pytest tests/secure_sync/test_tls_material.py -q --basetemp storage/runtime/s2-tls-material-final`：**2 passed in0.40s**。本机host为Windows，host0600断言按既有条件略过；Linux volume实际0600由sentinel测试验证。
- `HUB_RELAY_QA=1 python scripts/secure-relay-qa.py --init`：实际 **QA_READY TLS:127.0.0.1:38001 PG:127.0.0.1:35434**。
- `HUB_RELAY_QA=1 pytest tests/secure_relay/test_network.py::test_real_https_ca_hostname_and_plaintext_rejection -q --basetemp storage/runtime/s2-tls-network-final`：**1 passed in8.61s**，实际 CA/hostname/plaintext 验证和teardown隐私审计。
- 真实ready容器只提取cap/UID和stat验证：Relay/ingress均cap-dropALL、无CapAdd、UID10001；`/tls/server.key`为mode0600、uid/gid10001。
- teardown隐私：private_material_count=2、canary_count=7、unique_pattern_count=62、scanned_bytes=125730、bytea_column_count=11、bytea_value_count=1、bytea_decoded_bytes=474、hits=0。实际PG dump/driver decoded bytea与容器文件扫描，未输出私钥、原Env或凭据。
- 三个变更Python文件 Ruff check/format-check、tracked diff whitespace 检查通过。

实现只修改runner、partial init tests，新增Linux DAC test及本记录。未重复174/48密码suite或130网络suite；核心密码层未修改。最终保持专用QA服务ready，网络锁释放交root及最终安全审计者；独立安全复审和GitHub Linux CI结果由root接续，不以本地绿色替代远端CI。
