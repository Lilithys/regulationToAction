# Regulatory Change-to-Action：总体架构文字说明

更新：2026-09-12。最高依据是 `require.md`；`logic A-B-C` 和 `Integration-Guide.md` 是设计参考。以下描述的是目标架构，不代表已经全部实现。

## 一、围绕案件和问题工作

系统接收一个监管来源更新，先核对来源身份、版本、发布时间、适用日期及引用，创建一个案件。没有旧版原文就记录“暂时不能比较版本”；演示回放明确标记为回放。案件保存当前目标、已知事实、未决问题、发现、计划版本及审计记录。

协调 Agent 根据这些状态决定下一步。例如，已知机构在范围内、但某项业务事实未知时，可以继续检查控制文本和条件性成本，只暂停依赖未知事实的判断。发现矛盾、收到答复或改变约束时，回到需要更新的调查环节，不必从第一步全部重跑。工具调用次数、重复调查和重规划次数有上限。

## 二、四个角色的职责

**案件协调 Agent** 负责维护目标与进度，给专家分配具体调查任务，汇总冲突，选择对决策有影响的问题，并决定继续调查、请求人工输入还是形成待审核建议。它不能批准自己的法律解释或关闭任务。

**法规分析 Agent** 根据实际条文和引用，解释义务、机构/活动范围、时间条件及例外，调用来源与版本检查工具。输出明确区分原文、模型解释、适用性候选判断和已审核结论；无法确认的部分留作未决事项。

**银行调查 Agent** 检索产品、组合、政策、控制、流程和系统，判断某个控制究竟支持哪一项要求、覆盖什么范围。预填 ID 只提供线索。它需要区分“没找到控制”“已确认没有”“有设计但缺实操证据”，并追踪相关数据、供应商和职责。收到新证据后，可以带着新的审查任务再次调用它。

**响应规划 Agent** 根据已识别的缺口、业务范围、预算和期限组织行动方案。现有 manual/automated/hybrid 是估算模板；模型可以提出组合、缩小范围或分阶段实施，但必须说明范围、假设、依赖和未决确认，并交给计算工具重算。两条要求的方案不能被包装成覆盖全部八条要求。

四个角色可以共用一个模型服务，在一个 Python 进程中运行。区别在于各自的任务、上下文、可调用工具和完成条件；并不要求四个常驻服务，也不要求每个案件固定调用四个角色。

## 三、LLM、代码和人的边界

LLM 选择调查路径、提出语义候选判断、追问、解释发现、组合方案。代码负责记录查询、关系遍历、引用解析、金额与分母计算、日期选择、预算/产能检查、输入验证和状态转换。SQLite 持久化案件及版本；baseline 文件保持只读，答复形成带来源和时间的运行时事实补丁。

人负责关键法律解释、事实确认、方案取舍、责任接受及证据审核。批准必须绑定具体版本；修改范围或关键证据后，受影响的批准失效。普通答复不等于批准，否定或取消不能变成确认，模型也不能自行生成真人签字。

暴露度首先显示金额、份额、覆盖与缺失事实。行业代理应明确标记；字段质量不等于风险判断正确概率。AHP 只是可选的方法配置，主线不要求现场起草与审核矩阵。

## 四、一条完整的演示路径

1. 接收 ESG 监管候选，展示原始出处和版本限制，建立案件。
2. 法规分析与银行调查围绕实际问题工作，识别新授信筛查与存量持续监测的范围差异。
3. 系统先检索，再提出一个影响方案的业务问题，保存答复的单位、分母、范围、来源和日期。
4. 答复形成事实补丁，更新依赖它的发现与估算，保留之前的结果和变更原因。
5. 规划 Agent 提出可比较的方案，由工具计算建设成本、运行成本、三年 TCO 和期限条件。
6. 用户增加“建设预算不超过 €90k”等约束，触发有依据的重规划；不把未知产能当作充足。
7. 人选择具体范围的方案，确认负责人、接受责任、内部目标日期、依赖及验收条件。已过的法规日期仍如实保留。
8. 提交不合格证据时，系统指出具体缺项并退回；完整的模拟证据经过内容检查、任务测试和人工审核后，才可关闭对应窄任务。

关闭一项任务，不等于整家银行已符合全部 ESG 要求。演示中的 synthetic 事实、模拟证据、离线回放和真实模型调用需要分别展示。

## 五、当前实施状态

第一批 M1 完成 T01–T06：统一数据根目录与重建保护；拆分范围/日期/演示优先级/审核状态；修复 AHP 确认和版本绑定；按要求评价控制设计与操作证据；纠正治理链接和盲映射正文丢失；默认展示稳定分组的组合事实。

M2 完成 T09–T14、T16：`agent/case_store.py` 用 SQLite 持久化 Case/Finding/Question/GapAssessment/PlanVersion/Action/Evidence 及哈希链审计事件；四个角色（案件协调、法规分析、银行调查、响应规划）共享同一个受权限、预算（`RunBudget`）与"已观察引用"约束的工具循环（`agent/tool_runtime.py`）；业务访谈—答复—事实补丁—选择性失效—重算链路可通过显式回放（`ReplayClient`）或真实模型运行并从中断处恢复。

M3 完成 T15、T18：响应规划 Agent 新增 `find_roles`（按 RACI 提出有理由的负责人候选，而非直接断言）、`propose_plan`（把响应模板范围收窄到本次实际调查涉及的具体要求，禁止声称覆盖模板未涉及的其余条款，成本数字始终来自 `evaluate_option` 而非模型自报）、`propose_action`（起草任务，负责人必须来自已观察的 `find_roles` 候选，内部目标日期与原法规到期日期分开记录各自的临近/逾期状态）。责任接受是单独的 `accept_action`，只存在于 `CaseStore`，刻意不通过 `InvestigationTools`/`PERMISSIONS` 暴露给任何 LLM 角色，需经 `agent/run_case.py accept` 由人工以匹配的角色显式调用。`demo-replay` 已完整跑通一次真实的方案起草—任务指派—人工接受全流程（`agent/test_m3_planning.py`）。

M4 完成 T19–T20：`agent/evidence_intake.py` 新增 `submit_evidence`（人工/服务端提交，校验证据槽位属于该 Action 自己声明的 `required_evidence`、类型匹配、文件哈希；不属于声明范围或类型不符的"伪ID"提交直接拒绝，不会写入案件）与 `evaluate_closure`（只读，把当前 Action/Evidence 翻译为 `dataset_runtime.closure_gate()` 需要的形状后原样调用——`closure_gate` 本身完全未改动，继续复用已测试过的确定性判断）。`propose_action` 现在必须声明 `required_evidence`（每项证据的类型与用途），响应规划角色起草任务时一并给出。银行调查角色新增 `read_evidence`/`review_evidence`：先读取哈希校验过的证据原文，再给出 plausibly_responsive/unrelated_content 等内容判断——这只是一条provisional 的内容线索，既不代表已收集，也不代表人工已复核或可以结案，"无关文档"和"缺少测试文件"因此是两种不同、都会被挡住的失败路径。`CaseStore` 新增人工专属的 `decide_evidence`（verified/rejected；拒绝不删除历史，可重新提交再判定）与 `close_action`（只有确定性证据闸门判定 can_close 才允许结案，写入"仅此窄任务，不代表整条 ESG 要求或法律合规获得批准"的范围声明）——两者与 `accept_action` 一样，刻意不通过 `InvestigationTools`/`PERMISSIONS` 暴露给任何 LLM 角色。已结案的 Action 若之后证据被追溯打回，会经既有的依赖失效机制自动回到 stale。`agent/run_case.py` 的 `demo-replay` 已真实跑通"起草→接受→提交不合格证据→内容判断为无关→人工拒绝→重新提交合格证据→内容判断为相关→人工确认→两项证据齐全→结案"的完整链路。

M5 完成 T21–T22：工作区里没有 Integration-Guide.md 提到的 `frontend_app`（T21 自己的验收就预见了这种情况），新增的 `agent/view_adapter.py`/`agent/api_server.py` 因此没有照搬那份基于旧五阶段 A/B/C/D 流水线的前端契约，而是直接基于当前 Case/Finding/Question/GapAssessment/PlanVersion/Action/Evidence 模型重新设计，只保留"待办按 section 分类、resolve 时服务端必须重新校验"这两条仍然适用的思路。`view_adapter.py` 提供只读投影（案件概览、调查摘要、方案/行动、含版本历史的证据、审计日志）和 `pending_queue`（把开放问题/待接受行动/待裁定证据/可结案行动统一列成带 `section`（fact/response/evidence/closure）标签的待办队列），`resolve_queue_item` 按 section 分发到 `answer_question`/`accept_action`/`decide_evidence`/`close_action`——全部复用既有、已测试过的方法，这一层不重复任何业务判断。`api_server.py` 是纯标准库 `http.server`（单线程 `HTTPServer`，不是 `ThreadingHTTPServer`：sqlite3 连接默认不能跨线程用，为此把 `case_store.py` 的连接加上了 `check_same_thread=False`，让服务端可以在与创建连接不同的线程里跑）。`agent/test_m5_interface.py` 19 项测试中有 5 项启动真实 HTTPServer 用 `urllib` 发真实请求，另外用 `curl` 起了一个真实 CLI 子进程验证过。

LLM provider 从只支持 DeepSeek 扩展为可选 OpenAI：新增 `OpenAIToolClient`（`agent/llm.py`），把 OpenAI Chat Completions 的 tool_calls/finish_reason/usage 形状翻译成与 `AnthropicToolClient` 相同的归一化 text/tool_use block，`tool_runtime.py` 完全不用改。`LLM_PROVIDER` 环境变量选择 provider（默认 `anthropic`，覆盖 DeepSeek 这类兼容端点；设成 `openai` 才走新路径），`configure_llm.py --provider {deepseek,openai}`。已用假 key 真实打到 OpenAI 线上端点确认收到结构化 401（不是参数错误），但尚未用真实有效 key 验证过完整一轮。

T23–T25（重建回归评测、真实 LLM 端到端评测、最终演示收尾）尚未实现，T07–T08 的来源监测与最小补充材料仍待补齐，按 `TODO.md` 后续里程碑推进。
