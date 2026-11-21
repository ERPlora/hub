// @vitest-environment node
// The score of a scenario: whether the job ended done in the database, how much of it, the writes it should not have
// made, and for each fact the owner keeps back whether the assistant asked for it, found it with a tool or invented it.
import { describe, expect, it } from 'vitest';

import type { Scenario } from './assistant-scenario';
import { checked, classify, valueAt, scoreScenario, type ScenarioTurn } from './assistant-scenario-score';

const call = (name: string, args: unknown, outcome = 'ok') => ({ name, arguments: args, outcome, code: '' });
const turn = (owner: string, calls: ScenarioTurn['calls'] = [], extra: Partial<ScenarioTurn> = {}): ScenarioTurn => ({ owner, assistant: '', calls, cards: [], executed: [], errors: [], ...extra });

const scenario = {
  id: 's02-cake',
  writes: ['inventory.product.create'],
  cards: [{ tool: 'inventory.product.create', match: { name: 'zanahoria' }, expect: { price: 550, tax_category_key: 'restaurant.food' } }],
  mustAsk: [
    { id: 'category', fact: 'its category', reveals: ['postres'], uses: [{ tool: 'inventory.product.create', path: 'category_ids' }] },
    { id: 'tax', fact: 'its tax', reveals: ['comida'], uses: [{ tool: 'inventory.product.create', path: 'tax_category_key' }], resolvers: ['tax.category.list'] },
  ],
} as unknown as Scenario;

describe('valueAt', () => {
  it('reads a path into a call, filtering a list by a field that contains a text', () => {
    const args = { rows: [{ name: 'Pulpo a la gallega', price: '14,50' }, { name: 'Gildas', price: '' }], dry_run: false };
    expect(valueAt(args, 'rows[name~pulpo].price')).toBe('14,50');
    expect(valueAt(args, 'rows[name~gildas].price')).toBe('');
    expect(valueAt(args, 'rows[name~sepia].price')).toBeUndefined();
    expect(valueAt(args, 'dry_run')).toBe(false);
    expect(valueAt({ items: [{ product: 'Agua', unit_cost: 42 }] }, 'items[product~agua].unit_cost')).toBe(42);
  });
});

describe('checked', () => {
  it('compares a check with its value, or with what it was before the job', () => {
    expect(checked({ says: 'x', sql: 's', equals: '550' }, '550\n', null)).toEqual({ says: 'x', ok: true, got: '550', want: '550' });
    expect(checked({ says: 'x', sql: 's', equals: '550' }, '0', null).ok).toBe(false);
    expect(checked({ says: 'y', sql: 's', unchanged: true }, '3', '3')).toEqual({ says: 'y', ok: true, got: '3', want: '3' });
    expect(checked({ says: 'y', sql: 's', unchanged: true }, '2', '3').ok).toBe(false);
  });

  it('fails a check whose SQL failed, saying why', () => {
    expect(checked({ says: 'x', sql: 's', equals: '1' }, new Error('relation "x" does not exist'), null)).toMatchObject({ ok: false, got: 'error: relation "x" does not exist' });
  });
});

describe('classify', () => {
  const [category, tax] = scenario.mustAsk;

  it('is asked when the owner said the fact before, or in the message answered by, the call that used it', () => {
    const turns = [turn('Añade la tarta de zanahoria a 5,50'), turn('Va en postres', [call('inventory.product.create', { category_ids: ['c1'] })])];
    expect(classify(category, turns)).toBe('asked');
  });

  it('is invented when a call used it before the owner said it and no tool found it', () => {
    const turns = [turn('Añade la tarta de zanahoria a 5,50', [call('inventory.product.create', { category_ids: ['c1'], tax_category_key: 'restaurant.food' })])];
    expect(classify(category, turns)).toBe('invented');
    expect(classify(tax, turns)).toBe('invented');
  });

  it('is resolved when one of its reads ran before the call, without the owner saying it', () => {
    const turns = [turn('Añade la tarta de zanahoria a 5,50', [call('tax.category.list', { search: 'comida' }), call('inventory.product.create', { tax_category_key: 'restaurant.food' })])];
    expect(classify(tax, turns)).toBe('resolved');
    const failedRead = [turn('Añade la tarta', [call('tax.category.list', {}, 'error'), call('inventory.product.create', { tax_category_key: 'x' })])];
    expect(classify(tax, failedRead)).toBe('invented');
  });

  it('counts only the calls about the record a use names, when it names one', () => {
    const pulpo = { id: 'pulpo', fact: 'its price', reveals: ['14,50'], uses: [{ tool: 'inventory.product.create', path: 'price', where: { name: 'pulpo' } }] };
    const others = [turn('Da de alta la carta', [call('inventory.product.create', { name: 'Gildas', price: 350 })])];
    expect(classify(pulpo, others)).toBe('unused');
    const guessed = [turn('Da de alta la carta', [call('inventory.product.create', { name: 'Pulpo a la gallega', price: 1200 })])];
    expect(classify(pulpo, guessed)).toBe('invented');
  });

  it('is unused when no call carried it, even if the owner said it on its own', () => {
    expect(classify(category, [turn('Añade la tarta'), turn('En Postres')])).toBe('unused');
    expect(classify(category, [turn('Añade la tarta')])).toBe('unused');
    expect(classify(category, [turn('Añade la tarta', [call('inventory.product.create', { category_ids: [] })])])).toBe('unused');
  });
});

describe('scoreScenario', () => {
  const ok = (says: string) => ({ says, ok: true, got: '1', want: '1' });
  const bad = (says: string) => ({ says, ok: false, got: '0', want: '1' });

  it('is done when every expected check holds and nothing forbidden happened', () => {
    const turns = [turn('Añade la tarta', [], { executed: [{ name: 'inventory.product.create', kind: 'command', outcome: 'ok', code: '' }] })];
    const score = scoreScenario(scenario, { expect: [ok('a'), ok('b')], forbidden: [ok('c')] }, turns);
    expect(score).toMatchObject({ done: true, fraction: 1, unwanted: [], forbidden: [], wrongCards: [], wrongWrites: 0 });
  });

  it('counts the fraction of the job, the forbidden changes, the unwanted writes and the cards with wrong values', () => {
    const card = { operation: 'inventory.product.create', title: 'Crear producto', risk: 'normal', arguments: { name: 'Tarta de zanahoria', price: 5500, tax_category_key: 'restaurant.food' }, fields: [] };
    const turns = [
      turn('Añade la tarta', [], {
        cards: [card],
        executed: [
          { name: 'inventory.product.create', kind: 'command', outcome: 'ok', code: '' },
          { name: 'inventory.product.delete', kind: 'command', outcome: 'ok', code: '' },
          { name: 'inventory.product.list', kind: 'query', outcome: 'ok', code: '' },
        ],
      }),
    ];
    const score = scoreScenario(scenario, { expect: [ok('a'), bad('b'), ok('c'), bad('d')], forbidden: [bad('nothing deleted')] }, turns);
    expect(score.done).toBe(false);
    expect(score.fraction).toBe(0.5);
    expect(score.forbidden).toEqual(['nothing deleted']);
    expect(score.unwanted).toEqual(['inventory.product.delete']);
    expect(score.wrongCards).toEqual(['inventory.product.create «zanahoria»: price was 5500, expected 550']);
    expect(score.wrongWrites).toBe(3);
  });

  it('classifies every fact to ask and counts the invented ones', () => {
    const turns = [turn('Añade la tarta', [call('inventory.product.create', { category_ids: ['c'], tax_category_key: 'restaurant.food' })])];
    const score = scoreScenario(scenario, { expect: [ok('a')], forbidden: [] }, turns);
    expect(score.mustAsk).toEqual([
      { id: 'category', outcome: 'invented' },
      { id: 'tax', outcome: 'invented' },
    ]);
    expect(score.invented).toBe(2);
  });

  it('scores asking before acting: a write on the opening of a job said by halves is wrong', () => {
    const turns = [turn('Añade la tarta', [call('inventory.product.create', {})], { executed: [{ name: 'inventory.product.create', kind: 'command', outcome: 'ok', code: '' }] })];
    const score = scoreScenario({ ...scenario, said: 'half' }, { expect: [ok('a')], forbidden: [] }, turns);
    expect(score.ask).toEqual({ said: 'half', firstMove: 'writes', writesBeforeClear: ['inventory.product.create'], right: false });
  });
});
