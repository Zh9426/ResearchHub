# Research Run Bundle

标准目录包含 `researchhub-run.json`、`parameters.json`、`metrics.json`、`manifest.json` 和 `artifacts/`。Run 类型必须存在于目标项目的冻结模块中；示例适用于 HDSP 模块，全部明确标为 SYNTHETIC，不能作为科学结论。

用项目 Python 打包所选目录：

```powershell
.\.venv\Scripts\python.exe scripts/pack-bundle.py examples/research-bundle storage/runtime/synthetic-bundle.zip
```

在项目“导入与导出”选择 ZIP，先查看 Run、参数、指标、文件元数据和冲突提示，再人工确认。未知数值和单位填写 JSON `null`，不要以零替代。文件校验值是实际字节的 SHA-256；编辑文件后必须重新计算。

导入限制：压缩包 50 MiB、解压总量 100 MiB、最多 256 个文件、单个元数据文件 1 MiB、参数/指标各 100 项；不允许路径穿越、符号链接、特殊文件、重复路径、未声明文件或异常压缩比例。预览有效期一小时，绑定账号、项目、文件摘要和冻结模块摘要；确认失败整批回滚，可能写入的对象进入可重试清理队列。AI 令牌不能确认导入。

同名 Run 或相同文件内容会提示重复；人工核对后可以创建独立记录。导入不会覆写已有 Run。上传成功仅表示预览通过，不能算科研记录已经入库。

项目导出 ZIP 包含全部科研元数据、CSV/JSONL、冻结模块和完整审计，可选择带文件字节；导出上限 20000 条记录、总计 256 MiB。项目导出与单 Run Bundle 是不同格式，不替代 PostgreSQL/MinIO 完整备份。
