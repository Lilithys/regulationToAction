const AGENT_COLUMNS = [
  { role: 'regulatory_analyst', name: 'Regulatory Analyst', desc: 'Confirms what changed in the regulation and whether it applies here.' },
  { role: 'bank_investigator', name: 'Bank Investigator', desc: "Checks the bank's own controls and data against the requirement." },
  { role: 'response_planner', name: 'Response Planner', desc: 'Compares response options and drafts a remediation action.' },
];

async function renderEventDetail(caseId) {
  const app = document.getElementById('app');
  app.innerHTML = '<div class="loading-state">Loading event...</div>';
  try {
    const [o, inv, plansData] = await Promise.all([Api.decisionView(), Api.investigation(), Api.plans()]);
    const r = o.regulatory_change || {}, i = o.impact || {}, status = humanStatus(o.case.status);
    const impactRows = [['Exposure', i.exposure_eur_millions == null ? null : `EUR ${i.exposure_eur_millions}m`], ['Borrowers', i.borrower_count], ['Usable energy-cost data', i.energy_coverage_pct == null ? null : `${i.energy_coverage_pct}%`], ['Unresolved borrowers', i.missing_borrowers]].filter(([,v]) => v != null);
    app.innerHTML = `<div class="detail-header"><button class="text-button" id="back-events">${icon('arrowLeft')} All regulatory events</button><div class="decision-meta"><span class="status-pill ${status.className}">${status.label}</span><span>${escapeHtml(o.case.mode)} mode</span><span>Revision ${o.case.revision}</span></div><h1>${escapeHtml(r.title || 'Regulatory change')}</h1><p>${escapeHtml(o.case.goal)}</p></div>
      <div class="stage-track">${(o.stages || []).map(s => `<div class="stage-seg"><div class="stage-bar ${escapeHtml(s.state)}"></div><div class="stage-label ${escapeHtml(s.state)}">${escapeHtml(s.name)}</div></div>`).join('')}</div>
      <section class="detail-flow"><article class="flow-section"><div class="panel-kicker">Regulatory change</div><div class="panel-desc">What the source text says changed.</div><p>${escapeHtml(r.legal_status || 'Status not yet assessed')}</p><dl class="compact-kv"><dt>Effective date</dt><dd>${escapeHtml(r.effective_date || 'Not available')}</dd><dt>Source</dt><dd>${escapeHtml(r.source_id || 'Not available')}</dd></dl></article>
      <article class="flow-section"><div class="panel-kicker">Business impact</div><div class="panel-desc">Estimated exposure and data coverage.</div><div class="metric-grid">${impactRows.length ? impactRows.map(([label,value]) => `<div class="metric"><strong>${escapeHtml(String(value))}</strong><span>${escapeHtml(label)}</span></div>`).join('') : '<p class="muted">No impact calculation yet.</p>'}</div></article></section>
      <section class="role-columns">${AGENT_COLUMNS.map((col) => renderAgentColumn(col, inv, plansData)).join('')}</section>
      <section class="next-step card outline"><div><div class="panel-kicker">Next step</div><h3>${escapeHtml(o.next_step.title)}</h3><p>${escapeHtml(o.next_step.message)}</p></div><span class="status-pill ${o.pending_count ? 'warn' : ''}">${o.pending_count} pending</span></section>`;
    document.getElementById('back-events').addEventListener('click', renderOverview);
    app.querySelectorAll('[data-go-queue]').forEach((btn) => btn.addEventListener('click', () => setView('queue')));
  } catch (err) { showError(app, err); }
}

function renderAgentColumn(col, inv, plansData) {
  const findings = (inv.findings || []).filter((f) => f.author_role === col.role);
  const gaps = (inv.gap_assessments || []).filter((g) => g.author_role === col.role);
  const plans = (plansData.plans || []).filter((p) => p.author_role === col.role);
  const actions = (plansData.actions || []).filter((a) => a.author_role === col.role);
  // Only bank_investigator can call request_question (investigation_tools.py's
  // PERMISSIONS table) -- open questions always belong in its column.
  const questions = col.role === 'bank_investigator' ? (inv.open_questions || []) : [];
  const hasAny = findings.length || gaps.length || plans.length || actions.length || questions.length;
  return `
    <article class="role-column">
      <div class="role-column-header">${escapeHtml(col.name)}</div>
      <div class="role-column-desc">${escapeHtml(col.desc)}</div>
      ${hasAny ? '' : '<div class="agent-empty">Nothing from this role yet.</div>'}
      ${questions.map((q) => `<div class="decision-item"><div style="display:flex;justify-content:space-between;align-items:baseline;gap:8px;"><strong>Waiting on a human answer</strong><span class="status-pill warn">Open question</span></div><p>${escapeHtml(q.question)}</p><button class="text-button" data-go-queue style="margin-top:4px;">Answer in Queue &rarr;</button></div>`).join('')}
      ${findings.map((f) => `<div class="decision-item"><div style="display:flex;justify-content:space-between;align-items:baseline;gap:8px;"><strong>${escapeHtml(f.category)}</strong>${gapReviewPill(f.review_status)}</div><p>${escapeHtml(f.summary)}</p></div>`).join('')}
      ${gaps.map((g) => `<div class="decision-item"><div style="display:flex;justify-content:space-between;align-items:baseline;gap:8px;"><strong>${escapeHtml(g.candidate_control_id || g.requirement_id || 'Scoped gap')}</strong>${gapReviewPill(g.review_status)}</div><span>${escapeHtml(g.mapping_support || 'Assessment pending')} · ${escapeHtml(g.design_coverage || 'Coverage pending')}</span>${g.rationale ? `<p>${escapeHtml(g.rationale)}</p>` : ''}</div>`).join('')}
      ${plans.map((p) => `<div class="decision-item"><div style="display:flex;justify-content:space-between;align-items:baseline;gap:8px;"><strong>${escapeHtml(p.option_id)}</strong>${p.capacity_sufficient && p.regulatory_deadline_feasible ? '<span class="status-pill good">Feasible</span>' : '<span class="status-pill warn">Constrained</span>'}</div><span>${escapeHtml(p.rationale || '')}</span></div>`).join('')}
      ${actions.map((a) => `<div class="decision-item"><div style="display:flex;justify-content:space-between;align-items:baseline;gap:8px;"><strong>${escapeHtml(a.title)}</strong>${deadlineStatusPill(a.regulatory_deadline_status)}</div><span>${escapeHtml(a.accountable_role_id)} · target ${escapeHtml(a.target_date)} · ${escapeHtml(a.acceptance_status)}</span></div>`).join('')}
    </article>`;
}

