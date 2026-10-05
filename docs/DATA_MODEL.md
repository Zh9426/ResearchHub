# 数据模型

生产存储为 PostgreSQL；对象文件为私有 S3/MinIO。SQLite 仅用于隔离单元测试，不能作为生产替代。

核心表：`users`、`projects`、`research_questions`、`hypotheses`、`milestones`、`tasks`、`research_runs`、`parameters`、`metrics`、`sources`、`artifacts`、`evidence`、`claims`、`notes`、`decisions`、`risks`、`tags`、`audit_logs`。工作流表：`stage_gates`、`gate_criteria`。认证表：`sessions`、`api_tokens`。

Claim 的 Evidence/Run/Artifact/Source、Decision 的 Evidence、Gate 和 Criterion 的 Evidence 使用独立关联表及真实外键。项目属于一个 User；任何链接必须指向同一项目。Run 父关系必须同项目且无环。所有资源使用 UUID。

Run 执行状态与 `scientific_outcome` 独立：运行完成可以得到 `negative_result`、`inconclusive` 或 `candidate_rejected`。Observation、AI Analysis、Human Conclusion 分别保存。环境、软件版本、代码版本、时间、创建者为可追溯字段。

参数 value 可为 null；`source_kind=unknown` 不填假值。数值/字符串/布尔/对象/数组使用 value_type 验证。来源引用到 Source，并保留 source_location、uncertainty、valid_conditions、is_confirmed。Metric 可以引用所属 Module 的 metric_schema_id。

Artifact 数据库仅保存文件名、MIME、长度、SHA256、随机 object_key、归属、类别、metadata 与创建者。上传以固定块计算校验摘要与长度，超限拒绝；下载在授权后流式返回，不公开 bucket。文件扩展名与 MIME 有白名单，PNG/JPEG/PDF 验证头部。默认上限 50 MiB，由 MAX_UPLOAD_BYTES 控制。

Alembic 初始版本为 `0001_core`，包含冻结的建表定义。后续模型变化应添加递增 migration，不能重生成已部署的初始版本。运行 `python -m alembic -c infrastructure/migrations/alembic.ini upgrade head`。

会话仅保存 opaque cookie 的 SHA256；cookie 为 HttpOnly、SameSite=Lax，生产设置 COOKIE_SECURE=true。密码 scrypt 独立盐。写请求验证 CSRF；API Token 仅保存 SHA256，scope 限制读写，actor_type 由可信 human 签发并保存。首次 setup 由数据库唯一 bootstrap_key 防止并发重复管理员。

登录限制默认每个直接连接 IP 15 分钟最多 10 次失败尝试，成功登录清除记录；只信任连接地址，不接受客户端自报的转发 IP。内存缓存最多 1024 个 IP，进程重启会清空；多进程部署需后续共享限流存储。LOGIN_ATTEMPT_LIMIT 与 LOGIN_ATTEMPT_WINDOW_SECONDS 可配置。上传请求在 multipart 解析前限制总长度，文件流另校验实际字节数。
