// @vitest-environment node
// One owner message of a scenario and what the assistant did after it, read from the streamed answers of
// `/api/assistant/turn`: the answer, every call with its arguments, every card with the fields it showed, what ran and
// the errors; and the card as the owner reads it on the screen.
import { describe, expect, it } from 'vitest';

import { cardLine, cardsOf, scenarioTurn } from './assistant-scenario-turn';

const sse = (...frames: unknown[]): string => frames.map((frame) => `data: ${JSON.stringify(frame)}\n\n`).join('');

const CARD = {
  operation: 'inventory.product.create',
  app_name: 'Inventario',
  action: 'Crear producto',
  risk: 'normal',
  confirm_word: '',
  fields: [
    { name: 'name', label: 'Nombre', kind: 'text', value: 'Tarta de zanahoria' },
    { name: 'price', label: 'Precio', kind: 'money', value: 550 },
    { name: 'category_ids', label: 'Categorías', kind: 'list', value: ['Postres'] },
    { name: 'extra', label: 'Más', kind: 'object', value: { a: 1 } },
  ],
};
const CALL = { call_id: 'c2', name: 'inventory__product__create', arguments: '{"name": "Tarta de zanahoria", "price": 550}' };

const FIRST = sse(
  { type: 'text', text: 'Busco la categoría. ' },
  { type: 'done', append: [], pending: [{ call_id: 'c1', name: 'inventory__category__list', arguments: '{"search": "postres"}' }] },
);
const SECOND = sse(
  { type: 'executed', call_id: 'c1', name: 'inventory.category.list', kind: 'query', outcome: 'ok', code: '' },
  { type: 'confirm', card: CARD, call: CALL },
  { type: 'done', append: [], pending: [CALL] },
);
const THIRD = sse(
  { type: 'executed', call_id: 'c2', name: 'inventory.product.create', kind: 'command', outcome: 'ok', code: '' },
  { type: 'text', text: 'Hecho.' },
  { type: 'error', code: 'assistant.cut' },
  { type: 'done', append: [], pending: [] },
);

describe('cardsOf', () => {
  it('reads each card with its call\'s arguments and the fields it showed', () => {
    expect(cardsOf([SECOND])).toEqual([
      {
        operation: 'inventory.product.create',
        title: 'Crear producto (Inventario)',
        risk: 'normal',
        arguments: { name: 'Tarta de zanahoria', price: 550 },
        fields: [
          { name: 'name', label: 'Nombre', kind: 'text', value: 'Tarta de zanahoria' },
          { name: 'price', label: 'Precio', kind: 'money', value: 550 },
          { name: 'category_ids', label: 'Categorías', kind: 'list', value: ['Postres'] },
          { name: 'extra', label: 'Más', kind: 'object', value: { a: 1 } },
        ],
      },
    ]);
  });
});

describe('scenarioTurn', () => {
  it('gathers everything the assistant did after one owner message', () => {
    const turn = scenarioTurn('Añade la tarta de zanahoria a 5,50', [FIRST, SECOND, THIRD]);
    expect(turn.owner).toBe('Añade la tarta de zanahoria a 5,50');
    expect(turn.assistant).toBe('Busco la categoría. Hecho.');
    expect(turn.calls.map((call) => [call.name, call.outcome])).toEqual([
      ['inventory.category.list', 'ok'],
      ['inventory.product.create', 'ok'],
    ]);
    expect(turn.cards).toHaveLength(1);
    expect(turn.executed.map((ran) => ran.name)).toEqual(['inventory.category.list', 'inventory.product.create']);
    expect(turn.errors).toEqual(['assistant.cut']);
  });
});

describe('cardLine', () => {
  it('says the card as the owner reads it: what it does and its plain values, money in euros', () => {
    const [card] = cardsOf([SECOND]);
    expect(cardLine(card, 'es')).toBe('Crear producto (Inventario) — Nombre: Tarta de zanahoria; Precio: 5,50 €; Categorías: Postres');
    expect(cardLine(card, 'en')).toContain('Precio: 5.50 €');
  });
});
