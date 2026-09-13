# Regulatory Governance Dataset Skill

这是给 Regulatory Change-to-Action Agent 项目中 Person 1（Regulatory and Governance）使用的可复用 Skill。它会指导 coding agent 联网研究真实 EU/Irish 法规，并生成或更新以下五个文件：

```text
regulatory_sources/requirements.json
regulatory_sources/change_register.json
04_governance/policies.json
04_governance/controls.json
04_governance/procedures.json
```

## 安装

### Codex

项目级安装：把整个 `regulatory-governance-dataset` 文件夹复制到：

```text
<repository>/.agents/skills/regulatory-governance-dataset/
```

个人级安装：复制到：

```text
~/.agents/skills/regulatory-governance-dataset/
```

Codex 会自动发现 Skill；如果没有出现，重启 Codex。官方说明见 [Build skills](https://developers.openai.com/codex/skills)。

### Claude Code

项目级安装：把整个文件夹复制到：

```text
<repository>/.claude/skills/regulatory-governance-dataset/
```

个人级安装：复制到：

```text
~/.claude/skills/regulatory-governance-dataset/
```

Claude Code 会使用同一个 `SKILL.md`、`references/` 和 `scripts/`；`agents/openai.yaml` 仅用于 OpenAI/Codex 界面，Claude Code 可忽略。官方说明见 [Extend Claude with skills](https://code.claude.com/docs/en/skills)。

## 调用

Codex 中输入：

```text
$regulatory-governance-dataset
```

Claude Code 中输入：

```text
/regulatory-governance-dataset
```

推荐完整任务提示：

```text
Use the regulatory-governance-dataset skill.
Dataset root: <path-to-synthetic-bank-dataset>
Mode: create
Research cut-off: today
Scope: first demo — EBA ESG-risk management guidelines, Instant Payments
Regulation, DORA, and FRTB change.

Read Synthetic_Bank_Dataset_Work_Allocation.md and all existing shared dataset
files first. Research official sources online, generate the five Person 1 JSON
files, run strict validation, and report all needs_review,
insufficient_evidence, and cross-team dependencies. Do not invent downstream
bank facts or leak expected assessment labels into operational files.
```

若已有文件，把 `Mode` 改为 `refresh`；只做检查时改为 `validate`。

## 前提

- agent 可以访问互联网，并能打开 EUR-Lex、EBA、European Commission、Irish Statute Book、Central Bank of Ireland 等官方站点；
- agent 对 dataset root 有读取和写入权限；
- repository 内最好已经包含工作分配文档与 Persons 2–4 的共享数据；缺失时 Skill 会保留空引用并标记证据不足，不会代替其他成员编造记录；
- 最终 legal interpretation 与 `gold` annotation 仍需合格的人类 reviewer 审核。

## 包内容

```text
regulatory-governance-dataset/
├── SKILL.md
├── README.md
├── agents/
│   └── openai.yaml
├── references/
│   ├── data-contract.md
│   ├── research-protocol.md
│   └── first-demo.md
└── scripts/
    └── validate_person1_data.py
```

- `SKILL.md`：角色、范围、工作流、来源优先级、ID 与完整性规则、完成标准。
- `data-contract.md`：五个 JSON 的规范字段、枚举、示例与引用关系。
- `research-protocol.md`：联网法规研究、版本/法律状态、引用和不确定性处理协议。
- `first-demo.md`：四个 demo change 的研究入口、场景约束和防答案泄漏规则。
- `validate_person1_data.py`：只依赖 Python 标准库的确定性校验器。

## 手动运行校验

在 Skill 文件夹内执行：

```text
python3 scripts/validate_person1_data.py \
  --root <path-to-synthetic-bank-dataset> \
  --require-first-demo \
  --strict
```

非零退出码表示仍有 schema、来源、ID、双向引用或严格模式 warning 需要处理。缺失的 Persons 2–4 文件应作为 handoff blocker 报告，不能通过新造 ID 来消除。

## 设计原则

```text
No enterprise evidence -> no enterprise assertion.
```

外部 regulation/guidance 必须真实、可定位、可复核；虚构银行内部 governance 可以按已授权场景 synthetic，但每条都必须显式标记，并保持与其他团队数据一致。
