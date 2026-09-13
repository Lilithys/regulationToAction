const fs = require('fs');
function escapeHtml(s){return String(s==null?'':s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function icon(n){return '<svg-'+n+'>';}
function gapReviewPill(s){return '<pill-'+s+'>';}
function deadlineStatusPill(s){return '<pill-'+s+'>';}
let snippet = fs.readFileSync('tmp_verify_snippet.js', 'utf8');
snippet = snippet.replace('const AGENT_COLUMNS', 'var AGENT_COLUMNS').replace('function renderAgentColumn', 'var renderAgentColumn = function');
eval(snippet);
const inv = JSON.parse(fs.readFileSync('tmp_inv.json', 'utf8'));
const plansData = JSON.parse(fs.readFileSync('tmp_plans.json', 'utf8'));
for (const col of AGENT_COLUMNS) {
  const html = renderAgentColumn(col, inv, plansData);
  console.log('=== ' + col.role + ' (' + html.length + ' chars) ===');
}
console.log('OK: no exceptions thrown');
