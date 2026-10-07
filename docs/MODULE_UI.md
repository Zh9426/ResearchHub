# 模块界面与冻结版本

新项目采用 0.2.1 Manifest；既有项目仍使用原冻结快照，不会因更新 JSON 自动改变。数据管理提供人工升级预览，确认后才采用新版本。

- `navigation` 驱动项目导航，Core 路由使用 Registry；`custom_views` 声明布局及 run_types/metric_ids/artifact_categories/evidence_filters，由数据库分页查询执行筛选。
- `dashboard_widgets` 声明 kind、名称与筛选；同类组件可以使用不同 ID 各自显示。旧字符串定义仅合并同义组件，不改变科研记录。
- `run_forms` 按记录类型声明上下文字段和分组参数/指标。未知值保持 null、实际单位及已填来源保持；修改指标值后恢复未知验证状态。
- 指标方向默认 informational。maximize/minimize/target_range 必须由定义声明；代表性指标与时间序列不自动推断总体最佳。
- 时间序列按保存时间绘点，不等同实验时间；不同单位分图，不填补未知值、不插值，每页最多 50 点。显式 metric_schema_id 优先于名称匹配。

界面没有根据 HDSP/ICE 模块 ID 选择科学指标或领域视图。新模块可直接提供定义；需要新增布局时才扩展小型组件 Registry。实验和测量的快速采集仅发送冻结模块及所选表单支持的上下文字段。

旧版专属视图只有名称而未声明筛选时，使用通用视图并明确提示，不凭客户端硬编码补写旧科学定义。
