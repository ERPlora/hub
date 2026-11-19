// Compares the models of several bench reports (`.artifacts/qa/<run>/bench.json` of the Hub's probes, or the SaaS's
// `.artifacts/qa/probes/<run>/bench.json`, which share the format): per model, the pass rate overall, by read or write
// tool, by language and by app; the n/a; the failures split into the ranking's (the tool was not among the tools the
// turn offered: the same for every model) and the model's, the model's by reason; the mean cost and tokens per turn,
// the p50 and p95 latency; and the probes on which the models disagree. `pnpm -s qa:bench-compare <bench.json>…`.
import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';

import type { BenchReport, BenchTurn, BenchVerdict } from './assistant-bench.ts';

export interface Rate {
  passed: number;
  asked: number;
}

export interface ModelSummary {
  label: string;
  runs: string[];
  turns: number;
  asked: number;
  passed: number;
  failed: number;
  na: number;
  rankingFailures: number;
  modelFailures: number;
  byKind: Record<string, Rate>;
  byLanguage: Record<string, Rate>;
  byApp: Record<string, Rate>;
  /** The model's failures by reason, the commonest first. */
  reasons: [string, number][];
  /** Whether every run of the model gave its prices: without them its cost is unknown. */
  priced: boolean;
  meanCostUsd: number | null;
  meanTokensIn: number | null;
  meanTokensOut: number | null;
  p50LatencyMs: number | null;
  p95LatencyMs: number | null;
  /** Turns asked and answered whose tokens came back as zero: the provider gave no usage. */
  usageMissing: number;
}

export interface Disagreement {
  probe: string;
  phrase: string;
  verdicts: Record<string, BenchVerdict>;
}

const TOOL = /\b[a-z][a-z0-9_]*(?:\.[a-z0-9_]+){2,}\b/g;

/** A reason as the summary groups it: its tools, lists and quoted values left out. */
export const reasonOf = (reason: string): string =>
  reason.replace(/\([^)]*\)/g, '(…)').replace(/«[^»]*»/g, '«…»').replace(TOOL, '<tool>');

const labelOf = (report: BenchReport): string => `${report.meta.product} · ${report.meta.model.label}`;

function grouped(reports: BenchReport[]): Map<string, BenchReport[]> {
  const groups = new Map<string, BenchReport[]>();
  for (const report of reports) groups.set(labelOf(report), [...(groups.get(labelOf(report)) ?? []), report]);
  return groups;
}

function rates(turns: BenchTurn[], key: (turn: BenchTurn) => string): Record<string, Rate> {
  const out: Record<string, Rate> = {};
  for (const turn of turns) {
    const rate = (out[key(turn)] ??= { passed: 0, asked: 0 });
    rate.asked += 1;
    if (turn.verdict === 'pass') rate.passed += 1;
  }
  return out;
}

const mean = (values: number[]): number | null => (values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null);
const known = (values: (number | null)[]): number[] => values.filter((value): value is number => value !== null);

/** The nearest-rank percentile `p` of `values`. */
function percentile(values: number[], p: number): number | null {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.max(0, Math.ceil((p / 100) * sorted.length) - 1)];
}

function counted(reasons: string[]): [string, number][] {
  const counts = new Map<string, number>();
  for (const reason of reasons) counts.set(reason, (counts.get(reason) ?? 0) + 1);
  return [...counts].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
}

function summaryOf(label: string, reports: BenchReport[]): ModelSummary {
  const turns = reports.flatMap((report) => report.turns);
  const asked = turns.filter((turn) => turn.verdict !== 'n/a');
  const failed = asked.filter((turn) => turn.verdict === 'fail');
  const ofModel = failed.filter((turn) => turn.offered !== false);
  const priced = reports.every((report) => report.meta.model.priceIn !== null && report.meta.model.priceOut !== null);
  const latencies = known(asked.map((turn) => turn.latencyMs));
  return {
    label,
    runs: reports.map((report) => report.meta.run),
    turns: turns.length,
    asked: asked.length,
    passed: asked.length - failed.length,
    failed: failed.length,
    na: turns.length - asked.length,
    rankingFailures: failed.length - ofModel.length,
    modelFailures: ofModel.length,
    byKind: rates(asked, (turn) => turn.kind),
    byLanguage: rates(asked, (turn) => turn.language),
    byApp: rates(asked, (turn) => turn.app),
    reasons: counted(ofModel.flatMap((turn) => [...new Set(turn.reasons.map(reasonOf))])),
    priced,
    meanCostUsd: priced ? mean(known(asked.map((turn) => turn.costUsd))) : null,
    meanTokensIn: mean(known(asked.map((turn) => turn.tokensIn))),
    meanTokensOut: mean(known(asked.map((turn) => turn.tokensOut))),
    p50LatencyMs: percentile(latencies, 50),
    p95LatencyMs: percentile(latencies, 95),
    usageMissing: asked.filter((turn) => !turn.error && turn.tokensIn === 0 && turn.tokensOut === 0).length,
  };
}

/** One summary per model, in the order the reports came. */
export function summarize(reports: BenchReport[]): ModelSummary[] {
  return [...grouped(reports)].map(([label, group]) => summaryOf(label, group));
}

/** The probes at least two models answered with different verdicts (a model's last turn of each probe; n/a aside). */
export function disagreements(reports: BenchReport[]): Disagreement[] {
  const byProbe = new Map<string, Disagreement>();
  for (const [label, group] of grouped(reports)) {
    for (const turn of group.flatMap((report) => report.turns)) {
      if (turn.verdict === 'n/a') continue;
      const row = byProbe.get(turn.probe) ?? { probe: turn.probe, phrase: turn.phrase, verdicts: {} };
      row.verdicts[label] = turn.verdict;
      byProbe.set(turn.probe, row);
    }
  }
  return [...byProbe.values()]
    .filter((row) => new Set(Object.values(row.verdicts)).size > 1)
    .sort((a, b) => a.probe.localeCompare(b.probe));
}

const share = (rate: Rate): string => `${((100 * rate.passed) / Math.max(rate.asked, 1)).toFixed(1)} %`;
const percent = (rate: Rate): string => `${rate.passed}/${rate.asked} (${share(rate)})`;
const listed = (by: Record<string, Rate>): string => Object.entries(by).map(([key, rate]) => `${key} ${percent(rate)}`).join(' · ') || 'none';
const seconds = (ms: number | null): string => (ms === null ? 'n/a' : `${(ms / 1000).toFixed(1)} s`);
const rounded = (value: number | null): string => (value === null ? 'n/a' : value.toFixed(0));

function modelLines(summary: ModelSummary): string[] {
  const cost = summary.priced ? `${summary.meanCostUsd?.toFixed(6) ?? 'n/a'} USD` : 'n/a (no prices given)';
  const rest = { passed: summary.passed, asked: summary.asked - summary.rankingFailures };
  return [
    `## ${summary.label}`,
    '',
    `- Runs: ${summary.runs.join(', ')} · turns ${summary.turns}`,
    `- Pass: ${summary.passed}/${summary.asked} asked (${share(summary)}) · N/A ${summary.na}`,
    `- Read: ${percent(summary.byKind.read ?? { passed: 0, asked: 0 })} · Write: ${percent(summary.byKind.write ?? { passed: 0, asked: 0 })}`,
    `- By language: ${listed(summary.byLanguage)}`,
    `- By app: ${listed(summary.byApp)}`,
    `- Failures: ${summary.failed} = ${summary.rankingFailures} ranking (the tool was not offered: the same for every model) + ${summary.modelFailures} model; without the ranking's, ${percent(rest)}`,
    `- Model failures by reason: ${summary.reasons.map(([reason, count]) => `${count} × ${reason}`).join('; ') || 'none'}`,
    `- Per turn: cost ${cost} · tokens ${rounded(summary.meanTokensIn)} in / ${rounded(summary.meanTokensOut)} out · latency p50 ${seconds(summary.p50LatencyMs)} · p95 ${seconds(summary.p95LatencyMs)}`,
    `- Turns with no tokens recorded: ${summary.usageMissing}`,
    '',
  ];
}

/** The comparison as text: one section per model, then the probes on which they disagree. */
export function renderComparison(reports: BenchReport[]): string {
  const disagreeing = disagreements(reports);
  const lines = [
    '# Assistant models compared',
    '',
    ...summarize(reports).flatMap(modelLines),
    `## Probes where the models disagree (${disagreeing.length})`,
    '',
    ...disagreeing.map((row) => {
      const verdicts = Object.entries(row.verdicts).map(([label, verdict]) => `${label} ${verdict}`).join(' · ');
      return `- ${row.probe} «${row.phrase.slice(0, 80)}»: ${verdicts}`;
    }),
  ];
  return `${lines.join('\n')}\n`;
}

export interface CompareDeps {
  read: (path: string) => string;
  print: (line: string) => void;
  fail: (line: string) => void;
}

function reportAt(path: string, deps: CompareDeps): BenchReport {
  const report = JSON.parse(deps.read(path)) as BenchReport;
  if (report.schema !== 1 || !Array.isArray(report.turns) || !report.meta?.model) throw new Error('not a bench report of schema 1');
  return report;
}

/** The script: the comparison of the reports at `args`; 2 without any, 1 when one cannot be read. */
export function runCompare(args: string[], deps: CompareDeps): number {
  if (!args.length) {
    deps.fail('usage: pnpm -s qa:bench-compare <bench.json> [<bench.json>…] (tests/e2e/README.md, «Comparar modelos»)');
    return 2;
  }
  const reports: BenchReport[] = [];
  for (const path of args) {
    try {
      reports.push(reportAt(path, deps));
    } catch (error) {
      deps.fail(`${path}: ${(error as Error).message}`);
      return 1;
    }
  }
  deps.print(renderComparison(reports));
  return 0;
}

// Run as a script (`pnpm qa:bench-compare`), not when a test imports it.
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  process.exitCode = runCompare(process.argv.slice(2), {
    read: (path) => readFileSync(path, 'utf8'),
    print: (line) => console.log(line),
    fail: (line) => console.error(line),
  });
}
