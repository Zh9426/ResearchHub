# 数据备份与恢复

PostgreSQL 和 MinIO 需要一起备份。数据库有文件 metadata/对象 key，只有 SQL dump 或只有文件都不完整。默认数据卷由 Docker Desktop 管理；备份输出写入 Git 忽略的 `storage/backups/`。

```powershell
.\scripts\backup.ps1
# LAN 部署加 -Lan
```

脚本停止 API/Web 写入者，保留 DB/MinIO 运行；用 `pg_dump -Fc` 导出数据库，用 S3 API 导出全部对象到 `objects.zip`，每个对象记录 key/size/SHA256/ContentType/metadata。两份文件的 SHA256 写入 `manifest.json`。完成或失败后，只恢复原先正在运行的 API/Web。

维护窗口内不要用 dev 数据库端口或 MinIO 控制台直接写入，否则不能保证一致性。v0.1 使用离线写入窗口，不承诺在线 PITR。未启用对象版本控制，因此导出当前对象集合。

将整个备份目录复制到独立磁盘，并定期放入加密离线副本；`.env` 含秘密，单独加密保存，绝不提交。代码、manifest/module、迁移来自私有 Git；科研原始数据来自备份。Caddy CA 可单独保存，需要迁移时也可重新签发并在设备重新信任。

恢复只面向**空数据库和空目标 bucket**，不自动清除已有数据：

```powershell
.\scripts\setup.ps1
.\scripts\restore.ps1 -BackupDirectory 'H:\ResearchHub\storage\backups\20261005-180000' -ConfirmRestore
```

建议先在另一个 checkout 与 Compose 项目名称下恢复：通过 `$env:COMPOSE_PROJECT_NAME='researchhub-recovery'` 使用新的命名卷，停用旧 Web 以免占用端口。restore 验证外层校验摘要，停止写入，检查数据库空，再验证所有对象内部摘要，拒绝非空 bucket，最后恢复 SQL 并启动迁移/API/Web。不从 zip 解压任何路径，不使用 restore --clean，不删除旧卷。

若恢复中断，写入服务保持停止；目标可能只有部分恢复内容。保留备份与旧部署，在新的空目标上重试，不能将中断目标当作完整恢复。完成后检查登录、项目、Run 参数/指标、审计，以及一个实际 Artifact 下载并比对 checksum。

**普通停止**使用 `scripts/stop.ps1`。不要执行 `docker compose down -v`，该命令会删除数据库和对象卷。脚本实现与语法检查不是恢复演练；是否实际执行备份/恢复必须以本轮验证报告为准。
