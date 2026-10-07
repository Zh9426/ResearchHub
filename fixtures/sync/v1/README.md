# 固定协议与 Kernel 场景

- canonical.json：26 个手工固定 bytes/SHA-256 样例。
- protocol.json：59 个结构/字段/数字/身份样例，7 个有效、52 个拒绝。
- nesting.json：64 有效、65/600 拒绝的统一深度边界。
- kernel_cases.json：10 个固定场景、20 个步骤，覆盖科学冲突、ID 碰撞、schema/module 隔离、AI 冒充、trash、离线解决分叉、Unicode 与 Audit 碰撞。

Python 与 TypeScript 分别读取同一 raw wire 并核对 canonical hex、revision 和 transaction digest；两者不相互调用。真实 PostgreSQL transcript 测试另外核对 Kernel 状态，它为每轮映射新 UUID/hash namespace 避免已有 QA 历史干扰。TS 只实现 wire 层，不声称运行 PostgreSQL 状态引擎。

build_fixtures.py 与 build_kernel_fixtures.py 是 fixture 作者工具；固定字节来自人工确定的字段顺序与独立 hashlib 锚点，不调用被测 canonical/revision codec。测试读取已经提交的样例，CI 不重生成预期输出。
