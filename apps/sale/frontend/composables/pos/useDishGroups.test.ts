// flow: SALE-F42 — the groups of Modifiers of the dishes picked in a menu: read once per product, as the options sheet of
// a product sold on its own reads them (`modifier.group.for_target`); a failed read is said and read again on «Retry»;
// someone who may not read Modifiers, or a business without it, gets the dishes without options.
import { describe, expect, it } from 'vitest';

import { flush, mountComposable } from '../../__tests__/mount-sale';
import { refused } from '../../components/pos/__tests__/fixtures';
import { useDishGroups } from './useDishGroups';

const DONENESS = { id: 'doneness', name: 'Punto', kitchen_name: '', min_choices: 1, max_choices: 1, allow_repeat: false, is_required: true, options: [] };

let captured: ReturnType<typeof useDishGroups> | undefined;

async function setup(answer: (productId: string) => Response | Promise<Response>) {
  const m = await mountComposable(() => {
    captured = useDishGroups();
  });
  m.net.onApi((call) => answer(new URL(call.url, 'http://test').searchParams.get('product_id') ?? ''));
  return { ...m, dishes: captured! };
}

const reads = (s: Awaited<ReturnType<typeof setup>>) => s.sent().filter((call) => call.path === '/api/modifier/groups/for_target');

describe('useDishGroups', () => {
  it('reads the groups of each product once, loading until it answers', async () => {
    const s = await setup((id) => Response.json({ product_id: id, product_name: id, groups: id === 'p-steak' ? [DONENESS] : [] }));
    s.dishes.want(['p-steak', 'p-hake']);
    expect(s.dishes.of('p-steak')).toEqual({ state: 'loading' });
    await flush();
    expect(s.dishes.of('p-steak')).toEqual({ state: 'ready', groups: [DONENESS] });
    expect(s.dishes.of('p-hake')).toEqual({ state: 'ready', groups: [] });
    s.dishes.want(['p-steak']);
    await flush();
    expect(reads(s)).toHaveLength(2);
  });

  it('says a read failed, and reads it again on retry', async () => {
    let failing = true;
    const s = await setup((id) => (failing ? refused('internal_error', 'Internal error', 500) : Response.json({ product_id: id, product_name: id, groups: [DONENESS] })));
    s.dishes.want(['p-steak']);
    await flush();
    expect(s.dishes.of('p-steak')).toEqual({ state: 'error' });
    failing = false;
    s.dishes.retry('p-steak');
    await flush();
    expect(s.dishes.of('p-steak')).toEqual({ state: 'ready', groups: [DONENESS] });
  });

  it('someone who may not read Modifiers gets the dish without options and without an error', async () => {
    const s = await setup(() => refused('permission_denied', 'Not allowed', 403));
    s.dishes.want(['p-steak']);
    await flush();
    expect(s.dishes.of('p-steak')).toEqual({ state: 'ready', groups: [] });
  });

  it('forgets every read on reset, and an answer that arrives after it is ignored', async () => {
    const waiting: ((answer: Response) => void)[] = [];
    const s = await setup(() => new Promise<Response>((resolve) => waiting.push(resolve)));
    s.dishes.want(['p-steak']);
    await flush();
    s.dishes.reset();
    for (const resolve of waiting) resolve(Response.json({ product_id: 'p-steak', product_name: '', groups: [DONENESS] }));
    await flush();
    expect(s.dishes.of('p-steak')).toBeNull();
  });
});
