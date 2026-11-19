import { describe, expect, it } from 'vitest';

import { mountComposable } from '../../__tests__/mount-sale';
import { line, order } from '../../components/pos/__tests__/fixtures';
import { useLineNote } from './useLineNote';

async function setup() {
  let save!: ReturnType<typeof useLineNote>;
  const m = await mountComposable(() => {
    save = useLineNote((write) => write('o1').then(() => ({ ok: true as const })));
  });
  m.net.onApi(() => Response.json(order({ id: 'o1' })));
  return { ...m, save: () => save };
}

describe('useLineNote', () => {
  it('writes the note and then the allergy through their operations', async () => {
    const s = await setup();
    expect(await s.save()(line(), 'No ice', ['gluten'])).toEqual({ ok: true });
    expect(s.sent().map((call) => [call.path, call.body])).toEqual([
      ['/api/sale/orders/update_line', { order_id: 'o1', line_id: 'l1', notes: 'No ice' }],
      ['/api/sale/orders/set_line_allergy', { order_id: 'o1', line_id: 'l1', allergy: ['gluten'] }],
    ]);
  });

  it('keeps a note-only save to one operation', async () => {
    const s = await setup();
    await s.save()(line(), 'No ice');
    expect(s.sent()).toHaveLength(1);
  });

  it('hands a refusal back through the attempt', async () => {
    let save!: ReturnType<typeof useLineNote>;
    const failure = { ok: false as const, message: 'No longer available' };
    await mountComposable(() => {
      save = useLineNote(() => Promise.resolve(failure));
    });
    expect(await save(line(), 'No ice', ['gluten'])).toEqual(failure);
  });
});
