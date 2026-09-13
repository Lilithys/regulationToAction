# 首次真实调用后的请求控制修复

日期：2026-09-12。对应 TODO：T10、T11、T23、T24。

## 问题与证据

原案件 `CASE-cb4fa9d654e14a34b4df0a8ea7109e56` 在 `runs/esg_live.sqlite3` 中保留。首次真实运行尝试 6 次 API 请求，3 次响应成功，完成 3 次协调角色工具调用，随后连续两次 `RateLimitError` 停止。尚未委派专家或生成业务问题。原审计没有错误 code/HTTP status/重试提示，无法确定限流维度。

用户表示额度充足，怀疑 token 限流或较短上下文。这是排查方向，尚不是已验证原因。每分钟 token 限额与单次上下文上限分别控制吞吐和请求大小；应分别观察和配置。官方文档建议使用服务端 Retry-After、有限退避，并区分不能通过重试解决的额度错误。[OpenAI rate limits](https://developers.openai.com/api/docs/guides/rate-limits)、[OpenAI error codes](https://developers.openai.com/api/docs/guides/error-codes)。

原第一次搜索返回 16286 字符。改为摘要后，相同冻结数据、相同查询与候选 ID 返回 6235 字符，减少 61.7%。这只是检索结果字符数变化，不是实测 token 或费用下降比例。

## 已实现

- 新增 `agent/request_controls.py`：安全错误分类，已知错误 code 白名单、HTTP status、数值限流头、Retry-After/reset 提示、request ID 的 hash。完整错误文本、原始 headers、URL 和密钥均不写入诊断。
- 额度/账单、上下文或单次过大请求不作原样重试；暂时限流、连接或服务端错误最多重试一次。优先遵守服务端等待时间；无提示时采用带随机抖动的等待。SDK 自动重试保持关闭。
- 等待计入全局时间预算，按短间隔执行。若服务端要求的等待超过剩余预算，保留诊断并停止，不提前重试。
- 增加跨角色共享的最小请求间隔，以及单请求估算预算；每次审计记录估算输入、输出上限，成功后记录 provider 报告的输入/输出 tokens。
- 搜索默认返回带明确标记的摘要、记录 ID、引用；可用 `get_record` 获取全文。控制映射拒绝把搜索摘要当作完整读取。`detail=full` 仍支持少量针对性全文检索。
- 单请求超出本地预算时，压缩较早工具观察为明确标记的引用/记录索引，保留完整 tool call/result 对、最新观察和系统/任务指令。原文仍在审计中，可重新读取；若仍过大，则在发送 API 前停止，不悄悄裁掉最新依据。
- 显式脚本 replay 保留它已见过的测试观察，适配上下文压缩；这只是 fixture 状态，不计作真实模型记忆或推理质量。
- 隔离默认 provider 测试中的本地配置读取，修复用户创建 `.env.local` 后测试失效的问题。
- 真实恢复中发现模型单轮发起 8 次工具调用，最新结果合并后超过本地预算。OpenAI adapter 现设 `parallel_tool_calls=False`，单轮至多一个工具调用；选择工具与专家的顺序仍由模型决定。[官方参数说明](https://developers.openai.com/api/docs/guides/function-calling#parallel-function-calling)。
- 新增 `--tokens-per-minute`：按照估算输入加预留输出，在 60 秒滚动窗口内保守预留额度；各专家共享同一调度器，并从案件审计恢复最近一分钟的请求预留。单请求上限不会超过配置的 TPM。该估算并不等于 provider 的精确计量，也无法计入其他应用消耗的项目额度，服务端 Retry-After 仍有效。
- 请求次数已耗尽时立即停止，不再先等待一次无机会执行的重试；预算停止原因会出现在返回结果中。

## 验证

- Agent 最新全量：212/212 通过，含 19 项请求控制测试；本地 HTTP 测试在允许 loopback 端口的环境运行。
- Scripts 全量：24/24 通过。
- 日志：`research/request_controls_validation/agent_tests.log`、`script_tests.log`。
- 关键覆盖：错误信息不泄露、额度不重试、遵守等待时间、等待超预算停止、上下文预检、压缩不破坏协议、全文保留、摘要不可代替控制读取、请求计数。
- 保留修改前代码和案件数据库快照：`backups/2026-09-12-before-rate-controls/`。
- 单轮工具约束的 adapter 测试：17/17；请求控制/provider/调查相关测试：65/65。主动 TPM 预留仅完成本地验证，尚未用新增 API 请求验证。

## 已执行的受限恢复验证

```bash
.venv/bin/python agent/run_case.py \
  --db runs/esg_live.sqlite3 \
  --max-request-tokens 12000 \
  --max-model-calls 12 \
  --max-seconds 180 \
  --min-request-interval 12 \
  resume CASE-cb4fa9d654e14a34b4df0a8ea7109e56
```

上述恢复最初被自动审批拒绝，用户随后明确确认该案件数据外发，授权已被执行系统接受。共进行两段恢复，始终使用同一案件与数据库，合计未超过批准的 12 次 API 请求/180 秒运行预算。

| 阶段 | API 请求尝试 | 成功响应 | 耗时 | 结果 |
|---|---:|---:|---:|---|
| 摘要/退避修复后 | 3 | 3 | 39.777 秒 | 一轮 8 个工具结果过大，触发本地 `RequestTooLarge`，未发送超限请求 |
| 禁止单轮并行后 | 9 | 6 | 138.545 秒 | 两次按服务端提示等待后重试成功；最后遇到限流并耗尽调用预算 |
| 合计 | 12 | 9 | 178.322 秒 | 报告 tokens 合计 37855；未完成调查 |

新错误诊断明确记录 `429 / rate_limit_exceeded`；服务端响应头给出 `limit-tokens=10000`、`limit-requests=50`。三次限流时剩余 tokens 分别为 2165、1251、1282，而请求次数仍有余量，支持 token 吞吐限流判断。Retry-After 分别为 18、20、24 秒；前两次等待后成功返回，最后一次等待后因请求预算耗尽而停止，这也触发了上述“预算耗尽不再等待”的修复。

本地 `RequestTooLarge` 是应用设置的 12000-token 估算门槛触发，不是 provider 返回上下文过长。本轮没有收到 `context_length_exceeded`；不能据此判断模型的真实上下文窗口较短。

16 个工具执行记录分别为 2 次 `case_context`、8 次 `search_records`、6 次 `get_record`。专家委派为 0，仍无 Finding/Question/PlanVersion/Action。模型持续检索，没有形成需要恢复的业务判断；现有“案件恢复”保留了审计与状态，但尚不能证明它能续接未保存的调查思路。

原案件状态仍为 `failed`，审计 hash 链复核通过。运行 JSON 与汇总保存在 `research/request_controls_validation/live_resume.json`、`live_resume_serial.json`、`live_summary.json`。这些是实际模型运行记录，不是 replay。

## 后续工作

主动 TPM 预留已在本地测试；下轮可配置 `--tokens-per-minute 10000 --max-request-tokens 10000`，输出上限暂保留 2400。账户限额的证据仅对应本次调用时间和目的地，不应视作所有模型/账户的通用默认值。保守预留可能增加等待；七分钟 demo 还需要减少重复查询、专家上下文和不必要的工具往返。

下一项核心修复是协调角色的职责与任务分配：减少协调层的原始资料检索，让专家完成有边界的调查并保存 Findings；建立可恢复的调查检查点，避免每次 resume 从相同搜索重新开始。应以真实行为测试证明改进，再推进问答—重规划—证据闭环。

T24 仍为“真实工具调用和退避恢复已验证，完整调查及四角色协作未通过”。本轮未改变 baseline、成本假设、法律解释或人工批准门槛，也未超出用户确认的调用预算。
