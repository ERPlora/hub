// @vitest-environment node
// The comparison of several bench reports (`pnpm -s qa:bench-compare <bench.json>…`): per model, the pass rates, the
// failures split into the ranking's and the model's, the cost, tokens and latency per turn, and the probes on which
// the models disagree.
import { describe, expect, it } from 'vitest';

import type { BenchMeta, BenchReport, BenchTurn } from './assistant-bench';
import { disagreements, reasonOf, renderComparison, runCompare, summarize } from './assistant-bench-compare';

function turn(probe: string, overrides: Partial<BenchTurn> = {}): BenchTurn {
  return {
    probe,
    app: 'sale',
    phrase: `phrase of ${probe}`,
    role: 'owner',
    language: 'es',
    surface: 'hub',
    expect: 'read',
    kind: 'read',
    tool: 'sale.sale.today',
    lookups: [],
    offered: true,
    calls: [],
    card: false,
    cards: [],
    verdict: 'pass',
    reasons: [],
    rounds: 2,
    tokensIn: 1000,
    tokensOut: 100,
    tokensEmbedding: 0,
    costUsd: 0.001,
    latencyMs: 1000,
    error: null,
    ...overrides,
  };
}

function report(label: string, turns: BenchTurn[], priced = true, run = `run-${label}`): BenchReport {
  const meta: BenchMeta = {
    product: 'hub',
    run,
    date: '2026-11-19T10:00:00.000Z',
    model: { label, provider: 'qa-answer', kind: 'openai', id: label, baseUrl: '', priceIn: priced ? 1 : null, priceOut: priced ? 2 : null, fallback: null },
    files: ['tests/e2e/qa/probes/a.json'],
    corpus: 10,
    sample: { size: 4, seed: 1 },
  };
  return { schema: 1, meta, turns };
}

const A = report('model-a', [
  turn('p1'),
  turn('p2', { kind: 'write', expect: 'card', app: 'customer', verdict: 'fail', reasons: ['no card of customer.customer.create (cards: none)'], latencyMs: 3000, costUsd: 0.003 }),
  turn('p3', { language: 'en', verdict: 'fail', offered: false, reasons: ['sale.sale.today did not run (ran: none)'], latencyMs: 2000 }),
  turn('p4', { verdict: 'n/a', reasons: ['no tool'], tokensIn: null, tokensOut: null, costUsd: null, latencyMs: null }),
]);
const B = report(
  'model-b',
  [
    turn('p1', { verdict: 'fail', reasons: ['the first tool called was sale.sale.list, not sale.sale.today'], tokensIn: 0, tokensOut: 0, costUsd: 0 }),
    turn('p2', { kind: 'write', expect: 'card', app: 'customer' }),
    turn('p3', { language: 'en', verdict: 'fail', offered: false, reasons: ['sale.sale.today did not run (ran: none)'] }),
    turn('p4', { verdict: 'n/a', reasons: ['no tool'], tokensIn: null, tokensOut: null, costUsd: null, latencyMs: null }),
  ],
  false,
);

describe('reasonOf', () => {
  it('groups reasons by what failed, without the tools, values and lists of one turn', () => {
    expect(reasonOf('no card of customer.customer.create (cards: none)')).toBe('no card of <tool> (…)');
    expect(reasonOf('the first tool called was sale.sale.list, not sale.sale.today')).toBe('the first tool called was <tool>, not <tool>');
    expect(reasonOf('the turn ended with the error assistant.provider_failed')).toBe('the turn ended with the error assistant.provider_failed');
  });
});

describe('summarize', () => {
  const [a, b] = summarize([A, B]);

  it('counts the pass rate over the probes asked, by kind, language and app, and the n/a apart', () => {
    expect(a).toMatchObject({ label: 'hub · model-a', turns: 4, asked: 3, passed: 1, failed: 2, na: 1 });
    expect(a.byKind).toEqual({ read: { passed: 1, asked: 2 }, write: { passed: 0, asked: 1 } });
    expect(a.byLanguage).toEqual({ es: { passed: 1, asked: 2 }, en: { passed: 0, asked: 1 } });
    expect(a.byApp).toEqual({ sale: { passed: 1, asked: 2 }, customer: { passed: 0, asked: 1 } });
  });

  it('tells the failures of the ranking (the tool was not offered) from the model’s, and the model’s by reason', () => {
    expect(a).toMatchObject({ rankingFailures: 1, modelFailures: 1 });
    expect(a.reasons).toEqual([['no card of <tool> (…)', 1]]);
    expect(b.reasons).toEqual([['the first tool called was <tool>, not <tool>', 1]]);
  });

  it('gives the mean cost and tokens and the p50 and p95 latency of the turns asked', () => {
    expect(a.meanCostUsd).toBeCloseTo(0.005 / 3);
    expect(a).toMatchObject({ meanTokensIn: 1000, meanTokensOut: 100, p50LatencyMs: 2000, p95LatencyMs: 3000, priced: true });
  });

  it('gives no cost without the prices of the model, and counts the turns whose tokens never came', () => {
    expect(b).toMatchObject({ priced: false, meanCostUsd: null, usageMissing: 1 });
    expect(a.usageMissing).toBe(0);
  });
});

describe('disagreements', () => {
  it('lists the probes asked of every model with different verdicts, each model’s verdict', () => {
    expect(disagreements([A, B])).toEqual([
      { probe: 'p1', phrase: 'phrase of p1', verdicts: { 'hub · model-a': 'pass', 'hub · model-b': 'fail' } },
      { probe: 'p2', phrase: 'phrase of p2', verdicts: { 'hub · model-a': 'fail', 'hub · model-b': 'pass' } },
    ]);
  });

  it('takes the last turn of a probe asked twice of the same model', () => {
    const again = report('model-a', [turn('p1', { verdict: 'fail', reasons: ['x'] })], true, 'run-a2');
    expect(disagreements([A, again, B]).map((row) => row.probe)).toEqual(['p2']);
  });
});

describe('renderComparison', () => {
  const text = renderComparison([A, B]);

  it('prints each model with its rates, failures split, spend and latency', () => {
    expect(text).toContain('## hub · model-a');
    expect(text).toContain('Pass: 1/3 asked (33.3 %) · N/A 1');
    expect(text).toContain('Read: 1/2 (50.0 %) · Write: 0/1 (0.0 %)');
    expect(text).toContain('Failures: 2 = 1 ranking (the tool was not offered: the same for every model) + 1 model');
    expect(text).toContain('cost 0.001667 USD');
    expect(text).toContain('cost n/a (no prices given)');
    expect(text).toContain('latency p50 2.0 s · p95 3.0 s');
    expect(text).toContain('Turns with no tokens recorded: 1');
  });

  it('lists the probes the models disagree on', () => {
    expect(text).toContain('## Probes where the models disagree (2)');
    expect(text).toContain('- p1 «phrase of p1»: hub · model-a pass · hub · model-b fail');
  });
});

describe('runCompare', () => {
  const deps = (files: Record<string, string>) => {
    const out: string[] = [];
    const err: string[] = [];
    return {
      out,
      err,
      deps: { read: (path: string) => files[path] ?? (() => { throw new Error(`ENOENT ${path}`); })(), print: (line: string) => out.push(line), fail: (line: string) => err.push(line) },
    };
  };

  it('prints the comparison of the reports it is given', () => {
    const run = deps({ 'a.json': JSON.stringify(A), 'b.json': JSON.stringify(B) });
    expect(runCompare(['a.json', 'b.json'], run.deps)).toBe(0);
    expect(run.out.join('\n')).toContain('## hub · model-b');
  });

  it('says how it is used without reports, and names a report it cannot read', () => {
    const none = deps({});
    expect(runCompare([], none.deps)).toBe(2);
    expect(none.err.join('\n')).toMatch(/usage/);
    const broken = deps({ 'x.json': '{"schema": 2}' });
    expect(runCompare(['x.json'], broken.deps)).toBe(1);
    expect(broken.err.join('\n')).toContain('x.json');
  });
});
