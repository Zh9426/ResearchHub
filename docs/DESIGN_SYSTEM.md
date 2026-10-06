# Research Hub Design System

视觉依据为 `docs/researchhub-concept.png` 概念图。UI 使用 frontend-app-builder 与 ui-ux-pro-max：已运行 dense dashboard design-system、Next.js 表单检索。接受检索的表格密度、键盘焦点和触摸目标建议；营销 hero、默认 neumorphism 配色与本项目不符，未采用。

## 色彩与排版

白色工作面 `#fff`；导航 `#f5f7f8`；正文 `#17252b`；次要文字 `#586974`；边界 `#dde4e8`；主色 `#116b66`。蓝绿表示进行中、绿色表示已完成、红色表示 blocked/failed、灰色表示未知/未开始；始终显示状态文本。

系统 sans（Segoe UI、Arial、中文系统字体）；正文 14–16px，标题 28px，次标题 16px，辅助文字 12px；行高 1.5。数值、ID、revision 使用系统 monospace。无外部字体请求。

4/8px 间距；主要页边距 28px（手机 16px）；6px 圆角、1px 分隔线。科研分组使用少量有意义的 panel，细项用列表、表格、timeline，避免层层嵌套卡片。图表 v0.1 无推断统计图：实际指标用表格展示，未知值显示 unknown。

## 组件与状态

统一 outline SVG 图标，18px、1.75px stroke。按钮/链接有 hover、active、可见 focus；最小触摸目标 44px。表格紧凑行与表头浅灰，长表格自身横向滚动。表单可见 label，必填标识；错误保留输入并提供 alert；保存期间禁用提交。编辑器使用原生 dialog，Escape 可取消，焦点回到触发器。

DEMO / SYNTHETIC 在项目标题与工作区提示中持续显示；样本不被称为真实实验。Evidence 边界、负结果、unknown parameter 和 blocked gate 文本可见。AI Analysis 与 Human Conclusion 分区。

## 响应式

桌面固定 220px 左栏 + 主工作面；平板收窄侧栏但保持内容。手机隐藏桌面 rail，顶部项目 selector、水平项目 tabs、4 项底部导航（Home / Projects / Tasks / Activity），Settings 通过 Account 进入。主按钮在手机宽行；两栏科学面板改单栏；近期 Run 与任务表变为可点列表；宽参数比较表独立滚动。底部 padding 使用 safe-area-inset-bottom；不用缩小桌面页面。

## PWA 与真实状态

manifest + 192/512 PNG + SVG 源图标；service worker 仅缓存明确列出的静态离线资源，API 与认证页面不落缓存。离线显示连接说明。安装按钮响应浏览器 beforeinstallprompt；无 prompt 时提示浏览器菜单安装，HTTP 非安全上下文如实提示。真实 API 的 loading/error/empty 不回落到 mock。尊重 prefers-reduced-motion。

## v0.2 交互架构

已有界面审查：`screenshots/desktop-zh-run-editor.jpg` 显示万能弹窗过长；项目 context 逐渐增长，导航和领域视图存在硬编码。保留 v0.1 配色、字体、分隔列表和 44px 触摸目标；`researchhub-v02-concept.png` 用于记录页与手机采集的布局参考。

快捷创建只显示记录类型、标题、目标、可选父记录，按钮“创建并继续”。后续记录页按工作方式分组；参数按冻结 manifest 批量录入，空值保留 null；高级字段折叠。星标是独立操作，有 accessible name 和 pressed state；阴性结果与运行状态始终分开。手机采集使用页面/分步表单，观察、相机输入与保存易于触达。

数据管理位于项目导航与设置，归档/恢复使用普通按钮；项目移入回收站需要输入名称。审计与活动分开，活动隐藏操作不得调用删除审计。分页和查询状态可读，加载/失败保持真实反馈。

概念图的示例科学数值和单位不作为数据来源；实际单位由 manifest 与科研记录决定。图中“重新分析”不属于已授权自主分析能力，不生成此按钮。所有真实交互为代码组件；图示日期和样本不植入用户项目。最终浏览器比对覆盖中文文案、列表密度、配色、表单层次、44px 控件和移动布局。
