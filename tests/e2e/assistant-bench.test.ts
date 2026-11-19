// @vitest-environment node
// The record a run of the probes keeps of each turn, to compare models: what was called with which arguments, the
// verdict, the tokens and cost the business spent, the latency, and whether the tool was offered at all.
import { spawnSync } from 'node:child_process';

import { describe, expect, it } from 'vitest';

import { observe } from './assistant-battery';
import {
  benchModel,
  type BenchMeta,
  benchTurn,
  callsOf,
  type Measured,
  OFFERED_PY,
  offeredCommand,
  parseOffered,
  parseUsage,
  toolKind,
  USAGE_SQL,
  withTurn,
} from './assistant-bench';
import type { Catalog, Probe, ProbeOutcome } from './assistant-probes';
import { answerChoice } from './assistant-seed';

const sse = (...frames: object[]): string => frames.map((frame) => `data: ${JSON.stringify(frame)}\n\n`).join('');

const PROBE: Probe = {
  id: 'owner-es-customer-1',
  app: 'customer',
  tool: 'customer.customer.create',
  role: 'owner',
  language: 'es',
  phrase: 'apunta a Rocío, su móvil es 611 222 333',
  expect: 'card',
  lookups: ['customer.customer.list'],
};

/** The model looks the customer up, then asks for the write; the card shows and the person cancels it. */
const CARD = [
  sse({
    type: 'done',
    append: [],
    pending: [{ call_id: 'c1', name: 'customer__customer__list', arguments: '{"search":"Rocío"}' }],
    continuation: 't1',
  }),
  sse(
    { type: 'executed', call_id: 'c1', name: 'customer.customer.list', kind: 'query', outcome: 'ok', code: '' },
    { type: 'done', append: [], pending: [{ call_id: 'c2', name: 'customer__customer__create', arguments: '{"name":"Rocío","phone":"611222333"}' }], continuation: 't2' },
  ),
  sse(
    { type: 'confirm', card: { operation: 'customer.customer.create', risk: 'normal', confirm_word: '' }, call: { call_id: 'c2', name: 'customer__customer__create', arguments: '{"name":"Rocío","phone":"611222333"}' } },
    { type: 'done', append: [], pending: [{ call_id: 'c2', name: 'customer__customer__create', arguments: '{"name":"Rocío","phone":"611222333"}' }], continuation: 't2' },
  ),
  sse(
    { type: 'executed', call_id: 'c2', name: 'customer.customer.create', kind: 'command', outcome: 'cancelled', code: '' },
    { type: 'text', text: 'No lo he hecho.' },
    { type: 'done', append: [], pending: [], continuation: null },
  ),
];

function outcome(bodies: string[], overrides: Partial<ProbeOutcome> = {}): ProbeOutcome {
  return {
    probe: PROBE,
    answer: 'No lo he hecho.',
    observed: observe(bodies),
    decided: 'cancelled',
    notices: [],
    screenshot: '/tmp/p.png',
    problems: [],
    ...overrides,
  };
}

const MEASURED: Measured = {
  bodies: CARD,
  latencyMs: 4200,
  usage: { tokensIn: 5100, tokensOut: 230, tokensEmbedding: 0, costUsd: 0.0021 },
  offered: ['base.setup.status', 'customer.customer.create', 'customer.customer.list'],
  kind: 'write',
  error: null,
};

const META: BenchMeta = {
  product: 'hub',
  run: 'run-1',
  date: '2026-11-19T10:00:00.000Z',
  model: benchModel(answerChoice({})),
  files: ['tests/e2e/qa/probes/owner-es-customer.json'],
  corpus: 12,
  sample: { size: 2, seed: 7 },
};

describe('callsOf', () => {
  it('lists every tool the model called, in order, once each, with its parsed arguments and how it ended', () => {
    expect(callsOf(CARD)).toEqual([
      { name: 'customer.customer.list', arguments: { search: 'Rocío' }, outcome: 'ok', code: '' },
      { name: 'customer.customer.create', arguments: { name: 'Rocío', phone: '611222333' }, outcome: 'cancelled', code: '' },
    ]);
  });

  it('keeps arguments that are not JSON as the model wrote them, and a call that never ran as pending', () => {
    const body = sse({ type: 'done', append: [], pending: [{ call_id: 'x', name: 'sale__sale__today', arguments: '{broken' }], continuation: 't' });
    expect(callsOf([body])).toEqual([{ name: 'sale.sale.today', arguments: '{broken', outcome: 'pending', code: '' }]);
  });

  it('names a refused tool the Hub ran without a call the browser saw', () => {
    const body = sse({ type: 'executed', call_id: 'z', name: 'staff.member.create', kind: 'command', outcome: 'refused', code: 'not_offered' });
    expect(callsOf([body])).toEqual([{ name: 'staff.member.create', arguments: null, outcome: 'refused', code: 'not_offered' }]);
  });
});

describe('benchTurn', () => {
  it('records the probe, the calls, the card, the verdict, the rounds, the spend and the latency of a turn', () => {
    expect(benchTurn(outcome(CARD), MEASURED)).toEqual({
      probe: 'owner-es-customer-1',
      app: 'customer',
      phrase: PROBE.phrase,
      role: 'owner',
      language: 'es',
      surface: 'hub',
      expect: 'card',
      kind: 'write',
      tool: 'customer.customer.create',
      lookups: ['customer.customer.list'],
      offered: true,
      calls: callsOf(CARD),
      card: true,
      cards: ['customer.customer.create'],
      verdict: 'pass',
      reasons: [],
      rounds: 4,
      tokensIn: 5100,
      tokensOut: 230,
      tokensEmbedding: 0,
      costUsd: 0.0021,
      latencyMs: 4200,
      error: null,
    });
  });

  it('says the tool was not offered when the ranking left it out, and fails the turn with its reason', () => {
    const turn = benchTurn(outcome([sse({ type: 'text', text: 'Hola' }, { type: 'done', append: [], pending: [] })], { answer: 'Hola', decided: 'none' }), {
      ...MEASURED,
      bodies: [],
      offered: ['base.setup.status'],
    });
    expect(turn.offered).toBe(false);
    expect(turn.verdict).toBe('fail');
    expect(turn.reasons).toEqual(['no card of customer.customer.create (cards: none)', 'the card was not cancelled']);
    expect(turn.card).toBe(false);
  });

  it('records the error a turn ended with, and the one of a turn that never finished', () => {
    const failed = [sse({ type: 'error', code: 'assistant.provider_failed', retriable: true }, { type: 'done', append: [], pending: [] })];
    expect(benchTurn(outcome(failed, { answer: '' }), { ...MEASURED, bodies: failed }).error).toBe('assistant.provider_failed');
    const stuck = benchTurn(outcome([], { answer: '' }), { ...MEASURED, bodies: [], error: 'the turn did not end within 240000 ms' });
    expect(stuck).toMatchObject({ verdict: 'fail', error: 'the turn did not end within 240000 ms', rounds: 0 });
    expect(stuck.reasons).toContain('the turn did not end within 240000 ms');
  });

  it('records a probe that was not asked as n/a, with nothing spent nor offered', () => {
    const turn = benchTurn(outcome([], { problems: ['no tool x in the owner’s catalogue'] }), {
      ...MEASURED,
      bodies: [],
      latencyMs: null,
      usage: null,
    });
    expect(turn).toMatchObject({ verdict: 'n/a', reasons: ['no tool x in the owner’s catalogue'], offered: null, tokensIn: null, costUsd: null, latencyMs: null });
  });

  it('does not say whether a refused tool was offered: the role never holds it', () => {
    const refused = outcome([], { probe: { ...PROBE, expect: 'refused', role: 'employee' }, answer: 'No tienes permiso: pídeselo al propietario.' });
    expect(benchTurn(refused, { ...MEASURED, bodies: [] }).offered).toBeNull();
  });
});

describe('toolKind', () => {
  const owner: Catalog = [
    { name: 'customer.customer.create', tool_name: '', app_label: 'customer', kind: 'write', permission: '', risk: '', description: '', asks: [] },
  ];

  it('is the kind of the probe’s tool in the owner’s catalogue, else what the probe expects', () => {
    expect(toolKind({ ...PROBE, expect: 'refused' }, { 'owner/es': owner })).toBe('write');
    expect(toolKind({ ...PROBE, tool: 'sale.sale.today', expect: 'read' }, { 'owner/es': owner })).toBe('read');
    expect(toolKind({ ...PROBE, tool: 'gone.thing.create', expect: 'card' }, {})).toBe('write');
  });
});

describe('parseUsage', () => {
  it('reads the tokens and the cost the business spent, as the SQL sums them', () => {
    expect(parseUsage('5100|230|12|0.002100')).toEqual({ tokensIn: 5100, tokensOut: 230, tokensEmbedding: 12, costUsd: 0.0021 });
    expect(USAGE_SQL).toContain("slug = 'a'");
    expect(USAGE_SQL).toContain('assistant_assistantusage');
  });

  it('refuses a line it cannot read instead of recording zeros', () => {
    expect(() => parseUsage('')).toThrow(/usage/);
    expect(() => parseUsage('1|2|x|0')).toThrow(/usage/);
  });
});

describe('offered', () => {
  it('ranks the probes’ phrases in the Hub as a turn does, the probes in a file and not in the arguments', () => {
    const command = offeredCommand('/tmp/probes.json', { PATH: '/bin' });
    expect(command).toEqual({ file: 'uv', args: ['run', 'python', 'manage.py', 'shell', '-c', OFFERED_PY], env: { PATH: '/bin', QA_OFFERED_FILE: '/tmp/probes.json' } });
    expect(OFFERED_PY).toContain('assistant.relevance.relevant(');
    expect(OFFERED_PY).toContain('assistant.tools.catalog(');
    const parsed = spawnSync('python3', ['-c', 'import ast, sys; ast.parse(sys.stdin.read())'], { input: OFFERED_PY, encoding: 'utf8' });
    expect(parsed.status, parsed.stderr).toBe(0);
  });

  it('reads the last line the shell printed', () => {
    expect(parseOffered('12 objects imported automatically\n{"p1": ["a.b.c"]}\n')).toEqual({ p1: ['a.b.c'] });
  });
});

describe('withTurn', () => {
  const turn = benchTurn(outcome(CARD), MEASURED);
  const other = { ...turn, probe: 'owner-es-customer-0' };

  it('starts the report of a run and keeps its turns in the order of the run’s probes', () => {
    const first = withTurn(null, META, turn, ['owner-es-customer-0', 'owner-es-customer-1']);
    const both = withTurn(first, META, other, ['owner-es-customer-0', 'owner-es-customer-1']);
    expect(both).toEqual({ schema: 1, meta: META, turns: [other, turn] });
  });

  it('replaces a probe asked again in the same run and starts over for another run', () => {
    const first = withTurn(null, META, turn, [turn.probe]);
    const again = withTurn(first, META, { ...turn, verdict: 'fail' }, [turn.probe]);
    expect(again.turns.map((row) => row.verdict)).toEqual(['fail']);
    expect(withTurn(first, { ...META, run: 'run-2' }, other, [other.probe]).turns).toEqual([other]);
  });

  it('refuses to mix two models in one run', () => {
    const first = withTurn(null, META, turn, [turn.probe]);
    const other = { ...META, model: benchModel(answerChoice({ QA_ANSWER_KIND: 'openai', QA_ANSWER_MODEL: 'gpt-x', QA_ANSWER_KEY_ENV: 'K', QA_ANSWER_PRICE_IN: '1', QA_ANSWER_PRICE_OUT: '2' })) };
    expect(() => withTurn(first, other, turn, [turn.probe])).toThrow(/openai\/qwen3.7-plus/);
  });
});

describe('benchModel', () => {
  it('names the model that answers by its kind and id, with its address, prices, fallback and whether it sees images', () => {
    expect(benchModel(answerChoice({}))).toEqual({
      label: 'openai/qwen3.7-plus + gpt-5.4-mini',
      provider: 'qwen',
      kind: 'openai',
      id: 'qwen3.7-plus',
      baseUrl: answerChoice({}).baseUrl,
      priceIn: null,
      priceOut: null,
      fallback: 'gpt-5.4-mini',
      vision: false,
    });
  });
});
