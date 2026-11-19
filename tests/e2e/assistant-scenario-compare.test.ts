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
