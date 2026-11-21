// @vitest-environment node
// The scenarios of several runs side by side, per model: jobs done, how much of each job, facts invented, wrong
// writes, money per finished job and time per job, with the scenarios that were not asked counted apart.
import { describe, expect, it } from 'vitest';

import type { BenchReport } from './assistant-bench';
import { renderComparison } from './assistant-bench-compare';
import type { ScenarioRow } from './assistant-scenario-bench';
import { renderScenarios, summarizeScenarios } from './assistant-scenario-compare';

const row = (scenario: string, changes: Partial<ScenarioRow> = {}): ScenarioRow => ({
  scenario,
  title: scenario,
  vertical: 'restaurant',
  language: 'es',
  status: 'scored',
  why: null,
  done: true,
  fraction: 1,
  checks: { expect: [], forbidden: [] },
  forbidden: [],
  unwanted: [],
  wrongCards: [],
  wrongWrites: 0,
  mustAsk: [],
  invented: 0,
  ask: { said: null, firstMove: 'writes', writesBeforeClear: [], right: null },
  ownerMessages: 3,
  endedBy: 'done',
  wallMs: 60_000,
  tokensIn: 10_000,
  tokensOut: 500,
  tokensEmbedding: 0,
  costUsd: 0.004,
  owner: { tokensIn: 2000, tokensOut: 40, costUsd: 0.003 },
  calls: [],
  cards: [],
  errors: [],
  transcript: [],
  ...changes,
});

const report = (label: string, rows: ScenarioRow[], priced = true): BenchReport => ({
  schema: 1,
  meta: {
    product: 'hub',
    run: `run-${label}`,
    date: '2026-11-19',
    model: { label, provider: 'qa-answer', kind: 'openai', id: label, baseUrl: '', priceIn: priced ? 1 : null, priceOut: priced ? 1 : null, fallback: null },
    files: [],
    corpus: rows.length,
    sample: null,
    owner: { model: 'anthropic/claude-sonnet-5.5' },
  },
  turns: [],
  scenarios: rows,
});

describe('summarizeScenarios', () => {
  it('counts per model the jobs done, the share of each job, the invented facts, the wrong writes, money and time', () => {
    const [summary] = summarizeScenarios([
      report('m1', [
        row('s01'),
        row('s02', { done: false, fraction: 0.5, invented: 2, wrongWrites: 1, costUsd: 0.006, wallMs: 120_000, mustAsk: [{ id: 'a', outcome: 'invented' }, { id: 'b', outcome: 'asked' }] }),
        row('s03', { status: 'not_runnable', why: 'not runnable: tools not offered on the attached message (x.y.z)', done: false, fraction: 0, costUsd: null, wallMs: null }),
        row('s04', { status: 'excluded', why: 'golden path: step 2 failed', done: false, fraction: 0, costUsd: null, wallMs: null }),
      ]),
    ]);
    expect(summary).toMatchObject({
      label: 'm1',
      scored: 2,
      done: 1,
      meanFraction: 0.75,
      invented: 2,
      asked: 1,
      wrongWrites: 1,
      notRunnable: 1,
      excluded: 1,
      totalCostUsd: 0.01,
      costPerDoneUsd: 0.01,
      meanSeconds: 90,
      ownerCostUsd: 0.006,
    });
  });

  it('keeps the money unknown without prices, and per finished job unknown with none finished', () => {
    const [unpriced] = summarizeScenarios([report('m2', [row('s01')], false)]);
    expect(unpriced.totalCostUsd).toBeNull();
    const [none] = summarizeScenarios([report('m3', [row('s01', { done: false, fraction: 0.2 })])]);
    expect(none.costPerDoneUsd).toBeNull();
  });
});

describe('summarizeScenarios, asking before acting', () => {
  const ask = (said: 'half' | 'whole', firstMove: 'asks' | 'writes', right: boolean, writes: string[] = []): ScenarioRow['ask'] => ({ said, firstMove, writesBeforeClear: writes, right });
  const rows = [
    row('s11', { ask: ask('half', 'writes', false, ['inventory.stock.write_off']) }),
    row('s13', { done: false, fraction: 0, ask: ask('half', 'asks', true) }),
    row('s12', { ask: ask('whole', 'writes', true, ['inventory.stock.write_off']) }),
    row('s14', { done: false, fraction: 0, ask: ask('whole', 'asks', false) }),
    row('s01'),
    row('s15', { status: 'excluded', why: 'golden path: step 1 failed', done: false, fraction: 0, ask: { said: null, firstMove: null, writesBeforeClear: [], right: null } }),
  ];

  it('counts apart the jobs said by halves that asked before writing, their writes before the owner made it clear, and the jobs said whole that were done', () => {
    const [summary] = summarizeScenarios([report('m1', rows)]);
    expect(summary.ask).toEqual({ half: 2, askedFirst: 1, writesBeforeClear: 1, whole: 2, wholeDone: 1 });
  });

  it('writes the line of asking first, and leaves it out when no scenario says how the job is said', () => {
    expect(renderScenarios([report('m1', rows)])).toContain('- Asking first: 1/2 said by halves asked before writing · 1 write before the owner made it clear · 1/2 said whole done');
    expect(renderScenarios([report('m1', [row('s01')])])).not.toContain('Asking first');
  });

  it('counts a row of a report kept from before the measure, which has no ask, in neither group', () => {
    const kept: Partial<ScenarioRow> = row('s01');
    delete kept.ask;
    const [summary] = summarizeScenarios([report('m1', [kept as ScenarioRow, ...rows])]);
    expect(summary.ask).toEqual({ half: 2, askedFirst: 1, writesBeforeClear: 1, whole: 2, wholeDone: 1 });
    expect(renderScenarios([report('m1', [kept as ScenarioRow])])).not.toContain('Asking first');
  });
});

describe('renderScenarios', () => {
  it('writes a section per model and a table of each scenario per model', () => {
    const text = renderScenarios([report('m1', [row('s01'), row('s02', { done: false, fraction: 0.5 })]), report('m2', [row('s01', { done: false, fraction: 0 }), row('s02')])]);
    expect(text).toContain('# Scenarios compared');
    expect(text).toContain('## m1');
    expect(text).toContain('- Jobs done: 1/2 scored (50.0 %)');
    expect(text).toContain('| s01 | done | 0 % |');
    expect(text).toContain('| s02 | 50 % | done |');
  });

  it('says the wrong writes of a job that is not done, so a job whose checks all hold but broke something reads as such', () => {
    const text = renderScenarios([report('m1', [row('s01', { done: false, fraction: 1, wrongWrites: 2 })])]);
    expect(text).toContain('| s01 | 100 %, 2 wrong writes |');
  });

  it('puts every run of a model in its cell: how many were done and the mean share, not just the last run', () => {
    const runs = [
      { ...report('m1', [row('s01'), row('s02', { done: false, fraction: 0.5, wrongWrites: 1 })]), meta: { ...report('m1', []).meta, run: 'r1' } },
      { ...report('m1', [row('s01', { done: false, fraction: 0.2 }), row('s02', { done: false, fraction: 1 })]), meta: { ...report('m1', []).meta, run: 'r2' } },
    ];
    const text = renderScenarios(runs);
    expect(text).toContain('| s01 | 1/2 done · 60 % |');
    expect(text).toContain('| s02 | 0/2 done · 75 %, 1 wrong write |');
  });

  it('is empty without scenario reports', () => {
    expect(renderScenarios([])).toBe('');
  });
});

describe('renderComparison with scenario reports', () => {
  it('compares the probes of the probe reports and the scenarios of the scenario reports', () => {
    const text = renderComparison([report('m1', [row('s01')])]);
    expect(text).toContain('# Scenarios compared');
    expect(text).not.toContain('# Assistant models compared');
    const probes: BenchReport = { ...report('m0', []), turns: [], scenarios: undefined };
    const both = renderComparison([probes, report('m1', [row('s01')])]);
    expect(both.indexOf('# Assistant models compared')).toBeLessThan(both.indexOf('# Scenarios compared'));
    expect(both).toMatch(/## .*m0/);
  });
});
