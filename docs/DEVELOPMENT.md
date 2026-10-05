# 本地开发

Windows 使用 Docker Desktop（WSL2/Linux containers）和 Docker Compose v2，PowerShell 5.1 或 7 均可运行脚本。默认生产容器只向本机暴露 Web；依赖安装需要互联网下载开源包，不上传科研数据。

```powershell
.\scripts\setup.ps1
.\scripts\start.ps1
.\scripts\stop.ps1
```

setup 保留已有 `.env`，首次生成三个独立随机秘密。start 检查 CLI、daemon、Compose，运行 config 校验，build 并等健康检查；API 先执行 Alembic migration，再启动 uvicorn。进入 `http://localhost:3000` 首次创建账户。stop 不删除持久卷。

MinIO 使用上游固定安全修复版本 `RELEASE.2025-10-15T17-29-55Z` 源码构建，上游此版不提供官方预编译 Docker 镜像；第一次 Go 编译较慢。参见[官方版本说明](https://github.com/minio/minio/releases/tag/RELEASE.2025-10-15T17-29-55Z)。不使用旧版预编译镜像代替安全修复版本。

要直接运行后端/前端，显式启动依赖端口：

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d db minio
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r apps/api/requirements.txt -r apps/mcp/requirements.txt
# 设置 DATABASE_URL 指向 localhost:5432，S3_ENDPOINT_URL 指向 http://localhost:9000；
# 其余 S3 密钥使用 .env；API 不自动把 Compose 的主机名替换为 localhost。
.\.venv\Scripts\alembic.exe -c infrastructure/migrations/alembic.ini upgrade head
.\.venv\Scripts\uvicorn.exe apps.api.researchhub.main:app --port 8000
# 另一个 PowerShell
Set-Location apps/web
$env:API_INTERNAL_URL = 'http://127.0.0.1:8000'
npm ci
npm run dev
```

```powershell
.\.venv\Scripts\python.exe -m pytest tests/backend tests/mcp -q
Set-Location apps/web
npm test
npm run build
```

后端内存对象适配器/SQLite 测试验证业务关系，不等于 PostgreSQL/MinIO 持久化验收。实际运行验收还需要真实服务登录、上传、下载 checksum、服务重启、数据再次读取。PWA 页面可安装性需真实安全上下文验证。

手机和电脑访问同一服务器：把 `.env` 中 `RESEARCHHUB_HOST` 改为本机 LAN IP 或可解析主机名（例如 `192.168.1.50`），使用 `.\scripts\start.ps1 -Lan`。Caddy 在 443 提供本地 HTTPS；仅在可信私人局域网允许 Windows 防火墙入站 443，不配置公网端口转发。

导出本地 CA：`docker compose -f docker-compose.yml -f docker-compose.lan.yml cp caddy:/data/caddy/pki/authorities/local/root.crt storage/caddy-root.crt`。在电脑/手机系统中安装并显式信任这个根证书，再用 `https://192.168.1.50` 打开。iOS 通常还需证书信任设置中启用完全信任。IP 变化后同步配置并重启 Caddy。LAN 模式 Cookie Secure，不能继续用明文 localhost 登录；测试时统一使用 HTTPS 地址。

v0.1 PWA 不缓存科研 API 响应，网络断开时不承诺离线编辑，避免陈旧科研事实与会话数据留在 service worker 缓存中。

## Windows 原生验收运行环境

Docker Desktop 的 WSL2/Virtual Machine Platform 首次启用可能要求电脑重启。不能用 Compose 配置校验代替容器运行验收，也不自动重启用户电脑。为继续验证真实数据持久化，本仓库提供额外的 localhost 原生 QA 脚本；Docker Compose 仍是正式部署方式。

```powershell
.\scripts\native-qa.ps1 -Action Install
.\scripts\native-qa.ps1 -Action Start
.\scripts\native-app.ps1 -Action Start -Qa
.\scripts\native-app.ps1 -Action Stop
.\scripts\native-qa.ps1 -Action Stop
```

Install 从 PostgreSQL 官方推荐的 EDB 下载 PostgreSQL17.11 Windows binary zip，从 Go 官方下载当前稳定便携 zip 并验证官方 SHA256，再编译同一个固定 MinIO 安全源码版本。没有 SQLite 或假 S3 替代，没有安装 Windows 服务或更改注册表。首次编译会下载 Go 模块并耗时数分钟。

全部依赖、数据库目录、对象目录、日志和随机凭据放在被忽略的 `storage/runtime/`。PostgreSQL 仅监听 `127.0.0.1:55432`，host/local 都启用 SCRAM；MinIO API/Console 仅监听 `127.0.0.1:59000/59001`。`native-env.json` 含真实秘密，不能提交或公开。

`native-app.ps1 -Qa` 选择 `researchhub_qa` 数据库和 `researchhub-qa` bucket；不带 `-Qa` 选择独立空 `researchhub` 数据库和 `researchhub` bucket。脚本先迁移再启动 API8000 与已构建 Web3000，不自动建立用户或 demo，保留首次账户创建体验。QA 数据不能当作个人正式科研结果。API/Web Stop 不停止存储服务，所有 Stop 都保留数据。

原生验收通过只证明同版本真实 PostgreSQL/MinIO 与应用兼容；Docker 构建、容器网络、命名卷重启、Caddy LAN HTTPS 仍须在重启后单独验证。以上 localhost 原生脚本不提供手机网络访问。
