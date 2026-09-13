# Regulatory Change-to-Action — 实施 TODO

更新：2026-09-12。用户已接受 [架构与代码 Review](research/architecture_review_2026-09-11.md) 的方向。本清单替代旧 A/B/C/D 实施顺序；[旧 TODO](research/TODO_before_architecture_reset_2026-09-11.md) 仅作历史记录。

最高依据为 [require.md](require.md)。本轮目标：**一个 SME ESG 案件的来源变化 → 调查 → 关键事实访谈 → 控制缺口 → 约束下重规划 → 责任人/期限 → 证据审核闭环。**

勾选表示完成；“方向确认”及第一批 T01–T06 已完成，其余按勾选状态推进。P0 是扩大 LLM 自主性前必须修复的问题；P1 是完整 demo 必需能力；P2 为主线完成后再考虑的扩展。

## 已确认的方向

- [x] 四个 LLM 角色：案件协调、法规分析、银行调查、响应规划；各有任务、上下文和工具，可共用模型和单个 Python 进程。
- [x] AHP 移到可选方法配置，不再是主流程强制交互。
- [x] LLM 负责调查、候选语义判断、提问、方案组合和重规划；代码负责计算、验证、权限和状态门槛；人负责关键法律解释、资源/责任接受和证据批准。
- [x] 缺事实只阻塞依赖该事实的结论或动作，其他调查和条件性比较继续。
- [x] SME ESG 做完整闭环；IPS、DORA、FRTB 保留辅助验证。
- [x] 以实际数据为基础，只补有明确用途的材料，不为凑分数或预设答案修改事实。
- [x] 暂按约七分钟组织交互演示，可随最终展示要求调整。

## 第一阶段：修复基础错误与数据合同（P0）

- [x] **T01 — 统一数据入口，保存可复现基线。**
  统一 runtime、生成脚本、验证器和文档的 dataset root，解决根目录 calibrated_v0_2 与 data/calibrated_v0_2 分离的问题。保存输入清单/hash，区分 baseline、答复、方法配置与运行输出；将经审核的手工修复同步到迁移规则，保留已有人工矩阵记录。
  **验收：** 重建和运行使用同一版本，不悄悄产生第二套数据或丢失修复/审核记录。

- [x] **T02 — 修正适用性模型和边界。**
  拆分 legal_scope、temporal_status、demo_scope、review_status。修复未知地区/空机构类型、新产品预过滤、EU 地域匹配和未来日期提前返回；区分机构级义务与产品地域条件。将 SNCI 放入日期选择逻辑，统一要求与 change register 的日期。记录 ID 与 JSON Pointer 分开表示。
  **验收：** 未知不等于不适用；新产品不会消失；日期不绕过范围检查；不会用“US 位于 EU”作理由；聚合输出保留 provisional 限定。

- [x] **T03 — 修复人工确认与可选 AHP 路径。**
  只有明确确认才能写入 confirmed；取消/否定/无效输入不能批准。先验证 pair 完整性、唯一性、维度、正有限数、比例范围和互反关系，再计算 CR。起草时提供条文上下文；复用配置时核对要求、方法和范围版本。
  **验收：** n/skip 不确认；空表、缺 pair、非法数值被拒绝；旧配置不跨版本无提示复用；默认主流程无需审核矩阵。

- [x] **T04 — 按具体要求判断控制覆盖与证据。**
  区分 mapping_support、design_coverage、operating_evidence。无链接先调查，不直接判 missing；按要求的范围、频率、期限等维度评价控制联合覆盖，解析实际 evidence 记录。
  **验收：** 伪 evidence ID、空 coverage 不能得到 evidenced；授信准入、存量监测、十年视角不机械共享一个缺口理由；只有充分搜索或明确否定证据才确认能力缺失。

- [x] **T05 — 重审治理映射与盲评输入。**
  重审 onboarding screen 与 CREDIT-MONITORING、LONG-HORIZON 的链接，逐条保存语义支持范围；不以拆分血缘或双向 ID 对称代替证明。修正 mapping 视图，保留政策 statement 正文，只移走预填答案关联。
  **验收：** 每个保留链接有依据；不为消除 missing 而补造控制；盲映射既不读取答案，也不丢失必要证据。

- [x] **T06 — 调整暴露度、数据质量与代理表达。**
  主输出展示金额、份额、数据覆盖、代理依赖和未决事实，停止把字段完整度称为风险判断正确概率。修复未来日期/地理颗粒度问题；为保留评分定义稳定业务单位、方法版本和用途，处理 cohort 拆分敏感性及重复使用余额信息。
  **验收：** 不再出现“关键风险全是代理，却展示判断置信度100%、无数据缺口”的误导；改变存储分组不改变应保持稳定的组合结论。

## 第二阶段：来源与最小补充数据（P1）

- [ ] **T07 — 建立一个来源的监测、版本和回放入口。**
  登记选定 ESG 来源的状态、版本、发布/适用日期和引用；取得可合法获取的官方快照并保存 hash。实现单一来源的候选更新检测、去重和 intake，由法规 Agent 判断是否实质相关；准备明确标记的离线事件回放。
  **验收：** 有真实两版时能展示具体差异；缺旧版时返回不可比较，不编旧文；咨询稿与最终稿分开标状态；回放不宣称现场实时检测成功。

- [ ] **T08 — 补齐最小调查与证据材料。**
  优先复用现有治理文本，只在取证确实不足时补少量 synthetic 材料。明确能源数据覆盖等问题的总体、单位和分母。准备一个不合格证据样本和一个针对窄任务的完整模拟证据包，保留 before/after 数据。
  **验收：** 新增假设、模拟答复与证据均有标记；每份材料都对应具体判断/验收条件；不批量补齐所有控制来消除 demo 缺口。

## 第三阶段：案件状态与工具运行基础（P1）

- [x] **T09 — 定义并持久化案件对象。**
  落实 Case、Finding、Question、GapAssessment、PlanVersion、Action、Evidence、AuditEvent。默认单进程 Python + SQLite 保存运行状态，原始文件作为只读 baseline；区分场景日期、快照日和实际运行时间。
  **验收：** 重启可恢复；发现和计划可追溯输入版本；不同案件的行动 ID 不冲突；已解决问题和被替换计划仍保留历史。

- [x] **T10 — 建立受约束的 LLM 工具循环。**
  扩展现有 adapter，支持工具调用、结构化输出验证、有限重试/超时、调用预算与日志。专家有明确工具权限，应用服务校验并写状态；区分等待、失败和完成，限制无进展循环。
  **验收：** 模型根据工具观察选择下一步；错误不丢案件；不能自行批准、改 baseline 或执行任意生成代码；记录动作和简短依据。

- [x] **T11 — 暴露统一查询、关系和计算工具。**
  提供来源/治理文本检索、记录查询、引用解析、流程/系统/数据/供应商关系遍历、覆盖率计算、角色查找、成本和期限检查。小语料先用字段/关键词检索。
  **验收：** 工具返回结构化结果、来源与缺失状态；不把整份工作区或评测答案放入上下文；金额、日期和覆盖率由代码计算。

## 第四阶段：四个协作角色与业务访谈（P1）

- [x] **T12 — 案件协调 Agent。**
  根据目标、发现、未决问题和用户约束派发专家任务、选择下一步、汇总结果；允许补充调查和依赖允许的并行，管理调查/重规划预算。
  **验收：** 不同证据触发不同路径，不是固定顺序调用四个函数；任务边界清楚，无重复调查或无界互聊。

- [x] **T13 — 法规分析 Agent。**
  自主读取需要的原文、版本和交叉引用，提出原子义务、范围/日期/例外解释和缺失证据，调用引用/版本检查工具。
  **验收：** 关键解释有真实出处；区分原文、机器解释和审核结论；来源不足时明确返回不足。

- [x] **T14 — 银行调查 Agent。**
  围绕要求查询产品、组合、治理文本和运营关系，提出候选映射与缺口；区分没找到、已确认没有、已有设计但缺实操证据，按发现继续追查。
  **验收：** 去掉预填控制链接仍能调查相关文本；解释 onboarding 与 existing book 的差异，并指向相关流程、系统、数据和职责。

- [x] **T15 — 响应规划 Agent。**
  从实际 gap/scope 组合任务，以现有三方案为模板提出2—3个候选，必要时提出分阶段方案；估算须有依据、区间和确认人，调用计算工具比较并解释未决条件。
  **验收：** 缺口变化影响任务范围；两条要求的方案不会声称覆盖八条；模型不编最终 TCO，不把估算当已批准资源。

- [x] **T16 — 接通业务访谈与恢复。**
  先检索，再选择对决策有影响的问题；保存负责人、答案、单位/分母、来源和时间。答复形成运行时事实 patch，使依赖它的发现/计划失效并重算；模拟答复使用显式 fixture/replay 模式。
  **验收：** 至少一次业务问答导致有依据的结果更新；不覆盖 baseline；不相关结果无需重算；剩余未知不被补成确定值。

## 第五阶段：可执行方案与证据闭环（P1）

- [x] **T17 — 参数化成本工具，接入约束重规划。**
  接收 scope、workload、方案假设、预算和交付约束；保留原三方案计算作回归基线。区分建设成本、运行成本、三年 TCO 与任务成本，检查范围、重复计费和未决产能。
  **验收：** 新增“建设预算≤€90k”等假设约束可触发超预算标记与重规划；分阶段方案重新计算，不直接叠加整套 TCO；未知损失/收入/产能不按零处理。

- [x] **T18 — 明确责任、期限、团队产能和依赖。**
  按职责、流程归属和 RACI 提出有理由的 owner/A/R，由人确认或修改。任务具备步骤、内部目标、原法规日期、依赖、交付接受和验收条件；分开负责人额度与交付团队产能，避免资源重复承诺。
  **验收：** 至少一个任务完成指派和接受；已过的法规日期不被改写；能区分当前逾期与补救目标能否达到。

- [x] **T19 — 实现证据提交与内容检查。**
  保存文件、hash、类型、scope、任务归属和时间；银行调查角色在新的证据审查任务中检查内容，调用任务专属覆盖/测试工具。内容判断、完整性 gate 和人工批准分开。
  **验收：** 无关政策、缺测试文件和伪 ID 均不能结案；不合格证据有具体缺项解释；完整模拟证据能进入窄任务的人工审核。

- [x] **T20 — 实现批准、执行、返工与结案状态机。**
  明确定义 draft、待责任接受、执行中、证据提交、测试/审核、已验证等状态及退回路径。批准绑定具体方案/证据版本，检查责任、期限、依赖和证据；关键变更使旧批准失效，状态写入与审计一致。
  **验收：** 拒绝不会通过，重复请求不重复指派/关闭；窄任务闭环不等于全部 ESG 要求或法律合规获批。

## 第六阶段：界面与交互（P1）

- [x] **T21 — 接入当前前端，建立视图适配层。**
  取得并核对当前前端源码/接口，处理工作区缺少 frontend_app 的情况；把案件映射为事件、调查摘要、问题队列、方案和任务卡。五阶段卡片只作展示，不决定后端执行顺序。
  **验收：** 能显示部分完成、等待、失败、返工和计划版本；展示 provisional/模拟标记、引用和真实工具活动，而非仅展示分数。

- [x] **T22 — 接通交互 API 与审计查看。**
  实现案件读取、问题答复、约束更新、计划选择/批准、责任确认、证据提交和状态查询；服务端验证类型、范围与权限。保留原建议、修改理由和旧版本；AHP 放入可选方法入口。
  **验收：** 主线操作能从界面完成并恢复；按钮不能绕过后端校验；用户可追踪一项事实如何影响计划和行动。

## 第七阶段：行为验收与演示收尾（P1）

- [ ] **T23 — 重建回归和行为评测。**
  将 [反例探针](research/review_probes_2026-09-11.py) 转为正确行为断言，修复浅复制 fixture 污染。覆盖未知产品/地区、无映射、伪证据、版本变化、cohort 粒度、答案隔离、预算变化、事实更新、拒绝审批、重启和重复提交。
  **验收：** 不以“至少一个 high”“无链接就 missing”证明质量；分别报告通过/失败/跳过；检查上游证据变化是否导致合理的任务变化。

- [ ] **T24 — 运行真实 LLM 端到端评测。**
  验证当前 provider 的工具调用、结构化输出和四角色协作；记录调用、耗时、恢复、引用支持、问题价值和任务覆盖。使用不同事实/预算/证据的小型场景集，离线测试与显式回放作为补充。
  **验收：** 真实模型至少完成一轮调查—问答—重规划—任务—证据审核；缓存零调用、fixture 检查、确定性测试与模型表现分别报告，不强制唯一工具顺序。

- [ ] **T25 — 复演 demo 并更新交接文档。**
  编排来源/条款 → 控制范围差异 → 关键问题 → 新约束 → 修改计划 → 指派 → 拒绝不合格证据 → 合适模拟证据进入审核。更新 README、架构、Integration Guide 的参考地位、运行/重置/回放命令和已知限制，保留辅助监管回归结果。
  **验收：** 约七分钟主线稳定完成，不需现场改 JSON 或重新起草 AHP；至少展示一个新信息触发的真实决策变化。

## 依赖与建议开工顺序

| 里程碑 | 任务 | 退出条件 |
|---|---|---|
| M1：可信基础 | T01—T06；同步整理 T07—T08 | 关键反例修复，数据/日期/覆盖合同一致 |
| M2：能调查、追问、恢复 | T09—T14、T16；使用 T07—T08 的材料 | 案件能调用专家查证、询问业务事实并恢复 |
| M3：能据约束改变计划 | T15、T17—T18 | 方案由实际缺口产生，可重规划并明确指派 |
| M4：能审核证据 | T19—T20 | 窄任务具备可审查的成功和拒绝路径 |
| M5：能稳定展示 | T21—T25 | UI、真实模型、回归与演示脚本通过 |

第一批建议处理 **T01 → T02/T03 → T04/T05 → T06**。来源/材料整理可同步推进；T23 的相应回归随开发补上，不等最后才测试。前端适配可在 T09 合同明确后启动，最终联调等待实际行为就绪。

## 暂缓扩展（P2）

- [ ] 四个监管主题均实现完整深度流程。
- [ ] 大规模监测、多监管连接器和生产调度。
- [ ] 完整 CAP 本体、大行动目录和判例相似度检索。
- [ ] 生产级气候模型、概率置信度校准和模型参数微调。
- [ ] 图数据库、向量数据库、分布式多 Agent 服务与复杂调度框架。
- [ ] 自动对外任务/通知集成和生产级权限管理。

这些扩展在主线验收后，根据实际数据和评测价值重新排序。单一来源 intake、引用、合资格审核、任务和证据闭环仍属本轮必做；无人审核的法律结论批准和闭案不作为扩展目标。

## 2026-09-12 实施记录

**最新请求控制复核：** 用户已确认具体案件外发，随后受限恢复共 12 次 API 请求、9 次成功响应、178.322 秒；收到明确的 `429/rate_limit_exceeded` 和 10000-token 限流头，两次等待后重试成功。发现并修复单轮 8 个工具结果导致本地上下文预算超限的问题，OpenAI 现单轮至多一个工具。新增主动 TPM 预留、重启恢复近期预留、预算耗尽立即停止；主动节流尚仅本地验证。当前全量 agent 212/212、scripts 最近一次 24/24 通过。T24 仍未完成：实际运行只有协调角色检索，尚无专家委派、正式 Finding 或业务问题。下一步需修复协调职责和调查检查点，减少重复检索。详见 [请求控制报告](research/request_controls_2026-09-12.md)。另外，T17 预算尚未贯通 Agent/API，T21/T22 尚无实际前端及完整启动/恢复/约束接口，之前勾选仅能代表部分实现，不能视作这些任务全部验收完成。

M1（T01–T06）完成。73 项 agent 测试、14 项 runtime/重建测试及两套数据校验通过；离线开发评测 12 通过、2 跳过。真实 LLM 调用为 0，不计作 T24。详见 [M1 实施报告](research/m1_implementation_2026-09-12.md) 与 [文字架构](docs/architecture.md)。T23 的 M1 反例已加入，其余访谈、重规划、重启和状态机测试随对应能力实现。下一批进入来源/材料准备及 M2 案件与工具运行基础。

M2（T09–T14、T16）与 M3（T15、T17–T18）完成，此前漏勾选一并补上。`agent/case_store.py`/`tool_runtime.py`/`investigation_tools.py` 落实持久化案件对象、受权限与预算约束的工具循环、四角色协作与业务访谈-答复-选择性失效-重算-恢复；`dataset_runtime.evaluate_option` 把成本工具参数化为 scope/population/budget（`calculate_options` 保留为回归基线，逐位数值不变）；新增 `find_roles`/`propose_plan`/`propose_action`（响应规划角色）与人工专属 `accept_action`（刻意不经 `InvestigationTools`/`PERMISSIONS` 暴露给任何 LLM 角色）。`agent/test_m1_boundaries.py`+`test_m2_investigation.py`+`test_m3_planning.py` 共 75 项、`scripts/` 24 项测试及离线评测 12 通过/2 跳过全部通过；`agent/run_case.py demo-replay` 后接新增的 `accept` 子命令，已用真实 CLI 调用跑通一次方案起草→任务指派→人工接受的完整链路（含法规到期日期已逾期、内部目标日期仍在未来的正确区分）。真实 LLM 调用仍为 0，T24 未开始。下一批建议 T19–T20（证据与结案状态机），T07–T08 的来源/材料仍待补齐。

M4（T19–T20）完成。新增 `agent/evidence_intake.py`：`submit_evidence`（人工/服务端提交，校验 evidence_slot 属于该 action 自己声明的 `required_evidence`、类型匹配、文件哈希，伪 ID 与类型不符均直接拒绝）、`evaluate_closure`（只读，把当前 Action/Evidence 翻译成 `dataset_runtime.closure_gate()` 需要的形状后原样调用，`closure_gate` 本身未改动一行）。`propose_action` 新增 `required_evidence` 参数，由响应规划角色在起草任务时一并声明具体证据类型。`investigation_tools.py` 新增银行调查角色工具 `read_evidence`/`review_evidence`（先读原文哈希校验的证据文本，再给出 plausibly_responsive/unrelated_content 等内容判断，绝不代表已收集、已人工复核或可结案）与全角色只读工具 `check_closure`。`case_store.py` 新增人工专属 `decide_evidence`（verified/rejected，拒绝不覆盖历史，可重新提交再判定）与 `close_action`（只有 `evaluate_closure` 判定 can_close 才允许结案，写入"仅此窄任务，非整条 ESG 要求或法律合规批准"的范围声明）——两者均刻意不经 `InvestigationTools`/`PERMISSIONS` 暴露。已验证结案后若证据被追溯打回，受影响 Action 会经既有 `_invalidate` 机制自动回到 stale（这一步排查中发现并修复了一个真实 bug：`close_action` 最初把依赖键写成短 slug 而不是完整的 `action_key::slot` 复合键，导致该失效机制形同虚设，测试 `test_verified_action_becomes_stale_if_evidence_is_later_rejected` 专门覆盖这条路径）。新增 `agent/test_m4_evidence.py` 35 项测试，全部针对真实校准数据；agent 全量 110 项、`scripts/` 24 项、离线评测 12 通过/2 跳过均通过。`agent/run_case.py` 新增 `submit-evidence`/`decide-evidence`/`close-action` 三个 CLI 子命令，`demo-replay` 已扩展为真实跑通"起草→接受→提交不合格证据→内容判断为不相关→人工拒绝→重新提交合格证据→内容判断为相关→人工确认→两项证据齐全→结案"的完整链路（`materials/esg_demo/` 新增 `unrelated_policy.synthetic.txt` 不合格样本与 `control_design.synthetic.txt`/`control_effectiveness_test.synthetic.txt` 合格样本，对应 T08 遗留的证据材料缺口）。下一批建议 T21–T22（前端/交互 API），T07–T08 的来源监测材料仍待补齐。

T21–T22 完成，另加 LLM provider 从 DeepSeek 换到可选 OpenAI。工作区确认没有 `frontend_app`（Integration-Guide.md 提到的静态模拟前端不在这份工作区里）——T21 自己的验收就预见了这种情况，因此新增的视图层不是去套用 Integration-Guide.md 里那份基于旧 A/B/C/D 五阶段流水线的 `STATE.events/queue` 契约（字段对不上现在的 Case/Finding/Question/GapAssessment/PlanVersion/Action/Evidence 模型），而是直接基于当前真实对象模型重新设计，只保留"待办按 section 分类、resolve 时服务端必须重新校验"这两条仍然适用的思路。新增 `agent/view_adapter.py`：只读投影（案件概览、调查摘要、方案/行动、证据含版本历史、审计日志），以及 `pending_queue`（把开放的 Question/草稿 Action/待裁定 Evidence/可结案 Action 统一列成带 `section`（fact/response/evidence/closure）的待办队列）和 `resolve_queue_item`（按 section 分发到 `answer_question`/`accept_action`/`decide_evidence`/`close_action`，全部复用已测试过的方法，不重复业务逻辑）。新增 `agent/api_server.py`：纯标准库 `http.server`（不引入 Flask/FastAPI），单线程（`HTTPServer` 而非 `ThreadingHTTPServer`，因为 sqlite3 连接默认不能跨线程用；也因此把 `case_store.py` 里 `sqlite3.connect` 加上了 `check_same_thread=False`，好让服务端可以在与创建连接不同的线程里跑 `serve_forever`），路由：`GET /api/cases/:id`、`/investigation`、`/plans`、`/evidence`、`/audit`、`/queue`，`POST /api/cases/:id/queue/:item_id/resolve`、`POST /api/cases/:id/evidence`（证据文件走 base64 JSON，不用 multipart）。新增 `agent/test_m5_interface.py` 19 项测试，其中 5 项启动真实 HTTPServer 用 `urllib` 发真实 HTTP 请求（含一次由此暴露、随即修复的真实 bug：后台线程跑 `serve_forever()` 时 sqlite3 报"跨线程"错误）。agent 全量 146 项、`scripts/` 24 项、离线评测 12 通过/2 跳过均通过；另外用 `curl` 起了一个真实 CLI 子进程验证过。

LLM provider：新增 `OpenAIToolClient`（`agent/llm.py`），复用与 `AnthropicToolClient` 相同的 `generate()` 契约，把 OpenAI Chat Completions 的 tool_calls/finish_reason/usage 形状翻译成 `tool_runtime.py` 已经在用、会写入审计日志的同一套 text/tool_use 归一化 block，`tool_runtime.py`/`investigation_tools.py`/`roles.py` 因此完全不用改。`LLM_PROVIDER` 环境变量选择 provider（默认 `anthropic`，同时覆盖 DeepSeek 这种 Anthropic-Messages-API 兼容端点；设成 `openai` 才走新路径）。`configure_llm.py` 新增 `--provider {deepseek,openai}`。已装好 `openai` 3.13.0 包；新增 `agent/test_llm.py` 17 项测试（消息/工具 schema 翻译、响应归一化，全部 mock，不需要真实 key）全部通过。用一个假 key 真实打到了 OpenAI 的线上端点，收到结构化的 401 AuthenticationError（不是参数校验错误），说明模型名/请求体形状是对的；**没有用真实有效 key 跑通过**，跟 DeepSeek 当年那次不一样，第一次真实调用如果报参数错误，处理方式应该和当年调 DeepSeek 时一样——照实际报错改，不是照猜。
