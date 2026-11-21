// @vitest-environment node
// What a scenario run keeps of each scenario, in the bench report family (`bench.json`) so `pnpm qa:bench-compare` puts
// models side by side: the score, the conversation, the calls and cards, and the money and time apart for the assistant
// and for the simulated owner.
import { describe, expect, it } from 'vitest';

import type { BenchMeta } from './assistant-bench';
import type { Scenario } from './assistant-scenario';
import { scenarioRow, type ScenarioRow, withScenario } from './assistant-scenario-bench';
import type { ScenarioScore, ScenarioTurn } from './assistant-scenario-score';

const scenario = { id: 's02-cake', title: 'One product said aloud', vertical: 'restaurant', language: 'es' } as Scenario;
const meta: BenchMeta = {
  product: 'hub',
  run: 'r1',
  date: '2026-11-19T20:00:00Z',
  model: { label: 'openai/qwen3.7-plus', provider: 'qa-answer', kind: 'openai', id: 'qwen3.7-plus', baseUrl: '', priceIn: 0.276, priceOut: 1.101, fallback: null },
  files: ['tests/e2e/qa/scenarios/s02-cake.json'],
  corpus: 10,
  sample: null,
  owner: { model: 'anthropic/claude-sonnet-5.5' },
};
const ask: ScenarioScore['ask'] = { said: 'half', firstMove: 'writes', writesBeforeClear: ['inventory.product.create'], right: false };
const score: ScenarioScore = { done: true, fraction: 1, forbidden: [], unwanted: [], wrongCards: [], wrongWrites: 0, mustAsk: [{ id: 'tax', outcome: 'resolved' }], invented: 0, ask };
const turns: ScenarioTurn[] = [
  {
    owner: 'Añade la tarta de zanahoria a 5,50',
    assistant: 'Hecho.',
    calls: [{ name: 'inventory.product.create', arguments: { name: 'Tarta de zanahoria' }, outcome: 'ok', code: '' }],
    cards: [{ operation: 'inventory.product.create', title: 'Crear producto', risk: 'normal', arguments: { name: 'Tarta de zanahoria' }, fields: [] }],
    executed: [],
    errors: ['assistant.cut'],
  },
];

describe('scenarioRow', () => {
  it('keeps the score, the conversation, the calls and cards, and the assistant\'s and the owner\'s spend apart', () => {
    const row = scenarioRow(scenario, {
      status: 'scored',
      why: null,
      score,
      checks: { expect: [], forbidden: [] },
      turns,
      endedBy: 'done',
      wallMs: 61_000,
      usage: { tokensIn: 9000, tokensOut: 300, tokensEmbedding: 0, costUsd: 0.0028 },
      owner: { tokensIn: 1200, tokensOut: 20, costUsd: 0.0025 },
    });
    expect(row).toMatchObject({
      scenario: 's02-cake',
      status: 'scored',
      done: true,
      fraction: 1,
      ownerMessages: 1,
      endedBy: 'done',
      wallMs: 61_000,
      costUsd: 0.0028,
      owner: { tokensIn: 1200, tokensOut: 20, costUsd: 0.0025 },
      errors: ['assistant.cut'],
      ask,
    });
    expect(row.calls.map((call) => call.name)).toEqual(['inventory.product.create']);
    expect(row.transcript).toEqual([
      { who: 'owner', text: 'Añade la tarta de zanahoria a 5,50' },
      { who: 'assistant', text: 'Hecho.', cards: ['inventory.product.create'] },
    ]);
  });

  it('records a scenario that was not asked, with why and nothing spent', () => {
    const row = scenarioRow(scenario, { status: 'not_runnable', why: 'not runnable: tools not offered on the attached message (x.y.z)' });
    expect(row).toMatchObject({ status: 'not_runnable', done: false, fraction: 0, costUsd: null, wallMs: null, ownerMessages: 0, transcript: [] });
    expect(row.ask).toEqual({ said: null, firstMove: null, writesBeforeClear: [], right: null });
  });
});

describe('withScenario', () => {
  const row = (id: string, done = true): ScenarioRow => ({ ...scenarioRow({ ...scenario, id }, { status: 'not_runnable', why: 'x' }), done });

  it('starts the run\'s report, with no probe turns, and keeps the scenarios in the run\'s order', () => {
    const first = withScenario(null, meta, row('s05-drinks'), ['s02-cake', 's05-drinks']);
    const both = withScenario(first, meta, row('s02-cake'), ['s02-cake', 's05-drinks']);
    expect(both.turns).toEqual([]);
    expect(both.scenarios?.map((kept) => kept.scenario)).toEqual(['s02-cake', 's05-drinks']);
    expect(both.meta.owner).toEqual({ model: 'anthropic/claude-sonnet-5.5' });
  });

  it('replaces a scenario asked again, and refuses another model in the same run', () => {
    const first = withScenario(null, meta, row('s02-cake', false), ['s02-cake']);
    expect(withScenario(first, meta, row('s02-cake', true), ['s02-cake']).scenarios?.map((kept) => kept.done)).toEqual([true]);
    const other = { ...meta, model: { ...meta.model, label: 'anthropic/claude-x' } };
    expect(() => withScenario(first, other, row('s02-cake'), ['s02-cake'])).toThrow(/answered by openai\/qwen3.7-plus/);
  });
});
