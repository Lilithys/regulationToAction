# Regulatory Change-to-Action：当前任务交接

更新时间：2026-09-12。工作区：`/Users/yishanma/Desktop/reguagent`。文末已追加首次真实工具调用结果；该补充更新了下文初次检查时的 T24 状态。

本记录基于当前文件检查、TODO、用户提供的真实调用结果和本轮实际测试。TODO 的勾选代表实现者此前的完成声明；是否达到端到端验收条件，需要分别核实。

## 1. 已完成修改与当前进度

最高依据为 `require.md`。主线是虚构 Northstar 银行的 SME ESG 案件：来源变化、适用性访谈、控制缺口、具备责任人与期限的计划、完成证据。bunq 仅作真实同业参考。Integration Guide 和 A/B/C 构想是设计参考，不要求原样实现。

已接受的架构方向：案件协调、法规分析、银行调查、响应规划四个 LLM 角色；代码负责计算、校验、权限和状态；人负责关键解释审核、责任接受及证据批准。AHP 可选。缺失事实只阻塞其依赖结果。其他监管主题保留辅助验证。

当前 TODO 勾选 T01–T06、T09–T22；T07、T08、T23、T24、T25 未勾选。代码已明显超出早期 M1/M2 状态，但部分勾选尚不满足完整验收。

| 部分 | 当前已存在的实现 | 验证边界 |
|---|---|---|
| M1 基础 | 唯一数据入口、可复现构建、日期/范围分离、可选 AHP、控制覆盖与证据分离、事实优先的组合表达 | 历史实施报告与当前测试可查 |
| M2 调查 | SQLite 案件、版本化对象、审计链、四角色工具循环、权限/预算、查询/引用/关系遍历、事实问答及选择性失效恢复 | 有离线测试与脚本回放；真实模型行为仍待验证 |
| M3 计划 | 参数化成本函数、候选计划/行动、RACI 角色查找、内部目标日与法规日期分离、人工接受行动 | 预算约束尚未贯通 Agent 工具与交互入口；不能视为完整重规划验收 |
| M4 证据 | 文件入库/hash、先读后评内容、人工拒绝/确认、窄任务结案门槛、版本历史、后续证据变化使行动失效 | 已有合格/不合格 synthetic 样本与回放；实质审查质量未完成真实模型评测 |
| M5 接口 | JSON HTTP API、只读视图投影、问题/行动/证据/结案待办解析 | 工作区没有可操作前端；若干主线 API 尚缺 |
| LLM 接入 | Anthropic 兼容与 OpenAI 两个 adapter、provider 选择、本地配置工具、文本 smoke test | 用户已报告 OpenAI `gpt-5` 返回 `Dublin`；这是文本连通性成功，尚非工具/多角色闭环成功 |

用户最近执行成功：

```bash
python agent/configure_llm.py --from-env --provider openai --model gpt-5
python agent/llm_smoke_test.py
# Model replied: Dublin
```

本轮仅确认 `.env.local` 存在、文件权限为 `0600`；未展示密钥。此前“工具进程看不到已 export 的 key”的情况已不应继续作为当前阻塞。不要把配置或密钥写进审计、文档或提交记录。

## 2. 未完成事项与本轮核查发现

### 首要事项

1. **T24 真实模型端到端评测**：工具调用、专家委派、引用、提问、答复后恢复、重规划和证据审查还没有本轮可核实的成功记录。文本 smoke test 与显式脚本回放要分别报告。
2. **T17 预算重规划未贯通**：`scripts/dataset_runtime.py:evaluate_option(..., budget=...)` 支持建设预算；但 `InvestigationTools.compare_costs()` 无参数，`propose_plan()` 不传预算，当前 API 也没有约束更新入口。需要保存案件约束版本、传播依赖失效、重新调用成本工具并保留新旧方案。
3. **T21/T22 只能算部分完成**：有 `view_adapter.py` 和 JSON API，没有 HTML/React/Vue 等实际前端。API 尚无创建/启动/恢复案件、更新约束、选择/批准计划等完整入口；仅答复问题并不会自动运行下一轮 Agent。T21 的“从界面完成主线”尚未实现。
4. **T07 来源不足**：已有登记事件回放、本地候选快照导入、hash/版本比较。尚无完整官方双版本材料与单一来源更新检测闭环。`live` 当前指 LLM 真调用，来源 intake 仍标记为 `registered_source_replay`，不能展示为现场实时监测成功。
5. **T08 部分材料已补**：能源覆盖答复 fixture、不相关政策、控制设计、单周期 pilot 测试样本已存在；仍需逐项核对任务 scope、验收条件与 before/after，不能把 pilot 文本当作全量组合运行证明。
6. **T23/T25 收尾**：隔离测试配置，补真实行为场景与验收记录，完成界面复演，更新 README/架构/TODO。README 目前仍称只实现 M1，已落后于代码。

### 当前已确认的测试问题

`agent/test_llm.py:LiveClientFactoryTests.test_defaults_to_anthropic` 只清空环境变量，没有隔离 `load_local_config()`；测试会读取真实 `.env.local`，因此配置为 OpenAI 后实际返回 OpenAI client，默认 Anthropic 的断言失败。这是测试隔离问题，不应靠删除用户配置或改回 provider 解决。应 mock 配置读取，并为配置加载逻辑使用独立临时 fixture。

### 后续验收时还应检查的代码边界

- `propose_plan()` 当前检查引用是否已观察，但未强制它一定来自支持该范围的 Finding/GapAssessment；测试中成本观察本身即可作为引用。引用存在不等于语义支持充分。
- `find_roles()` 提供登记的 RACI 候选，尚不等于交付团队产能、多个任务的资源冲突或依赖计划已验证。`dependency_note` 目前主要是文字。
- 交互 API 接受请求后使用服务端当前对象版本进行操作；需要客户端提交其看过的 expected version，才能拒绝对旧页面内容的批准。
- 证据上传直接把请求中的 `filename` 拼到临时目录，应在交互演示前限制为安全文件名并验证路径边界。
- `run_case.py` 默认 GOAL 偏向调查/条件性成本比较，且禁止模型自行批准/结案。完整演示需要分阶段明确目标，并通过人类专属入口完成接受与审核，不能期望默认 `start` 自动完成所有业务步骤。
- 当前 runner 每次运行默认最多 36 次模型尝试、70 次工具调用、5 次委派、180 秒、累计 160000 tokens；单次输出上限 2400、请求超时上限 35 秒。真实模型第一次失败时应查明预算、截断或协议原因，再调整；不要直接扩大所有限制。

### 本轮测试证据

本轮未调用真实模型 API，未修改业务代码或 baseline。

| 检查 | 实际结果 |
|---|---|
| `python -m unittest discover -s agent -p 'test_*.py'` | 发现并运行 193 项：185 通过、1 失败、7 环境错误 |
| 上述 1 失败 | 默认 provider 测试读取真实本地配置，见上文 |
| 上述 7 环境错误 | 沙箱拒绝 `127.0.0.1` 端口绑定；不是模型调用失败 |
| 允许本地端口后单独重跑 `test_m5_interface.ApiServerTests` | 7/7 通过 |
| `python -m unittest discover -s scripts -p 'test_*.py'` | 24/24 通过 |

因此，分别复核后 193 项 agent 测试中有 192 项通过、1 项待修；尚未完成一次修复后的全量全绿运行。TODO 中的“146 项全通过”属于旧记录。本轮没有重跑严格数据校验或开发评测；历史结果不能记为本輪新验证。

## 3. 当前代码结构

```text
reguagent/
├── require.md                         # 最高项目要求
├── TODO.md                            # 实施清单，部分勾选待校准
├── README.md                          # 当前落后于实现
├── CODEX_CONTEXT.md                   # 本交接记录
├── docs/architecture.md               # 目标架构文字说明
├── agent/
│   ├── run_demo.py                    # 旧确定性基线入口，AHP 可选
│   ├── run_case.py                    # 当前案件 CLI，live/replay 分离
│   ├── llm.py                        # Anthropic/OpenAI adapter
│   ├── llm_config.py                  # allowlist 本地配置读取/保存
│   ├── configure_llm.py               # 从终端环境导入配置
│   ├── llm_smoke_test.py              # 真实文本连通性检查
│   ├── roles.py                       # 四角色提示与职责
│   ├── tool_runtime.py                # 工具循环、委派、预算、恢复
│   ├── tool_contracts.py              # 工具参数 schema 校验
│   ├── investigation_tools.py         # 调查/访谈/计划/证据工具
│   ├── case_store.py                  # SQLite 对象、版本、审计、人工操作
│   ├── source_intake.py               # 登记来源回放/候选快照/比较
│   ├── evidence_intake.py             # 证据文件与结案检查适配
│   ├── replay_client.py               # 明确标记的脚本回放客户端
│   ├── view_adapter.py                # 展示视图及待办解析
│   ├── api_server.py                  # 本地 JSON HTTP API
│   ├── applicability.py / gap_assessment.py / exposure_esg.py
│   ├── response_design.py / evidence_closure.py
│   └── test_*.py                      # 模块、M1–M5、provider 测试
├── scripts/                           # 构建、数据加载/计算、校验、开发评测
├── calibrated_v0_2/                   # 唯一校准 baseline
├── config/                            # 方法矩阵与迁移历史
├── materials/esg_demo/                # 显式 synthetic 访谈/证据样本
├── data/                              # 原始资料、dataset skill、bunq reference
├── research/                          # 调研、review、来源审计与 M1 验证记录
├── runs/                              # 运行输出默认位置，按命令创建
└── backups/                           # 历史备份
```

## 4. 下一步建议操作

推荐顺序：**修正配置测试隔离 → 最小真实工具调查 → 答复与恢复 → 接通预算约束重规划 → 真实证据审查 → 补齐来源和前端 → 七分钟复演**。

先让一个窄案件证明真实工具链可用，成功标准是实际工具结果支撑 Findings、必要问题被保存、案件可恢复。等待业务答复是正常业务状态。不要以工具执行顺序必须等同 replay 作为验收标准。

从项目根目录运行以下命令可开始第一轮真实调查；它会调用已配置 provider 并产生 API 使用量：

```bash
.venv/bin/python agent/run_case.py --db runs/esg_live.sqlite3 start --mode live --new
```

记录返回的 `case_id`，查询和恢复都使用同一个数据库。以下 `CASE_ID` 必须替换为实际值：

```bash
.venv/bin/python agent/run_case.py --db runs/esg_live.sqlite3 show CASE_ID --audit
.venv/bin/python agent/run_case.py --db runs/esg_live.sqlite3 resume CASE_ID
```

先查看开放问题及 schema，再通过 `answer CASE_ID --file ...` 提交带来源、单位、分母、日期和 synthetic 标记的答复，随后 resume。用于虚构银行的演示答复应继续明确标为 synthetic，即使推理调用是真实 LLM。不要把示例文件包装成真实业务人员的回答，也不要由 Agent 代替人类完成关键批准。

第一轮检查重点：工具协议能否完成往返、引用是否指向实际材料、是否区分 onboarding 与 existing-book monitoring、问题是否影响后续决定、缺官方快照是否诚实报告、失败是否保留调查状态。接下来用预算 ≤€90k、不同事实覆盖率、错误/合适证据做小型场景集，并记录模型调用量、耗时、成功/失败及人工干预。

## 5. 关键文件路径与稳定约束

- 项目要求：`require.md`；实施清单：`TODO.md`；目标架构：`docs/architecture.md`。
- 设计参考：`Regulatory_Change_to_Action_Design.md`、`Integration-Guide.md`、`logic A-B-C/B-Logic.md`、`logic A-B-C/Part_C.md`。
- 数据编写规范：`data/regulatory-governance-dataset/SKILL.md`；真实同业材料：`data/bunq_reference bank/`。
- 唯一 baseline：`calibrated_v0_2/`；构建 hash：`calibrated_v0_2/calibration/build_manifest.json`；迁移历史：`config/dataset_migration_history.json`。
- 历史报告：`research/architecture_review_2026-09-11.md`、`research/market_landscape_2026-09-08.md`、`research/source_audit.md`、`research/m1_implementation_2026-09-12.md`、`research/m1_validation/`。
- 本地配置：`.env.local`，权限 `0600`，不要打印内容；当前用户已配置 OpenAI/gpt-5。`.env.example` 仅为示例。
- 默认案件数据库：`runs/cases.sqlite3`；建议真实联调隔离为 `runs/esg_live.sqlite3`。CLI 的 `--db` 放在子命令之前。
- 场景日期与研究截止为 `2026-09-08`，数据快照为 `2026-06-30`；实际运行时间另记，不得混用。
- Northstar 是虚构银行，非 SNCI；SME 组合 10000 借款人、€2300m。现有三响应模板仅覆盖 DATA-GAPS 与 CREDIT-MONITORING，不能声称解决全部八项 ESG 要求。
- 65% 能源数据答复表示 6500 已覆盖、3500 未覆盖的模拟事实；不能单凭它推断真实气候风险或自动改写自动化率/TCO。
- 模型调查完成、窄任务完成与全部 ESG 法律合规批准是不同状态；保留法律文本、解释、建议、审核结果的区分。

本轮已核对 TODO 和实现、运行上述测试并保存交接记录；尚未调整 TODO 勾选、修复代码、运行真实工具调用或构建前端。

## 最新补充：用户已运行首次真实调查

用户随后执行了 `start --mode live --new` 和 `show CASE_ID --audit`。已直接以 SQLite 只读模式检查工作区数据库，无需用户粘贴同一份输出。

- 数据库：`runs/esg_live.sqlite3`。
- 案件：`CASE-cb4fa9d654e14a34b4df0a8ea7109e56`，模式 `live`，当前状态 `failed`，revision 1。
- 实际运行：2026-09-12 12:27:33 至 12:28:11 UTC，约 38 秒。
- 6 次 API 请求尝试，3 次成功模型响应，成功响应合计记录 11275 tokens。
- 协调角色实际完成 3 次工具调用：`case_context`、两次 `search_records`；均没有工具执行错误。
- 出现一次 `APIConnectionError`，随后重试成功；之后连续两次 `RateLimitError`，重试耗尽，案件停止。
- 尚未发生专家委派，未生成 Finding、Question、PlanVersion 或 Action，因此并未到等待业务答复阶段。
- 审计 hash 链通过独立只读复核；案件、工具观察与错误记录均保留。

T24 现在应标记为“首次真实工具调用已执行，端到端未通过”。真实工具往返已得到证据，不能继续称仅完成文本 smoke test；也不能把它计为四角色协作成功。

当前审计仅记录异常类型，缺少 provider 错误 code、HTTP status、request id 和 retry-after 等信息，尚不能判断 RateLimitError 是请求/token 速率限制还是可用额度问题。下一步应记录经过 allowlist 过滤的诊断字段，区分可重试限流与不可立即恢复的额度问题，并完善预算内退避；禁止把原始请求头、密钥或完整错误体写入日志。诊断后恢复同一案件，避免反复 `start --new` 产生重复调查。本次检查未重新调用模型、未修改运行数据库或错误处理代码。

## 最新补充：请求控制已修复，真实恢复待确认

用户表示额度充足，怀疑 token 限流或上下文较短。现已完成代码修复：`agent/request_controls.py`、`tool_runtime.py` 加入安全诊断、服务端提示优先的有限退避、跨角色请求间隔、单请求预算与旧工具观察压缩；`investigation_tools.py` 默认搜索摘要并要求控制映射读取全文；`run_case.py` 增加调试预算选项。隔离了 `test_llm.py` 的个人配置依赖，replay 适配已见观察保存。

本轮 agent 全量 208/208、scripts 24/24 通过，记录在 `research/request_controls_validation/`。相同搜索由 16286 字符降至 6235 字符，候选 ID 不变；这不是实测 token 降幅。此前“192 通过、1 待修”的记录已被本次验证更新。

完整说明及待执行命令见 `research/request_controls_2026-09-12.md`。已备份原案件和代码到 `backups/2026-09-12-before-rate-controls/`。README 与 TODO 已追加最新状态；T24 不勾选完成。

**历史审批阻塞（现已解除）：** 自动审批最初拒绝该案件外发；用户随后明确回复“确认”，恢复命令已经获准执行。后续不能再把同一数据/目的地的外发确认视为缺失。本次批准的 12 次请求/180 秒预算已用于下述验证，后续运行仍应明确设置有限预算。

## 最新补充：真实恢复结果与 token 节流

- 两段恢复仍使用 `CASE-cb4fa9d654e14a34b4df0a8ea7109e56`：先 3 次 API 请求/39.777 秒，发现单轮 8 个工具结果超过本地上下文预算；然后设 `parallel_tool_calls=False`，用剩余 9 次/140 秒预算继续，实际运行 138.545 秒。
- 本轮合计 12 次请求、9 次成功响应、37855 个 provider 报告 tokens、178.322 秒。3 次 provider 错误均为 `429/rate_limit_exceeded`，限流头为 tokens=10000、requests=50；前两次按 Retry-After 等待后成功，最后一次达到请求预算后停止。
- 本地 `RequestTooLarge` 与 provider 上下文过长不同；没有收到 `context_length_exceeded`，不能声称模型上下文窗口较短。
- 当前案件仍 `failed`；hash 审计链有效。只有 SourceVersion 与 Task，专家委派、Finding、Question、PlanVersion、Action 均未产生。协调角色持续查询的行为说明任务分配/调查检查点仍需改进。
- `agent/llm.py` 新增单轮工具约束；`request_controls.py`/`tool_runtime.py` 增加 60 秒 token 预留窗口，从同一案件最近审计恢复预留，并修复调用预算已耗尽还等待重试的问题。`run_case.py` 新增 `--tokens-per-minute`，默认 0（不主动限制），下轮可按已观察头设置 10000。该节流不计其他应用的额度消耗，且尚未新发 API 验证。
- 最新全量 agent 212/212 通过；scripts 最近一次 24/24 通过。受影响模块组合测试 65/65 通过，日志在 `research/request_controls_validation/`。
- 真实记录：`live_resume.json`、`live_resume_serial.json`、`live_summary.json`；完整分析与下一步见 `research/request_controls_2026-09-12.md`。README/TODO 已更新。

下一步优先调整协调角色工具职责、专家任务边界及中途 Findings 的保存/恢复，随后验证主动 TPM 节流与真正的专家协作；不要通过无限加大调用数掩盖重复检索。完整问答、重规划、证据审核仍未完成真实模型验收。
