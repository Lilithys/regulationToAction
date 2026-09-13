// Main application logic. Every view is rendered from a real API response
// (see api.js) -- there is no local STATE object standing in for the backend
// anymore. If a fetch fails, the view shows an error box, it does not fall
// back to fixture data.

let currentView = 'overview';
let loaded = false;
let selectedCaseId = null;

// ---------------------------------------------------------------
// Case selection -- the backend runs and persists cases on its own; the
// frontend only ever reads a case and posts human decisions against it.
// ---------------------------------------------------------------
function openCase(caseId) {
  selectedCaseId = caseId;
  loaded = true;
  Api.caseId = caseId;
  renderEventDetail(caseId);
}

function autoContinueEnabled() {
  const checkbox = document.getElementById('auto-continue');
  return !checkbox || checkbox.checked;
}

// ---------------------------------------------------------------
// Navigation
// ---------------------------------------------------------------
document.querySelectorAll('.tab').forEach((tab) => {
  tab.addEventListener('click', () => setView(tab.dataset.view));
});

function setView(view) {
  currentView = view;
  document.querySelectorAll('.tab').forEach((t) => t.classList.toggle('active', t.dataset.view === view));
  if (view === 'overview') { renderOverview(); return; }
  if (!selectedCaseId) { document.getElementById('app').innerHTML = '<div class="empty-state">Select a regulatory event first.</div>'; return; }
  loaded = true;
  const renderers = {
    investigation: renderInvestigation,
    plans: renderPlans,
    evidence: renderEvidence,
    queue: renderQueue,
    audit: renderAudit,
  };
  renderers[view]();
}

async function refreshQueueCount() {
  try {
    const items = await Api.queue();
    document.getElementById('queue-count').textContent = items.length || '';
  } catch (err) {
    // Non-fatal -- the badge just stays empty if this fails.
  }
}

function showError(container, err) {
  container.innerHTML = `<div class="error-box">${escapeHtml(err.message)}</div>`;
}

function escapeHtml(s) {
  const div = document.createElement('div');
  div.textContent = s;
  return div.innerHTML;
}

// Decision-oriented status -> (color class, label) mappings. These translate the
// backend's raw enum strings into a colored pill so severity is visible without
// reading the value. GapAssessment.status is a generic object lifecycle field
// (draft/stale) that InvestigationTools always sets to 'draft' on creation --
// it is not a risk signal, so the gap pill is keyed off review_status instead
// (provisional/approved/escalated, the tri-state trust field case_store.py's own
// closure-gate logic treats as authoritative -- see case_store.py's can_close check).
function gapReviewPill(reviewStatus) {
  const map = {
    provisional: ['neutral', 'Provisional (AI draft)'],
    approved: ['good', 'Approved'],
    escalated: ['danger', 'Escalated'],
  };
  const [cls, label] = map[reviewStatus] || ['neutral', reviewStatus || 'Unknown'];
  return `<span class="status-pill ${cls}">${escapeHtml(label)}</span>`;
}

// regulatory_deadline_status / internal_target_status come from two code paths:
// dataset_runtime.py's deadline_status() (unknown/past_due/due_today/future) for
// live-computed actions, and compressed_demo.py's fixture literal 'overdue_or_due'.
// Both are covered explicitly; anything else still renders (neutral) instead of
// showing blank.
function deadlineStatusPill(status) {
  const map = {
    past_due: ['danger', 'Past due'],
    overdue_or_due: ['danger', 'Overdue / due'],
    due_today: ['warn', 'Due today'],
    future: ['good', 'On track'],
    unknown: ['neutral', 'Unknown'],
  };
  const [cls, label] = map[status] || ['neutral', status || 'Unknown'];
  return `<span class="status-pill ${cls}">${escapeHtml(label)}</span>`;
}

// Turns a raw audit event payload into a one-line human summary instead of a
// JSON blob. Falls back to a generic key: value join for event types not
// explicitly handled here (case_store.py emits several -- see _audit() call sites).
function formatAuditDetail(eventType, detail) {
  const d = detail || {};
  switch (eventType) {
    case 'case_created':
      return `Case started in ${d.mode} mode, as of ${d.as_of_date}`;
    case 'object_version':
      return `${d.kind} ${d.key} -> v${d.version} (${d.status})`;
    case 'case_status':
      return `Status changed to ${d.status}${d.reason ? ' — ' + d.reason : ''}`;
    case 'fact_answered':
      return `${d.fact_id} answered: ${JSON.stringify(d.answer)}`;
    case 'action_accepted':
      return `${d.action_key} accepted by ${d.accepted_by}`;
    case 'evidence_decided':
      return `${d.evidence_key} marked ${d.decision} by ${d.decided_by}`;
    case 'action_closed':
      return `${d.action_key} closed by ${d.closed_by}`;
    default:
      return Object.entries(d).map(([k, v]) => `${k}: ${typeof v === 'object' ? JSON.stringify(v) : v}`).join('; ') || '(no detail)';
  }
}

// ---------------------------------------------------------------
// Overview  (GET /api/cases/:id)
// ---------------------------------------------------------------
async function renderOverview() {
  const app = document.getElementById('app');
  app.innerHTML = `<div class="page-header"><div class="page-title">${icon('gavel')}Regulatory events</div><div class="page-meta">Live case registry</div></div><div id="overview-body"></div>`;
  const body = document.getElementById('overview-body');
  try {
    const cases = await Api.cases();
    body.innerHTML = cases.length ? `<div class="event-list">${cases.map(c => {
      const status = humanStatus(c.status);
      return `<article class="event-card" data-case-id="${escapeHtml(c.case_id)}" data-mode="${escapeHtml(c.mode)}">
        <div class="event-card-main"><div class="event-card-eyebrow">${escapeHtml(c.mode)} assessment</div>
          <h2>${escapeHtml(c.title)}</h2><p>${escapeHtml(c.summary)} · As of ${escapeHtml(c.as_of_date)} · Updated ${escapeHtml(c.updated_at)}</p></div>
        <div class="event-card-side"><span class="status-pill ${status.className}">${status.label}</span><span class="event-arrow">${icon('chevronRight')}</span></div>
      </article>`;
    }).join('')}</div>` : '<div class="empty-state">No regulatory events have been created yet.</div>';
    body.querySelectorAll('.event-card').forEach(card => card.addEventListener('click', () => openCase(card.dataset.caseId, card.dataset.mode)));
  } catch (err) {
    showError(body, err);
  }
}

// Each investigative role is rendered as its own column, populated purely by
// filtering on the author_role the backend already stamps on every Finding/
// GapAssessment/PlanVersion/Action -- there is no separate "who does what"
// list to keep in sync here, and no fixed hand-off order is assumed (roles.py
// does not enforce one; a role's column simply fills in as its objects land).
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
      <section class="role-columns">${AGENT_COLUMNS.map((col) => renderAgentColumn(col, inv, plansData, r)).join('')}</section>
      <section class="next-step card outline"><div><div class="panel-kicker">Next step</div><h3>${escapeHtml(o.next_step.title)}</h3><p>${escapeHtml(o.next_step.message)}</p></div><span class="status-pill ${o.pending_count ? 'warn' : ''}">${o.pending_count} pending</span></section>`;
    document.getElementById('back-events').addEventListener('click', renderOverview);
    app.querySelectorAll('[data-go-queue]').forEach((btn) => btn.addEventListener('click', () => setView('queue')));
  } catch (err) { showError(app, err); }
}

function renderAgentColumn(col, inv, plansData, regulatoryChange) {
  const findings = (inv.findings || []).filter((f) => f.author_role === col.role);
  const gaps = (inv.gap_assessments || []).filter((g) => g.author_role === col.role);
  const plans = (plansData.plans || []).filter((p) => p.author_role === col.role);
  const actions = (plansData.actions || []).filter((a) => a.author_role === col.role);
  // Only bank_investigator can call request_question (investigation_tools.py's
  // PERMISSIONS table) -- open questions always belong in its column.
  const questions = col.role === 'bank_investigator' ? (inv.open_questions || []) : [];
  const hasAny = findings.length || gaps.length || plans.length || actions.length || questions.length;
  // The compressed/reviewed-request intake path skips a separate regulatory_analyst
  // step entirely -- applicability was already confirmed by a human during intake,
  // so this column is empty by design rather than because analysis is pending.
  const skippedByReview = col.role === 'regulatory_analyst' && !hasAny && regulatoryChange && regulatoryChange.review_status === 'human_reviewed';
  const emptyState = skippedByReview
    ? '<div class="agent-empty">Human reviewed</div>'
    : '<div class="agent-empty">Nothing from this role yet.</div>';
  return `
    <article class="role-column">
      <div class="role-column-header">${escapeHtml(col.name)}</div>
      <div class="role-column-desc">${escapeHtml(col.desc)}</div>
      ${hasAny ? '' : emptyState}
      ${questions.map((q) => `<div class="decision-item"><div style="display:flex;justify-content:space-between;align-items:baseline;gap:8px;"><strong>Waiting on a human answer</strong><span class="status-pill warn">Open question</span></div><p>${escapeHtml(q.question)}</p><button class="text-button" data-go-queue style="margin-top:4px;">Answer in Queue &rarr;</button></div>`).join('')}
      ${findings.map((f) => `<div class="decision-item"><div style="display:flex;justify-content:space-between;align-items:baseline;gap:8px;"><strong>${escapeHtml(f.category)}</strong>${gapReviewPill(f.review_status)}</div><p>${escapeHtml(f.summary)}</p></div>`).join('')}
      ${gaps.map((g) => `<div class="decision-item"><div style="display:flex;justify-content:space-between;align-items:baseline;gap:8px;"><strong>${escapeHtml(g.candidate_control_id || g.requirement_id || 'Scoped gap')}</strong>${gapReviewPill(g.review_status)}</div><span>${escapeHtml(g.mapping_support || 'Assessment pending')} · ${escapeHtml(g.design_coverage || 'Coverage pending')}</span>${g.rationale ? `<p>${escapeHtml(g.rationale)}</p>` : ''}</div>`).join('')}
      ${plans.map((p) => `<div class="decision-item"><div style="display:flex;justify-content:space-between;align-items:baseline;gap:8px;"><strong>${escapeHtml(p.option_id)}</strong>${p.capacity_sufficient && p.regulatory_deadline_feasible ? '<span class="status-pill good">Feasible</span>' : '<span class="status-pill warn">Constrained</span>'}</div><span>${escapeHtml(p.rationale || '')}</span></div>`).join('')}
      ${actions.map((a) => `<div class="decision-item"><div style="display:flex;justify-content:space-between;align-items:baseline;gap:8px;"><strong>${escapeHtml(a.title)}</strong>${deadlineStatusPill(a.regulatory_deadline_status)}</div><span>${escapeHtml(a.accountable_role_id)} · target ${escapeHtml(a.target_date)} · ${escapeHtml(a.acceptance_status)}</span></div>${(a.required_evidence || []).length ? `<div class="evidence-slots">${a.required_evidence.map((e) => `<span class="evidence-slot ${e.submitted ? 'submitted' : 'missing'}">${e.submitted ? icon('check') : icon('fileQuestion')}${escapeHtml(e.title)}</span>`).join('')}</div>` : ''}</div>`).join('')}
    </article>`;
}

function humanStatus(status) {
  const labels = { open: 'Open', running: 'Running', waiting_for_input: 'Waiting for input', needs_review: 'Needs review', investigation_complete: 'Investigation complete', failed: 'Paused after failure' };
  return { label: labels[status] || status || 'Unknown', className: status === 'failed' ? 'danger' : status === 'running' ? 'active' : '' };
}

// ---------------------------------------------------------------
// Investigation  (GET /api/cases/:id/investigation)
// ---------------------------------------------------------------
async function renderInvestigation() {
  const app = document.getElementById('app');
  app.innerHTML = `<div class="page-header"><div class="page-title">${icon('search')}Investigation</div></div><div id="inv-body"></div>`;
  const body = document.getElementById('inv-body');
  try {
    const inv = await Api.investigation();

    body.innerHTML = `
      ${recordSection('Tasks', inv.tasks, (t) => `
        <div class="record-card">
          <div class="record-card-top"><span class="record-card-title">${escapeHtml(t.task)}</span>
            <span class="record-card-status">${escapeHtml(t.status)}</span></div>
          <div class="record-card-body">${fieldLine('Role', t.role)}${fieldLine('Key', t.key)}${fieldLine('Version', t.version)}</div>
        </div>`)}

      ${recordSection('Findings', inv.findings, (f) => `
        <div class="record-card">
          <div class="record-card-top"><span class="record-card-title">${escapeHtml(f.summary)}</span>
            <span class="record-card-status">${escapeHtml(f.status)} / ${escapeHtml(f.review_status)}</span></div>
          <div class="record-card-body">
            ${fieldLine('Category', f.category)}${fieldLine('Author role', f.author_role)}
            ${fieldLine('References', (f.reference_ids || []).join(', ') || '(none)')}
            ${fieldLine('Key', f.key)}${fieldLine('Version', f.version)}
          </div>
        </div>`)}

      ${recordSection('Gap Assessments', inv.gap_assessments, (g) => `
        <div class="record-card">
          <div class="record-card-top">
            <span class="record-card-title">${escapeHtml(g.requirement_id)}${g.candidate_control_id ? ' · ' + escapeHtml(g.candidate_control_id) : ''}</span>
            ${gapReviewPill(g.review_status)}
          </div>
          <div class="agent-card-who">${escapeHtml(g.mapping_support)} · ${escapeHtml(g.design_coverage)} · ${escapeHtml(g.operating_evidence)}</div>
          ${g.rationale ? `<p style="margin:6px 0 0;font-size:12.5px;color:var(--text-secondary);">${escapeHtml(g.rationale)}</p>` : ''}
          <button class="toggle-btn" data-gap="${escapeHtml(g.key)}" style="margin-top:8px;">Details</button>
          <div class="toggle-box" data-gap="${escapeHtml(g.key)}">
            ${fieldLine('Author role', g.author_role)}${fieldLine('Key', g.key)}${fieldLine('Version', g.version)}
          </div>
        </div>`)}

      ${recordSection('Open Questions', inv.open_questions, (q) => `
        <div class="record-card">
          <div class="record-card-top"><span class="record-card-title">${escapeHtml(q.question)}</span></div>
          <div class="record-card-body">
            ${fieldLine('Owner role', q.owner_role_id)}
            ${q.decision_reason ? fieldLine('Why this matters', q.decision_reason) : ''}
            ${fieldLine('Key', q.key)}${fieldLine('Version', q.version)}
          </div>
        </div>`)}
    `;
    body.querySelectorAll('.toggle-btn[data-gap]').forEach((btn) => {
      btn.addEventListener('click', () => {
        document.querySelector(`.toggle-box[data-gap="${CSS.escape(btn.dataset.gap)}"]`).classList.toggle('open');
      });
    });
  } catch (err) {
    showError(body, err);
  }
}

function recordSection(title, items, cardFn) {
  return `
    <div style="font-size:13px;font-weight:500;margin:16px 0 8px;">${escapeHtml(title)}</div>
    <div class="record-list">
      ${items && items.length ? items.map(cardFn).join('') : '<div class="section-empty">None yet.</div>'}
    </div>
  `;
}

function fieldLine(label, value) {
  return `<div class="record-card-row"><span class="field-label">${escapeHtml(label)}</span>${escapeHtml(String(value))}</div>`;
}

// ---------------------------------------------------------------
// Plans & Actions  (GET /api/cases/:id/plans)
// ---------------------------------------------------------------
async function renderPlans() {
  const app = document.getElementById('app');
  app.innerHTML = `<div class="page-header"><div class="page-title">${icon('target')}Plans &amp; Actions</div></div><div id="plans-body"></div>`;
  const body = document.getElementById('plans-body');
  try {
    const [{ plans, actions }, evidenceData] = await Promise.all([Api.plans(), Api.evidence()]);
    const evidenceCurrent = evidenceData.current || [];

    body.innerHTML = `
      ${recordSection('Plan Versions', plans, (p) => `
        <div class="record-card">
          <div class="record-card-top"><span class="record-card-title">${escapeHtml(p.option_id)}</span>
            <span class="record-card-status">${escapeHtml(p.status)} / ${escapeHtml(p.recommendation_status)}</span></div>
          <div class="agent-card-who">
            ${p.capacity_sufficient ? '<span class="status-pill good">Capacity OK</span>' : '<span class="status-pill danger">Capacity insufficient</span>'}
            ${p.regulatory_deadline_feasible ? '<span class="status-pill good">Deadline feasible</span>' : '<span class="status-pill danger">Deadline not feasible</span>'}
          </div>
          <div class="record-card-body" style="margin-top:6px;">
            ${fieldLine('Addresses', (p.addresses_requirement_ids || []).join(', ') || '(none)')}
            ${fieldLine('Deferred', (p.deferred_requirement_ids || []).join(', ') || '(none)')}
            ${fieldLine('Rationale', p.rationale)}
            ${fieldLine('3-year TCO (EUR)', p.three_year_tco_eur)}
            ${fieldLine('Setup total (EUR)', p.setup_total_eur)}
            ${fieldLine('Selected regulatory due date', p.selected_regulatory_due_date)}
            ${fieldLine('Key', p.key)}${fieldLine('Version', p.version)}
          </div>
        </div>`)}

      ${recordSection('Actions', actions, (a) => renderActionCard(a, evidenceCurrent))}
    `;
    bindUploadForms(actions);
  } catch (err) {
    showError(body, err);
  }
}

function renderActionCard(a, evidenceCurrent) {
  const needsEvidence = a.acceptance_status === 'accepted' && (a.required_evidence || []).length > 0;
  const totalSlots = (a.required_evidence || []).length;
  const verifiedCount = (evidenceCurrent || []).filter((e) => e.action_key === a.key && e.status === 'verified').length;
  return `
    <div class="record-card">
      <div class="record-card-top">
        <span class="record-card-title">${escapeHtml(a.title)}</span>
        ${deadlineStatusPill(a.regulatory_deadline_status)}
      </div>
      <div class="agent-card-who">${escapeHtml(a.accountable_role_id)} · target ${escapeHtml(a.target_date)} · ${escapeHtml(a.status)} / ${escapeHtml(a.acceptance_status)}</div>
      <div class="record-card-body" style="margin-top:6px;">
        ${fieldLine('Steps', a.steps)}
        ${fieldLine('Regulatory due date', a.regulatory_due_date)}
        ${fieldLine('Internal target status', a.internal_target_status)}
        ${a.accepted_by_role_id ? fieldLine('Accepted by', a.accepted_by_role_id) : ''}
        ${totalSlots ? fieldLine('Evidence verified', `${verifiedCount}/${totalSlots}`) : ''}
        ${fieldLine('Required evidence', (a.required_evidence || []).map((e) => `${e.evidence_key}${e.submitted ? ' (submitted)' : ' (missing)'}`).join(', ') || '(none)')}
        ${a.closure_status ? fieldLine('Closure status', a.closure_status) : ''}
        ${a.closure_scope_note ? fieldLine('Closure scope note', a.closure_scope_note) : ''}
        ${fieldLine('Key', a.key)}${fieldLine('Version', a.version)}${fieldLine('Plan key', a.plan_key)}
      </div>
      ${needsEvidence ? `
        <button class="btn small upload-toggle" data-action-key="${escapeHtml(a.key)}">Upload evidence</button>
        <div class="upload-form" data-action-key="${escapeHtml(a.key)}" style="display:none;"></div>
      ` : ''}
    </div>
  `;
}

function bindUploadForms(actions) {
  document.querySelectorAll('.upload-toggle').forEach((btn) => {
    btn.addEventListener('click', () => {
      const key = btn.dataset.actionKey;
      const formEl = document.querySelector(`.upload-form[data-action-key="${CSS.escape(key)}"]`);
      const action = actions.find((a) => a.key === key);
      const open = formEl.style.display !== 'none';
      if (open) { formEl.style.display = 'none'; return; }
      formEl.style.display = 'block';
      formEl.innerHTML = buildUploadFormHtml(action);
      bindUploadSubmit(formEl, action);
    });
  });
}

function buildUploadFormHtml(action) {
  const slotOptions = (action.required_evidence || [])
    .map((slot) => `<option value="${escapeHtml(slot.evidence_key)}">${escapeHtml(slot.evidence_key)} -- ${escapeHtml(slot.title)}${slot.submitted ? ' (already submitted)' : ''}</option>`).join('');
  return `
    <div class="field"><label>Evidence slot</label><select class="ev-slot">${slotOptions}</select></div>
    <div class="field"><label>Evidence type</label><input type="text" class="ev-type" placeholder="e.g. policy_document"></div>
    <div class="field"><label>Submitted by (role ID)</label><input type="text" class="ev-role" placeholder="ROLE-..."></div>
    <div class="field"><label>File</label><input type="file" class="ev-file"></div>
    <div class="error-text" style="display:block;"></div>
    <button class="btn primary small ev-submit">Submit evidence</button>
  `;
}

function bindUploadSubmit(formEl, action) {
  formEl.querySelector('.ev-submit').addEventListener('click', async () => {
    const errEl = formEl.querySelector('.error-text');
    const slot = formEl.querySelector('.ev-slot').value;
    const type = formEl.querySelector('.ev-type').value.trim();
    const role = formEl.querySelector('.ev-role').value.trim();
    const fileInput = formEl.querySelector('.ev-file');
    const file = fileInput.files[0];
    if (!type || !role || !file) {
      errEl.textContent = 'Evidence type, submitted-by role, and a file are all required.';
      errEl.style.color = 'var(--danger)';
      return;
    }
    errEl.textContent = 'Uploading...';
    errEl.style.color = 'var(--text-secondary)';
    try {
      await Api.submitEvidence({ actionKey: action.key, evidenceSlot: slot, evidenceType: type, submittedByRoleId: role, file });
      errEl.textContent = 'Submitted. Refreshing...';
      renderPlans();
      refreshQueueCount();
    } catch (err) {
      errEl.textContent = err.message;
      errEl.style.color = 'var(--danger)';
    }
  });
}

// ---------------------------------------------------------------
// Evidence  (GET /api/cases/:id/evidence)
// ---------------------------------------------------------------
async function renderEvidence() {
  const app = document.getElementById('app');
  app.innerHTML = `<div class="page-header"><div class="page-title">${icon('stamp')}Evidence</div></div><div id="ev-body"></div>`;
  const body = document.getElementById('ev-body');
  try {
    const { current, history } = await Api.evidence();

    body.innerHTML = recordSection('Current Evidence', current, (e) => {
      const hist = history[e.key] || [];
      return `
        <div class="record-card">
          <div class="record-card-top"><span class="record-card-title">${escapeHtml(e.title)}</span>
            <span class="record-card-status">${escapeHtml(e.status)}</span></div>
          <div class="record-card-body">
            ${fieldLine('Action', e.action_key)}
            ${fieldLine('Evidence slot key', e.evidence_key)}
            ${fieldLine('Type', e.evidence_type)}
            ${fieldLine('Submitted by', e.submitted_by_role_id)}
            ${fieldLine('Collected at', e.collected_at)}
            ${e.content_assessment ? fieldLine('Content assessment', e.content_assessment) : ''}
            ${e.content_rationale ? fieldLine('Content rationale', e.content_rationale) : ''}
            ${e.human_decision ? fieldLine('Human decision', e.human_decision) : ''}
            ${e.decided_by_role_id ? fieldLine('Decided by', e.decided_by_role_id) : ''}
            ${fieldLine('Key', e.key)}${fieldLine('Version', e.version)}
          </div>
          ${hist.length ? `
            <div class="evidence-history-toggle toggle-btn" data-key="${escapeHtml(e.key)}">History (${hist.length})</div>
            <div class="evidence-history-list" data-key="${escapeHtml(e.key)}">
              ${hist.map((h) => `<div class="record-card-row">v${h.version}: ${escapeHtml(h.status)} ${h.human_decision ? '— ' + escapeHtml(h.human_decision) : ''}</div>`).join('')}
            </div>` : ''}
        </div>
      `;
    });

    body.querySelectorAll('.evidence-history-toggle').forEach((btn) => {
      btn.addEventListener('click', () => {
        document.querySelector(`.evidence-history-list[data-key="${CSS.escape(btn.dataset.key)}"]`).classList.toggle('open');
      });
    });
  } catch (err) {
    showError(body, err);
  }
}

// ---------------------------------------------------------------
// Audit Log  (GET /api/cases/:id/audit)
// ---------------------------------------------------------------
async function renderAudit() {
  const app = document.getElementById('app');
  app.innerHTML = `<div class="page-header"><div class="page-title">${icon('list')}Audit Log</div></div><div id="audit-body"></div>`;
  const body = document.getElementById('audit-body');
  try {
    const events = await Api.audit();
    body.innerHTML = `
      <table class="log-table">
        <thead><tr><th style="width:8%">Seq</th><th style="width:16%">At</th><th style="width:10%">Actor type</th>
          <th style="width:16%">Actor</th><th style="width:16%">Event type</th><th>Detail</th></tr></thead>
        <tbody>
          ${events.slice().reverse().map((e) => `
            <tr>
              <td class="muted">${e.seq}</td>
              <td class="muted">${escapeHtml(e.at)}</td>
              <td><span class="log-actor ${e.actor_type === 'human' ? 'human' : 'agent'}">${escapeHtml(e.actor_type)}</span></td>
              <td>${escapeHtml(e.actor)}</td>
              <td>${escapeHtml(e.event_type)}</td>
              <td class="muted">${escapeHtml(formatAuditDetail(e.event_type, e.detail))}</td>
            </tr>`).join('')}
        </tbody>
      </table>
    `;
  } catch (err) {
    showError(body, err);
  }
}

// ---------------------------------------------------------------
// Queue  (GET /api/cases/:id/queue, POST .../resolve)
// ---------------------------------------------------------------
const SECTION_META = {
  fact: { title: 'Open Questions', desc: 'Facts the investigation could not determine on its own' },
  response: { title: 'Actions Awaiting Acceptance', desc: 'Drafted actions waiting for a role to accept them' },
  evidence: { title: 'Evidence Awaiting Review', desc: 'Submitted evidence waiting for a verify/reject decision' },
  closure: { title: 'Ready to Close', desc: 'Actions where all required evidence has been verified' },
};
const SECTION_ORDER = ['fact', 'response', 'evidence', 'closure'];

async function renderQueue() {
  const app = document.getElementById('app');
  app.innerHTML = `<div class="page-header"><div class="page-title">${icon('hand')}Queue</div></div>
    <label class="hint-text" style="display:block;margin-bottom:10px;"><input type="checkbox" id="auto-continue" checked> Continue coordinator after a human decision</label>
    <div id="queue-sections"></div><div id="queue-form-area"></div>`;
  try {
    const items = await Api.queue();
    renderQueueSections(items);
    refreshQueueCount();
  } catch (err) {
    showError(document.getElementById('queue-sections'), err);
  }
}

// Frontend-only staging: while any fact (open question) item is pending, the
// response/evidence/closure sections are shown but locked. The backend's
// investigation is unaffected -- a specialist may still draft an action while
// a question is open (roles.py allows conditional work) -- this only stops
// the human-facing queue from presenting "answer this" and "accept that" as
// equally actionable at the same time.
function renderQueueSections(items) {
  const sectionsEl = document.getElementById('queue-sections');
  sectionsEl.innerHTML = '';
  const openFactCount = items.filter((i) => i.section === 'fact').length;
  const locked = openFactCount > 0;
  SECTION_ORDER.forEach((key) => {
    const meta = SECTION_META[key];
    const groupItems = items.filter((i) => i.section === key);
    const isLocked = locked && key !== 'fact';
    const row = document.createElement('div');
    row.className = 'agent-row' + (isLocked ? ' agent-row-locked' : '');
    row.innerHTML = `
      <div class="agent-row-title">
        <span class="agent-row-name">${escapeHtml(meta.title)}</span>
        <span class="agent-row-count">${groupItems.length}</span>
      </div>
      ${isLocked ? `<div class="agent-locked-note">${icon('lock')}Blocked until the open question${openFactCount === 1 ? ' above is' : 's above are'} answered.</div>` : ''}
      <div class="agent-cards">
        ${groupItems.length ? groupItems.map((it) => `
          <div class="agent-card${isLocked ? ' agent-card-locked' : ''}" data-item-id="${escapeHtml(it.id)}">
            <div class="agent-card-type">${escapeHtml(meta.desc)}</div>
            <div class="agent-card-text">${escapeHtml(it.text)}</div>
            <div class="agent-card-who">Owner: ${escapeHtml(it.who)}</div>
          </div>
        `).join('') : `<div class="agent-empty">Nothing pending</div>`}
      </div>
    `;
    sectionsEl.appendChild(row);
  });

  sectionsEl.querySelectorAll('.agent-card:not(.agent-card-locked)').forEach((el) => {
    el.addEventListener('click', () => {
      const item = items.find((i) => i.id === el.dataset.itemId);
      openQueueForm(item);
    });
  });
}

function openQueueForm(item) {
  const formArea = document.getElementById('queue-form-area');
  formArea.innerHTML = '';
  const renderers = {
    fact: renderFactForm,
    response: renderResponseForm,
    evidence: renderEvidenceDecisionForm,
    closure: renderClosureForm,
  };
  renderers[item.section](item, formArea);
}

// section=fact: answer the server-defined FACT-ESG-ENERGY-COVERAGE contract.
function renderFactForm(item, container) {
  const p = item.payload;
  const snapshotDate = (p.snapshot_dates || [])[0] || '';
  const card = document.createElement('div');
  card.className = 'form-card';
  card.innerHTML = `
    <div class="form-title">${escapeHtml(item.text)}</div>
    <div class="form-sub">Owner: ${escapeHtml(item.who)}</div>
    <div class="hint-text" style="margin-bottom:10px;">
      Expected unit: ${escapeHtml(p.unit || 'n/a')} · Denominator: ${escapeHtml(p.denominator || 'n/a')} ·
      Population: ${escapeHtml(p.population_product_id || 'n/a')}
    </div>
    <div class="field"><label>Value</label><input type="text" class="fact-value"></div>
    <div class="field"><label>Answered by</label><input type="text" class="fact-answered-by" value="Simulated Head of Lending"></div>
    <div class="field"><label>Source</label><input type="text" class="fact-source" value="Synthetic owner answer for demo; not operating evidence"></div>
    <label class="hint-text"><input type="checkbox" class="fact-synthetic" checked> Synthetic demo answer</label>
    <div class="error-text" style="display:none;"></div>
    <button class="btn primary" id="fact-submit">Submit answer</button>
  `;
  container.appendChild(card);
  card.querySelector('#fact-submit').addEventListener('click', async () => {
    const errEl = card.querySelector('.error-text');
    const value = Number(card.querySelector('.fact-value').value.trim());
    if (!value) {
      errEl.textContent = 'A value is required.';
      errEl.style.display = 'block';
      return;
    }
    const answeredBy = card.querySelector('.fact-answered-by').value.trim();
    const source = card.querySelector('.fact-source').value.trim();
    const denominator = Number(p.denominator);
    const numerator = value * denominator / 100;
    if (!Number.isInteger(numerator) || !answeredBy || !source || !snapshotDate) {
      errEl.textContent = 'Enter a whole-number-compatible value, answerer, source, and date.';
      errEl.style.display = 'block';
      return;
    }
    try {
      await Api.resolve(item.id, {
        value,
        unit: p.unit,
        denominator,
        numerator,
        population_product_id: p.population_product_id,
        as_of_date: snapshotDate,
        answered_by: answeredBy,
        answered_by_role_id: item.who,
        source,
        synthetic: card.querySelector('.fact-synthetic').checked,
        auto_continue: autoContinueEnabled(),
      });
      card.innerHTML = doneNote('Answer submitted.');
      renderQueue();
    } catch (err) {
      errEl.textContent = err.message;
      errEl.style.display = 'block';
    }
  });
}

// section=response: accept as drafted, modify (target_date/steps) and accept,
// or reject with a required reason. Mirrors case_store.py's accept_action
// (with its restricted overrides) and reject_action.
function renderResponseForm(item, container) {
  const p = item.payload;
  const stepsText = (p.steps || []).join('\n');
  const card = document.createElement('div');
  card.className = 'form-card';
  card.innerHTML = `
    <div class="form-title">${escapeHtml(item.text)}</div>
    <div class="form-sub">Accountable role (draft): ${escapeHtml(item.who)}</div>
    <div class="record-card-body" style="margin-bottom:10px;">
      ${fieldLine('Steps', p.steps)}
      ${fieldLine('Target date', p.target_date)}
      ${fieldLine('Regulatory due date', p.regulatory_due_date)}
      ${fieldLine('Regulatory deadline status', p.regulatory_deadline_status)}
      ${fieldLine('Required evidence', (p.required_evidence || []).map((e) => e.evidence_key).join(', ') || '(none)')}
      ${p.capacity_sufficient != null ? fieldLine('Capacity sufficient', p.capacity_sufficient ? 'Yes' : 'No') : ''}
      ${p.regulatory_deadline_feasible != null ? fieldLine('Deadline feasible', p.regulatory_deadline_feasible ? 'Yes' : 'No') : ''}
    </div>
    <div class="field"><label>Your role (role ID)</label><input type="text" class="resp-role" placeholder="ROLE-..."></div>
    <div style="display:flex;gap:8px;margin:10px 0;">
      <button class="toggle-btn active" data-mode="accept" type="button">Accept</button>
      <button class="toggle-btn" data-mode="modify" type="button">Modify &amp; accept</button>
      <button class="toggle-btn" data-mode="reject" type="button">Reject</button>
    </div>
    <div class="resp-mode-body" data-mode-body="modify" style="display:none;">
      <div class="field"><label>Target date (override)</label><input type="text" class="resp-target-date" value="${escapeHtml(p.target_date || '')}" placeholder="YYYY-MM-DD"></div>
      <div class="field"><label>Steps (override, one per line)</label><textarea class="resp-steps" rows="4">${escapeHtml(stepsText)}</textarea></div>
    </div>
    <div class="resp-mode-body" data-mode-body="reject" style="display:none;">
      <div class="field"><label>Reason for rejection</label><textarea class="resp-reason" rows="3" placeholder="Why is this action not acceptable as drafted?"></textarea></div>
    </div>
    <div class="error-text" style="display:none;"></div>
    <button class="btn primary" id="resp-submit">Accept action</button>
  `;
  container.appendChild(card);

  let mode = 'accept';
  const submitBtn = card.querySelector('#resp-submit');
  const modeLabels = { accept: 'Accept action', modify: 'Save changes & accept', reject: 'Reject action' };
  card.querySelectorAll('.toggle-btn[data-mode]').forEach((btn) => {
    btn.addEventListener('click', () => {
      mode = btn.dataset.mode;
      card.querySelectorAll('.toggle-btn[data-mode]').forEach((b) => b.classList.toggle('active', b === btn));
      card.querySelectorAll('.resp-mode-body').forEach((el) => { el.style.display = el.dataset.modeBody === mode ? 'block' : 'none'; });
      submitBtn.textContent = modeLabels[mode];
      submitBtn.className = 'btn ' + (mode === 'reject' ? 'danger' : 'primary');
    });
  });

  submitBtn.addEventListener('click', async () => {
    const errEl = card.querySelector('.error-text');
    const role = card.querySelector('.resp-role').value.trim();
    if (!role) {
      errEl.textContent = mode === 'reject' ? 'rejected_by_role_id is required.' : 'accepted_by_role_id is required.';
      errEl.style.display = 'block';
      return;
    }
    try {
      if (mode === 'reject') {
        const reason = card.querySelector('.resp-reason').value.trim();
        if (!reason) {
          errEl.textContent = 'A rejection reason is required.';
          errEl.style.display = 'block';
          return;
        }
        await Api.resolve(item.id, { decision: 'reject', rejected_by_role_id: role, reason, auto_continue: autoContinueEnabled() });
        card.innerHTML = doneNote('Action rejected.');
      } else if (mode === 'modify') {
        const targetDate = card.querySelector('.resp-target-date').value.trim();
        const steps = card.querySelector('.resp-steps').value.split('\n').map((s) => s.trim()).filter(Boolean);
        const overrides = {};
        if (targetDate && targetDate !== p.target_date) overrides.target_date = targetDate;
        if (steps.length && JSON.stringify(steps) !== JSON.stringify(p.steps || [])) overrides.steps = steps;
        await Api.resolve(item.id, { decision: 'accept', accepted_by_role_id: role, overrides, auto_continue: autoContinueEnabled() });
        card.innerHTML = doneNote('Action modified and accepted.');
      } else {
        await Api.resolve(item.id, { decision: 'accept', accepted_by_role_id: role, auto_continue: autoContinueEnabled() });
        card.innerHTML = doneNote('Action accepted.');
      }
      renderQueue();
    } catch (err) {
      errEl.textContent = err.message;
      errEl.style.display = 'block';
    }
  });
}

// section=evidence: verify or reject. The API takes no reason/comment field
// for a rejection -- only decision + decided_by_role_id.
function renderEvidenceDecisionForm(item, container) {
  const p = item.payload;
  const card = document.createElement('div');
  card.className = 'form-card';
  card.innerHTML = `
    <div class="form-title">${escapeHtml(item.text)}</div>
    <div class="form-sub">Submitted by: ${escapeHtml(item.who)}</div>
    ${p.content_assessment ? `<div class="record-card-body" style="margin-bottom:10px;">${fieldLine('Content assessment', p.content_assessment)}${p.content_rationale ? fieldLine('Content rationale', p.content_rationale) : ''}</div>` : ''}
    <div class="field"><label>Deciding role (role ID)</label><input type="text" class="ev-role" placeholder="ROLE-..."></div>
    <div class="error-text" style="display:none;"></div>
    <div style="display:flex;gap:8px;margin-top:10px;">
      <button class="btn primary" data-decision="verified">Verify</button>
      <button class="btn" data-decision="rejected">Reject</button>
    </div>
  `;
  container.appendChild(card);
  card.querySelectorAll('button[data-decision]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const errEl = card.querySelector('.error-text');
      const role = card.querySelector('.ev-role').value.trim();
      if (!role) {
        errEl.textContent = 'decided_by_role_id is required.';
        errEl.style.display = 'block';
        return;
      }
      try {
        await Api.resolve(item.id, { decision: btn.dataset.decision, decided_by_role_id: role, auto_continue: autoContinueEnabled() });
        card.innerHTML = doneNote(`Evidence marked ${btn.dataset.decision}.`);
        renderQueue();
      } catch (err) {
        errEl.textContent = err.message;
        errEl.style.display = 'block';
      }
    });
  });
}

// section=closure: only decided_by_role_id is accepted.
function renderClosureForm(item, container) {
  const card = document.createElement('div');
  card.className = 'form-card';
  card.innerHTML = `
    <div class="form-title">${escapeHtml(item.text)}</div>
    <div class="form-sub">Accountable role: ${escapeHtml(item.who)}</div>
    <div class="field"><label>Deciding role (role ID)</label><input type="text" class="close-role" placeholder="ROLE-..."></div>
    <div class="error-text" style="display:none;"></div>
    <button class="btn primary" id="close-submit">Close action</button>
  `;
  container.appendChild(card);
  card.querySelector('#close-submit').addEventListener('click', async () => {
    const errEl = card.querySelector('.error-text');
    const role = card.querySelector('.close-role').value.trim();
    if (!role) {
      errEl.textContent = 'decided_by_role_id is required.';
      errEl.style.display = 'block';
      return;
    }
    try {
      await Api.resolve(item.id, { decided_by_role_id: role, auto_continue: autoContinueEnabled() });
      card.innerHTML = doneNote('Action closed.');
      renderQueue();
    } catch (err) {
      errEl.textContent = err.message;
      errEl.style.display = 'block';
    }
  });
}

function doneNote(text) {
  return `<div class="done-note">${icon('check')}${escapeHtml(text)}</div>`;
}

renderOverview();
