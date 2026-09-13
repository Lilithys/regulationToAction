# TODO

Deferred items, in the order raised. Nothing here blocks the current ESG demo path.

## 1. Orchestrator / queue persistence

`agent/orchestrator.py` was in the original plan (Phase 1) but never built. Right now
`run_demo.py` is a one-shot script with no memory between runs except the AHP
registry (`calibrated_v0_2/06_organisation/pairwise_matrix_registry.json`). Missing:

- `STATE.events` / `STATE.queue` / `STATE.logs` / `STATE.notifications` persisted as
  JSON files (per `Integration-Guide.md` section 2's shape -- the reference frontend
  at https://deluxe-conkies-e59e16.netlify.app/ already expects this exact shape).
- A `resolve_queue_item()`-style function: "certain -> advance + log" / "uncertain ->
  create queue item + notify, pause" -- Integration-Guide.md section 10's pseudocode,
  generalized to work per-regulation-change rather than per Part A/B/C/D stage.
- Decide: keep this as files (matches the project's existing zero-dependency style),
  or a lightweight DB if concurrent queue writes become a real concern.

## 2. Phase 8: monitoring/intake integration

Decided architecture (this session): changedetection.io (or official EUR-Lex
Cellar/webservice + EBA RSS) as a dumb "this changed" signal -> triggers
`data/regulatory-governance-dataset` skill in refresh mode -> diffs against the
current `change_register.json`/`requirements.json` -> writes a `detection`-type
queue item for human confirmation. Nothing here is built yet -- not even the design
doc (`docs/monitoring-integration.md`) mentioned in the original plan. This is the
one place in the whole pipeline where genuine open-ended agent research (not a fixed
decision procedure) is actually the right tool, since the skill already does
multi-step verification/extraction with its own anti-hallucination rules.

## 3. Narrative/explanation LLM pass

Raised when the user pushed back that the running system "doesn't feel like an
agent" -- true today: the LLM touches exactly one step (AHP pairwise-comparison
drafting in `agent/review_matrix_cli.py`). Integration-Guide.md's original Prompt 2
("turn a deterministic decision into 1-2 sentences of plain language") was never
built. Adding it after every deterministic stage (applicability/gap/response/
closure) would make the LLM visibly present throughout the run without changing
what gets decided -- the narrative only restates an already-fixed structured result,
same guardrail as the AHP draft. Lower priority than 1-2 but cheap once
agent/llm.py's thinking-disabled fix is confirmed stable.

## 4. Governance-data completeness for the ESG/IPS/DORA "missing" capabilities

**Part A -- DONE (2026-09-11):** of the 6 ESG requirements that showed `missing`,
2 (`REQ-ESG-CREDIT-MONITORING-001`, `REQ-ESG-LONG-HORIZON-001`) turned out to be a
bidirectional-mapping bug, not a real content gap: both split from a requirement
that already had `CTRL-ESG-ONBOARD-SCREEN` linked (`REQ-ESG-CREDIT-POLICY-001` and
`REQ-ESG-RISK-INTEGRATION-001` respectively), but the control's own `requirement_ids`
was never back-filled after the split (verified via `provenance.created_at` --
everything was generated in the same batch, so it's a same-pass propagation gap,
not staleness). Fixed in `calibrated_v0_2/04_governance/controls.json` and
`regulatory_sources/requirements.json` (both directions, plus `current_coverage`),
validated against the project's own `validate_person1_data.py --strict` (0
errors/warnings) and this project's full test suite (73 tests, still green).
Both requirements now correctly read `partial` (not `evidenced` -- coverage[]'s
`existing_portfolio: not_covered` is unchanged), which is a more accurate
characterization of the same real gap, not a weaker one.

**Part B -- still open, needs the user's decision:** the remaining 4 ESG
requirements (`RISK-KRI`, `DATA-SELECTION`, `DATA-GAPS`, `RISK-APPETITE`) have no
split-lineage explanation -- genuinely no control exists anywhere for them. Same
for IPS's 3/4 (`CHARGES-PARITY`, `SANCTIONS-SCREEN`, `SEND-RECEIVE`) and DORA's 2/4
(`ICT-FRAMEWORK`, `TPRM-STRATEGY`) -- checked, no split lineage there either (only
ESG went through atomic-splitting). `data/regulatory-governance-dataset/references/
first-demo.md` designed the *original* ESG gap as deliberate ("Do not create a
portfolio-wide monitoring control ... because that would erase the intended gap"),
so filling all of these in isn't a neutral completeness pass -- it would remove the
reason Phase 4/5 (response design, evidence closure) has anything to do in the demo.
User's stated position: look at what's realistic for Northstar to actually have,
generate it if a real bank in this situation plausibly would; not yet decided which
specific documents that means. Options still on the table: (a) leave as-is, (b)
add partial/intent-only documents for some of these (states intent, not
implementation -- doesn't erase the gap), (c) fill in fully. Waiting on the user
before touching any more calibrated_v0_2 governance files.

## 5. Run the full demo-style walkthrough for IPS/DORA/FRTB, not just ESG

DONE (2026-09-11) -- no new bugs found, output looked sane for all three. One
finding worth keeping in mind for item 4 above: IPS's 3/4-missing pattern looks
structurally like ESG's original (pre-fix) 6/8, which is what prompted checking
whether the same split-lineage bug applied there too (it doesn't -- IPS never went
through atomic splitting).
