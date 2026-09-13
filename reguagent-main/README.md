# Regulatory Change-to-Action

以 `require.md` 为最高要求，围绕虚构 Northstar 银行的 SME ESG 案件构建可追溯、有人审核的 multi-agent 演示。bunq 仅作真实同业参考。

- [总体架构：文字描述](docs/architecture.md)
- [实施 TODO 与进度](TODO.md)
- [本轮 M1 实施与验证报告](research/m1_implementation_2026-09-12.md)
- [架构与代码 Review](research/architecture_review_2026-09-11.md)
- [同类产品、开源项目和公开数据集调研](research/market_landscape_2026-09-08.md)
- [数据内容与运行方式](calibrated_v0_2/README.md)、[数据字典](calibrated_v0_2/DATA_DICTIONARY.md)
- [来源审计与缺失证据](research/source_audit.md)

## 当前可运行

```bash
# 离线基线检查；不会调用 LLM、选择方案或执行批准
.venv/bin/python agent/run_demo.py --non-interactive

# 交互式查看基线并选择方案草案；回车不选择
.venv/bin/python agent/run_demo.py

# 可选方法审核：需要配置当前 LLM provider
.venv/bin/python agent/run_demo.py --review-ahp
```

上述 `run_demo.py` 是确定性基线入口。当前四角色工具运行入口为 `agent/run_case.py`，已有案件持久化、访谈恢复、方案/行动、证据状态机和 JSON API。预算约束贯通、实际前端、来源材料和真实模型端到端验收仍按 TODO 推进。离线检查和脚本 replay 不证明真实 LLM 的调查质量。

## 真实调用的请求预算

当前用户已配置 OpenAI/gpt-5。真实调用已验证工具往返和限流等待后的成功重试；服务端返回的 token 限流头为 10000，请求次数限流头为 50。完整四角色闭环尚未通过。

```bash
# 示例：恢复原案件；CASE_ID 替换为实际 ID，使用创建时同一个数据库
# 会发送案件上下文至已配置 provider 并产生 API 使用量
.venv/bin/python agent/run_case.py --db runs/esg_live.sqlite3 \
  --max-request-tokens 10000 --tokens-per-minute 10000 --max-model-calls 12 \
  --max-seconds 180 --min-request-interval 12 resume CASE_ID
```

`--max-request-tokens` 是包括系统提示、工具定义、历史和预留输出的本地估算上限，不是账户 TPM。`--tokens-per-minute` 对同一案件的请求按 60 秒窗口保守预留额度，重启时恢复最近请求记录；不计其他应用的调用，仍以服务端提示为准。`--min-request-interval` 另外控制所有角色的请求启动间隔。输出上限默认 2400，可通过 `--max-output-tokens` 配置；全部选项放在子命令之前。上述为短时调试预算，不能保证完成完整调查。

搜索默认给出摘要，随后按记录 ID 读取全文；OpenAI 单轮至多一个工具调用。运行记录安全的错误分类、请求大小和等待时间，超过预算保留状态。用户已确认案件外发，受限恢复已执行；最新主动 TPM 预留通过本地测试，尚待真实验证。详见[请求控制修复与验证](research/request_controls_2026-09-12.md)。

## 数据与复现

### 压缩 SME ESG 演示

压缩演示使用一份已人工审核的法规请求，跳过法规监测，快速生成一个窄范围的 Part B/Part C 结果。默认 replay 不调用 LLM，也不消耗 API 额度：

```powershell
.venv\Scripts\python.exe agent\compressed_demo.py `
  --db runs\compressed_demo.sqlite3 `
  --mode replay
```

如需让 LLM 只解释候选控制与现有 SME 组合的关系，先确认 `.env.local` 已配置 OpenAI，再使用 `--mode live`；该模式仍由确定性代码计算暴露、覆盖率、成本和期限，输出必须人工审核：

```powershell
.venv\Scripts\python.exe agent\compressed_demo.py `
  --db runs\compressed_demo_live.sqlite3 `
  --mode live --model gpt-5-mini
```

结果会写入普通 `CaseStore`，可用返回的 `case_id` 在 `frontend_v2` 中查看。该演示不是完整法规监测、法律结论或完整四角色调查。

唯一 baseline 是根目录 `calibrated_v0_2/`，数据版本 `0.2.1`，场景和法律研究截止仍为 `2026-09-08`。原始 `data/person1` 至 `person4` 不变。方法记录在 `config/`，运行输出写入 `runs/`；不要把整个工作区递归送给模型。

```bash
# 检查本地修订，临时构建并校验，备份后发布到唯一 baseline
.venv/bin/python scripts/calibrate_dataset.py

# 指定一个尚不存在的临时输出目录，并固定构建时间，便于逐字节复现
.venv/bin/python scripts/calibrate_dataset.py --output /tmp/northstar-review-build --build-timestamp 2026-09-12T00:00:00Z

.venv/bin/python -m unittest discover -s agent -p 'test_*.py'
.venv/bin/python -m unittest discover -s scripts -p 'test_*.py'
.venv/bin/python scripts/validate_dataset.py
.venv/bin/python data/regulatory-governance-dataset/scripts/validate_person1_data.py --root calibrated_v0_2 --strict --require-first-demo
.venv/bin/python scripts/run_eval.py
```

重建检测到未经合并的 baseline 修改时会停止发布，保留当前文件；先在新目录生成、审查差异，并把应保留的修订纳入迁移规则。已有人工矩阵原样迁移，旧版本的确认不会静默批准新方法。

全部法规要求仍为 silver、待合资格人工审核；官方全文版本快照、真实操作证据和完整模型端到端评测尚未补齐。
