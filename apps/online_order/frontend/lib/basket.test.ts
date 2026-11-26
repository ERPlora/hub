// The basket of a table's page (ONLINE_ORDER-F04): the lines a customer adds, their total as the menu shows it, and
// what the order sends, which names everything by its id and never a price.
import { describe, expect, it } from 'vitest';

import { addLine, basketTotal, setQuantity, toSend, type BasketLine } from './basket';

const AIOLI = { id: 'o1', name: 'Aioli', price_delta: 50 };
const HAKE = { id: 'c2', name: 'Hake', price_delta: 200 };
const LENTILS = { id: 'c1', name: 'Lentils', price_delta: 0 };

function croquettes(quantity = 2): Omit<BasketLine, 'key'> {
  return { kind: 'dish', ref: 'p1', name: 'Croquettes', price: 750, picks: [AIOLI, AIOLI], quantity, notes: 'No salt' };
}

const menu: Omit<BasketLine, 'key'> = {
  kind: 'menu',
  ref: 'm1',
  name: 'Menu of the day',
  price: 1350,
  picks: [LENTILS, HAKE, HAKE],
  quantity: 1,
  notes: '',
};

describe('basket', () => {
  it('adds each line with a key of its own', () => {
    const lines = addLine(addLine([], croquettes()), menu);
    expect(lines.map((line) => line.key)).toEqual([1, 2]);
    expect(addLine(lines.slice(1), croquettes()).at(-1)!.key).toBe(3);
  });

  it('totals each line at its price plus what its picks add, times its quantity', () => {
    const lines = addLine(addLine([], croquettes(2)), menu);
    expect(basketTotal(lines)).toBe(2 * (750 + 50 + 50) + (1350 + 0 + 200 + 200));
  });

  it('changes the quantity of a line, and takes it out at zero', () => {
    const lines = addLine(addLine([], croquettes(2)), menu);
    expect(setQuantity(lines, 1, 3).map((line) => line.quantity)).toEqual([3, 1]);
    expect(setQuantity(lines, 2, 0).map((line) => line.name)).toEqual(['Croquettes']);
  });

  it('sends a dish with its options and a set menu with its dishes counted, by their ids and without a price', () => {
    const sent = toSend(addLine(addLine([], croquettes(2)), menu));
    expect(sent).toEqual([
      { product_id: 'p1', option_ids: ['o1', 'o1'], quantity: 2, notes: 'No salt' },
      {
        combo_id: 'm1',
        choices: [
          { option_id: 'c1', quantity: 1 },
          { option_id: 'c2', quantity: 2 },
        ],
        quantity: 1,
        notes: '',
      },
    ]);
    expect(JSON.stringify(sent)).not.toMatch(/price/);
  });
});
