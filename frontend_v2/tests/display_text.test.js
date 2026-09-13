const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const { test } = require('node:test');
const vm = require('node:vm');

function client(fetch) {
  const context = vm.createContext({ window: {}, location: { hostname: 'localhost' }, fetch });
  for (const file of ['display_text.js', 'api.js']) {
    vm.runInContext(readFileSync(join(__dirname, '..', file), 'utf8'), context);
  }
  return context.window;
}

test('legacy nested records render in English without changing source data or identifiers', () => {
  const { EnglishDisplay } = client();
  const original = {
    id: 'response:action-1', revision: 3, approved: false, capacity: null,
    text: '部署自动化存量ESG监测控制',
    payload: { required_evidence: [{ evidence_key: 'test', title: '控制有效性测试结果' }] },
  };
  const before = JSON.stringify(original);
  const projected = EnglishDisplay.project(original);
  assert.equal(projected.text, 'Implement automated ESG monitoring controls for the existing portfolio');
  assert.equal(projected.payload.required_evidence[0].title, 'Control effectiveness test results');
  assert.equal(projected.payload.required_evidence[0].evidence_key, 'test');
  for (const key of ['id', 'revision', 'approved', 'capacity']) assert.equal(projected[key], original[key]);
  assert.equal(JSON.stringify(original), before);
});

test('dynamic summaries preserve actual counts, cost amounts and status values', () => {
  const { EnglishDisplay } = client();
  const summaries = [
    '按归属明确的答复：12000个存量SME客户中，7800个有可用能源数据，4200个待补齐。答复不是实操证据。',
    "两条要求的模板三年TCO：{'OPT-ESG-AUTOMATED': 123456.78}。团队产能未知，最低成本不等于获批建议。",
    '来源为已登记候选；版本检查=insufficient_source_snapshots。候选范围=in_scope，时间=application_date_reached。使用整理后的条款转述，未独立完成原文抽取或法律审核。',
  ];
  const translated = EnglishDisplay.project(summaries);
  assert.doesNotMatch(JSON.stringify(translated), /\p{Script=Han}/u);
  assert.match(translated[0], /12000.*7800.*4200/);
  assert.match(translated[0], /not operating evidence/);
  assert.match(translated[1], /'OPT-ESG-AUTOMATED': 123456\.78/);
  assert.match(translated[1], /not an approved recommendation/);
  assert.match(translated[2], /insufficient_source_snapshots.*in_scope.*application_date_reached/);
});

test('composed evidence and closure queue labels also render in English', () => {
  const { EnglishDisplay } = client();
  assert.equal(EnglishDisplay.project('控制有效性测试结果 needs a verify/reject decision'),
    'Control effectiveness test results needs a verify/reject decision');
  assert.equal(EnglishDisplay.project('All required evidence verified for 部署自动化存量ESG监测控制; ready to close'),
    'All required evidence verified for Implement automated ESG monitoring controls for the existing portfolio; ready to close');
});

test('unknown text is preserved rather than guessed or hidden', () => {
  const { EnglishDisplay } = client();
  for (const text of ['An English finding.', '客户提供的原始备注', '<script>alert(1)</script>']) {
    assert.equal(EnglishDisplay.project(text), text);
  }
});

test('GET projections translate nested audit details; POST content stays unchanged', async () => {
  const raw = { detail: { arguments: { summary: '能源数据问题及相关发现已保存。' } } };
  const calls = [];
  const { Api } = client(async (url, options) => {
    calls.push({ url, options });
    return { ok: true, json: async () => raw };
  });
  Api.caseId = 'CASE-1';
  assert.equal((await Api.audit()).detail.arguments.summary,
    'The energy-data question and related findings have been saved.');
  const body = { reason: '客户提供的原始备注', accepted_by_role_id: 'ROLE-CHIEF-RISK' };
  assert.equal(await Api.resolve('response:action-1', body), raw);
  assert.equal(calls[1].options.body, JSON.stringify(body));
  assert.match(calls[1].url, /response%3Aaction-1/);
  assert.equal(raw.detail.arguments.summary, '能源数据问题及相关发现已保存。');
});

test('HTTP errors still propagate instead of turning into display data', async () => {
  const { Api } = client(async () => ({ ok: false, status: 403, json: async () => ({ message: 'Forbidden' }) }));
  await assert.rejects(Api.cases(), /Forbidden/);
});
