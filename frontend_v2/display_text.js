// English presentation of text emitted by older ReplayClient versions. Stored
// case objects and audit events remain untouched; this is a display projection.
// Translate only known phrases/templates, preserving unknown text and all values.
const EnglishDisplay = (() => {
  const phrases = new Map([
    ['调查及条件性成本已保存；等待明确分母的能源数据答复。', 'Investigation findings and conditional costs have been saved; awaiting an energy-data answer with an explicit denominator.'],
    ['已根据答复更新能源数据完整度；原有来源和成本发现保留。来源全文、法律审核及后续行动实施仍待完成。', 'Energy-data completeness has been updated from the answer; existing source and cost findings have been retained. Full source text, legal review and subsequent action implementation remain outstanding.'],
    ['来源限制、日期与候选范围已记录，法律解释保持 provisional。', 'Source limitations, dates and candidate scope have been recorded; the legal interpretation remains provisional.'],
    ['文本提及ESG存量监测控制/测试相关内容，与该证据类型声明相符。', 'The text refers to ESG monitoring controls or tests for the existing portfolio, consistent with the declared evidence type.'],
    ['文本未提及ESG、控制或监测，疑似与声明的证据类型无关。', 'The text lacks relevant ESG, control or monitoring content and appears unrelated to the declared evidence type.'],
    ['已读取并给出证据内容判断；最终认定与结案仍需人工决定。', 'The evidence has been read and its content assessed; final verification and closure still require human decisions.'],
    ['控制按新申请执行，不能证明存量持续监测。', 'The control runs for each new application and does not demonstrate ongoing monitoring of the existing portfolio.'],
    ['需要审核控制频率与持续监测之间的支持关系。', 'The relationship between control frequency and ongoing monitoring needs review.'],
    ['确定能源数据采集的缺失客户规模；不把该比例推断为风险水平或自动化率。', 'Determine how many borrowers need energy-data collection; do not interpret this percentage as a risk level or automation rate.'],
    ['能源数据覆盖仍未知；保留采集工作量的不确定性。', 'Energy-data coverage remains unknown; the data-collection workload is still uncertain.'],
    ['能源数据问题及相关发现已保存。', 'The energy-data question and related findings have been saved.'],
    ['本任务范围仅为存量客户ESG监测要求；自动化模板三年期成本最低，但产能与法律审核未决，先按此单一要求提出方案，其余ESG要求分开处理。', 'This task covers only ESG monitoring for existing borrowers. The automated template has the lowest three-year cost, but capacity and legal review remain unresolved. Propose a plan for this requirement and address other ESG requirements separately.'],
    ['部署自动化存量ESG监测控制', 'Implement automated ESG monitoring controls for the existing portfolio'],
    ['确认自动化监测所需数据字段与实施步骤；小范围试点验证准确性；扩大到全部存量SME客户并保留运行证据。', 'Confirm the data fields and implementation steps for automated monitoring; validate accuracy in a small pilot; extend coverage to all existing SME borrowers and retain operating evidence.'],
    ['依赖治理映射审核结论（per-application控制不能直接证明存量监测）先确认，避免重复计入同一控制的覆盖范围。', 'First confirm the governance mapping review: a per-application control does not directly demonstrate existing-portfolio monitoring. Avoid double-counting the coverage of the same control.'],
    ['存量自动化ESG监测控制设计文档', 'Control design document for automated ESG monitoring of the existing portfolio'],
    ['控制有效性测试结果', 'Control effectiveness test results'],
    ['条件性经济比较、按存量ESG监测要求单独提出的分阶段方案与责任指派（草案）已保存；责任接受、执行与证据审核仍需人工在调查之外确认，不构成已批准资源或最终整改承诺。', 'The conditional cost comparison, phased plan scoped to existing-portfolio ESG monitoring and draft responsibility assignment have been saved. Acceptance, execution and evidence review still require human confirmation outside the investigation; resources and final remediation commitments have not been approved.'],
  ]);

  function text(value) {
    let result = value;
    for (const [source, translation] of phrases) {
      result = result.replaceAll(source, translation);
    }
    return result
      .replace(/来源为已登记候选；版本检查=([^。]+)。候选范围=([^，]+)，时间=([^。]+)。使用整理后的条款转述，未独立完成原文抽取或法律审核。/g,
        'The source is a registered candidate; version check=$1. Candidate scope=$2; timing=$3. This uses curated clause paraphrases; independent source-text extraction and legal review have not been completed.')
      .replace(/两条要求的模板三年TCO：([^。]+)。团队产能未知，最低成本不等于获批建议。/g,
        'Template three-year TCO for the two requirements: $1. Team capacity is unknown; the lowest cost is not an approved recommendation.')
      .replace(/按归属明确的答复：([\d,.]+)个存量SME客户中，([\d,.]+)个有可用能源数据，([\d,.]+)个待补齐。答复不是实操证据。/g,
        'According to the attributed answer: of $1 existing SME borrowers, $2 have usable energy data and $3 still need data. The answer is not operating evidence.');
  }

  function project(value) {
    if (typeof value === 'string') return text(value);
    if (Array.isArray(value)) return value.map(project);
    if (value && typeof value === 'object') {
      return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, project(item)]));
    }
    return value;
  }

  return Object.freeze({ project });
})();

window.EnglishDisplay = EnglishDisplay;
