# Sprint3B Implementation Plan

> 使用 superpowers:subagent-driven-development；每任务一个实施worker，先规格再质量审查。用户已明确授权普通细节连续推进，设计复审不重复请求人工许可。

**Goal:** 同一合成项目的Browser/PC独立节点经原QA Relay真实双向同步Run/Note/星标。
**Architecture:** 3B独立入口/IDB与PC QA Domain+Kernel+Outbox；冻结v1和显式v2；标准浏览器密码与严格HTTPS。
**Tech Stack:** React/esbuild/Playwright Chromium/WebCrypto/@hpke/core；Python/FastAPI/SQLAlchemy/隔离PostgreSQL/既有Relay。

## 1. A1版本契约
- [x] 新v2固定向量先RED：星标仅(2,2)支持，混合版本/未知字段拒绝，旧v1 unchanged。
- [x] 修改sync protocol Python/TS pure core、Kernel物化按版本、secure envelope Python/TS/公共Relay版本分派与内外绑定；suite不变。
- [x] ADR-029及协议追加说明；Python/Node/v1+v2/crypto回归；两阶段审查后提交。


A1规格与质量独立审查PASS；真实QA PG回归132PASS。提交RH028。

## 2. A2独立节点及因果工作区

A2a已完成并两阶段复审PASS（RH029）：3314/storage adapter/专门星标/稳定转换/字段绑定预览。A2b仍需PC独立服务、真实项目加入与显式3A导入，不能将A2a计为G1完成。
- [ ] 创建受限PC QA API/ResearchReadService/Domain命令与Outbox，复用展示UI；独立3B origin/build/profile/IDB。
- [ ] 项目绑定/公开能力与pin材料，稳定adapter mapping、连续父链、单击星标与dirty隔离，显式3A导入。
- [ ] 真实UI+IDB/QA PG验证，保护3A测试，两阶段审查提交。

## 3. B浏览器正式安全与加入
- [ ] 实际浏览器Ed/X/HPKE/AES/SHA、Python双向vectors、独立key IDB、nonce预约/缓存状态机负例。
- [ ] 实现原配对challenge/SAS/confirm/HPKE grant和完整chain pin，当前epoch baseline取得；非空旧历史阻塞。
- [ ] 窄CORS/OPTIONS/CSP与独立Linux信任环境；实际CA/hostname/proof/signature/AAD拒绝，既有ingress不绕过。
- [ ] 安全规格/质量复审与exact版本记录，前置满足才进入网络业务。

## 4. C真实传输和冲突
- [ ] Browser↔Relay↔PC双向，persisted claim/receipt/cursor，签名peer应用回执新契约。
- [ ] Browser本轮DAG/整批屏障与Python相同向量差异；三方比较与expected_heads解决；迟到冲突撤回。
- [ ] 真实PC UI/Browser操作，ACK丢失后重开重送、页失败/撤销/旧epoch、PC停消费恢复，pending/dirty保留。
- [ ] 独立复审，最小补丁后继续验收。

## 5. A–P矩阵与交付
- [ ] 真实浏览器/loopback/PG/IDB与Relay隐私扫描正对照，保留所有失败证据，不跳过/降安全。
- [ ] Windows/Linus实际平台边界、桌面/移动视口截图view_image，旧产品/安全/3A回归。
- [ ] exact implementation SHA首次CI/白名单artifact；最终独立review，SPRINT_3B_REPORT Gate/分类/启动步骤。
- [ ] 中文四段递增RH提交与远端核对；STOP，不3C/生产/标签移动。
