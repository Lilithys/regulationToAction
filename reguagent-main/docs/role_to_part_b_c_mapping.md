# Four LLM Roles To Part B / Part C Mapping

The compressed demo uses a human-reviewed request as its trusted intake and deliberately skips source monitoring. It demonstrates a narrow, auditable slice:

```text
reviewed request -> deterministic Part B exposure/coverage
                 -> LLM-supported control-gap interpretation
                 -> deterministic cost/RACI/deadline plan
                 -> human review and action/evidence closure
```

The full multi-agent path remains available through `agent/run_case.py`. The compressed path is implemented by `agent/compressed_demo.py` and writes the same `CaseStore` objects exposed by `view_adapter.py` and `api_server.py`.

| Role or decision | Responsibility |
|---|---|
| Coordinator | Routes bounded work in the full multi-agent path; not used by the compressed demo |
| Regulatory analyst | Reviews scope, dates, citations and source limitations when needed |
| Bank investigator | Interprets whether the candidate control supports recurring SME ESG monitoring |
| Response planner | Drafts a scoped plan/action in the full path |
| Part B exposure, population and coverage | Deterministic code |
| Cost, RACI, deadline and evidence gates | Deterministic code |
| Legal approval, action acceptance, evidence verification and closure | Human |

The compressed demo is not a complete legal-compliance conclusion, live regulation monitor, or fully calibrated risk model. Its output remains provisional and requires human review.
