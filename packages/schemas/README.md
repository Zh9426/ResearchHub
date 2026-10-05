# API 输入契约

这些 JSON Schema 从 API Pydantic 类型生成，Core 字段严格验证，额外字段拒绝。创建请求使用完整 schema；PATCH 为部分更新，服务器合并现值后使用相同 schema 校验。服务负责同项目引用、所有权、父 Run 无环和 Gate 证据校验。

更新类型后运行 `python -m apps.api.researchhub.export_schemas`。Module manifest 的契约也在这里；各模块实际配置在 `packages/project-modules/`。
