// The scenarios of several scenario runs (`bench.json` with `scenarios`, assistant-scenario-bench.ts) side by side, per
// model: the jobs done, the mean share of each job, the facts to ask that were asked, found or invented, the wrong
// writes, the assistant's money in total and per finished job, the time per job and the owner's messages, the simulated
// owner's money apart, and the scenarios not asked (a precheck, or a golden path that failed) counted apart; then a table
// of each scenario per model. assistant-bench-compare.ts prints it after the probes. Pure, so Vitest proves it.
import type { BenchReport } from './assistant-bench.ts';
import type { ScenarioRow } from './assistant-scenario-bench.ts';

export interface ScenarioSummary {
  label: string;
  runs: string[];
  scored: number;
  done: number;
  meanFraction: number | null;
  asked: number;
  resolved: number;
  invented: number;
  wrongWrites: number;
  notRunnable: number;
  excluded: number;
  /** The assistant's money over the scored scenarios; null when the model has no prices. */
  totalCostUsd: number | null;
  costPerDoneUsd: number | null;
  meanSeconds: number | null;
  meanOwnerMessages: number | null;
  ownerCostUsd: number | null;
}

const money = (value: number): number => Math.round(value * 1e6) / 1e6;
const mean = (values: number[]): number | null => (values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null);
const sum = (values: number[]): number => values.reduce((total, value) => total + value, 0);
const facts = (rows: ScenarioRow[], outcome: string): number => rows.flatMap((row) => row.mustAsk).filter((fact) => fact.outcome === outcome).length;

function grouped(reports: BenchReport[]): Map<string, BenchReport[]> {
  const groups = new Map<string, BenchReport[]>();
  for (const report of reports.filter((kept) => kept.scenarios)) groups.set(report.meta.model.label, [...(groups.get(report.meta.model.label) ?? []), report]);
  return groups;
}

function summaryOf(label: string, group: BenchReport[]): ScenarioSummary {
  const rows = group.flatMap((report) => report.scenarios ?? []);
  const scored = rows.filter((row) => row.status === 'scored');
  const done = scored.filter((row) => row.done).length;
  const priced = group.every((report) => report.meta.model.priceIn !== null && report.meta.model.priceOut !== null);
  const total = priced ? money(sum(scored.map((row) => row.costUsd ?? 0))) : null;
  const owners = scored.map((row) => row.owner.costUsd);
  return {
    label,
    runs: group.map((report) => report.meta.run),
    scored: scored.length,
    done,
    meanFraction: mean(scored.map((row) => row.fraction)),
    asked: facts(scored, 'asked'),
    resolved: facts(scored, 'resolved'),
    invented: sum(scored.map((row) => row.invented)),
    wrongWrites: sum(scored.map((row) => row.wrongWrites)),
    notRunnable: rows.filter((row) => row.status === 'not_runnable').length,
    excluded: rows.filter((row) => row.status === 'excluded').length,
    totalCostUsd: total,
    costPerDoneUsd: total !== null && done ? money(total / done) : null,
    meanSeconds: mean(scored.map((row) => (row.wallMs ?? 0) / 1000)),
    meanOwnerMessages: mean(scored.map((row) => row.ownerMessages)),
    ownerCostUsd: owners.some((cost) => cost === null) ? null : money(sum(owners as number[])),
  };
}

/** One summary per model that has scenario reports, in the order the reports came. */
export function summarizeScenarios(reports: BenchReport[]): ScenarioSummary[] {
  return [...grouped(reports)].map(([label, group]) => summaryOf(label, group));
}

const usd = (value: number | null): string => (value === null ? 'n/a' : `${value.toFixed(4)} USD`);
const share = (part: number, whole: number): string => `${((100 * part) / Math.max(whole, 1)).toFixed(1)} %`;
const fixed = (value: number | null, digits: number, unit = ''): string => (value === null ? 'n/a' : `${value.toFixed(digits)}${unit}`);

function modelLines(summary: ScenarioSummary): string[] {
  return [
    `## ${summary.label}`,
    '',
    `- Runs: ${summary.runs.join(', ')}`,
    `- Jobs done: ${summary.done}/${summary.scored} scored (${share(summary.done, summary.scored)}) · mean share of the job ${fixed(summary.meanFraction === null ? null : 100 * summary.meanFraction, 1, ' %')}`,
    `- Facts to ask: ${summary.asked} asked · ${summary.resolved} found with a read · ${summary.invented} invented`,
    `- Wrong writes: ${summary.wrongWrites}`,
    `- Not asked: ${summary.notRunnable} not runnable (the same for every model) · ${summary.excluded} excluded (setup or golden path failed)`,
    `- Money: ${usd(summary.totalCostUsd)} in total · ${usd(summary.costPerDoneUsd)} per finished job · simulated owner ${usd(summary.ownerCostUsd)} apart`,
    `- Time per job: ${fixed(summary.meanSeconds, 1, ' s')} · owner messages ${fixed(summary.meanOwnerMessages, 1)}`,
    '',
  ];
}

const wrongOf = (count: number): string => (count ? `, ${count} wrong write${count === 1 ? '' : 's'}` : '');

function single(row: ScenarioRow): string {
  if (row.done) return 'done';
  return `${Math.round(100 * row.fraction)} %${wrongOf(row.wrongWrites)}`;
}

/** A model's runs of one scenario: one run as it ended, several as how many were done and the mean share. */
function cell(rows: ScenarioRow[]): string {
  const scored = rows.filter((row) => row.status === 'scored');
  if (!scored.length) return rows.length ? rows[0].status.replace('_', ' ') : '—';
  if (scored.length === 1) return single(scored[0]);
  const done = scored.filter((row) => row.done).length;
  const share = Math.round((100 * scored.reduce((sum, row) => sum + row.fraction, 0)) / scored.length);
  return `${done}/${scored.length} done · ${share} %${wrongOf(scored.reduce((sum, row) => sum + row.wrongWrites, 0))}`;
}

function table(reports: BenchReport[], labels: string[]): string[] {
  const byModel = new Map(labels.map((label) => [label, new Map<string, ScenarioRow[]>()]));
  for (const report of reports) {
    const rows = byModel.get(report.meta.model.label);
    for (const row of report.scenarios ?? []) rows?.set(row.scenario, [...(rows.get(row.scenario) ?? []), row]);
  }
  const ids = [...new Set(reports.flatMap((report) => (report.scenarios ?? []).map((row) => row.scenario)))];
  return [
    `| Scenario | ${labels.join(' | ')} |`,
    `|---|${labels.map(() => '---').join('|')}|`,
    ...ids.map((id) => `| ${id} | ${labels.map((label) => cell(byModel.get(label)?.get(id) ?? [])).join(' | ')} |`),
  ];
}

/** The scenarios compared as text, or nothing without scenario reports. */
export function renderScenarios(reports: BenchReport[]): string {
  const summaries = summarizeScenarios(reports);
  if (!summaries.length) return '';
  const lines = ['# Scenarios compared', '', ...summaries.flatMap(modelLines), ...table(reports, summaries.map((summary) => summary.label))];
  return `${lines.join('\n')}\n`;
}
