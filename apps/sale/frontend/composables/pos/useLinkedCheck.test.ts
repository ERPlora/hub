// The check the till's address names (`/sale/pos?order=<id>`, Appointments' «Charge»): pending from the moment the address
// names it until the till shows it, read once the till can show it, put on the till when open, and said when it cannot
// be opened until the person leaves it. An address of another page opens nothing.
import { describe, expect, it, vi } from 'vitest';
import { shallowRef } from 'vue';

import { mountComposable, settle } from '../../__tests__/mount-sale';
import { order } from '../../components/pos/__tests__/fixtures';
import type { OrderOut } from '../../operations';
import { type LinkedCheck, useLinkedCheck } from './useLinkedCheck';

const O7 = order({ id: 'o7' });

async function setup(path: string, answer: [number, unknown] = [200, O7]) {
  const ready = shallowRef(false);
  const shown = shallowRef<string | null>(null);
  const open = vi.fn((check: OrderOut) => check);
  let linked!: LinkedCheck;
  const m = await mountComposable(
    () => {
      linked = useLinkedCheck({ ready: () => ready.value, shown: () => shown.value, open });
    },
    { path, locale: 'es' },
  );
  m.net.onApi(() => Response.json(answer[1], { status: answer[0] }));
  const reads = () => m.sent().filter((call) => call.path === '/api/sale/orders/detail').map((call) => call.query);
  return { ...m, linked, ready, shown, open, reads };
}

describe('useLinkedCheck', () => {
  it('pending from the address, read once the till can show it, and done once the till shows it', async () => {
    const s = await setup('/sale/pos?order=o7');
    expect(s.linked.pending.value).toBe(true);
    await settle();
    expect(s.router.currentRoute.value.fullPath).toBe('/sale/pos');
    expect(s.reads()).toEqual([]);
    s.ready.value = true;
    await settle();
    expect(s.reads()).toEqual([{ order_id: 'o7' }]);
    expect(s.open).toHaveBeenCalledWith(expect.objectContaining({ id: 'o7' }));
    expect(s.linked.pending.value).toBe(true);
    s.shown.value = 'o7';
    await settle();
    expect(s.linked.pending.value).toBe(false);
    expect(s.linked.error.value).toBeNull();
  });

  it('a check no longer open is said and stays said until it is left; then the till is as it was', async () => {
    const s = await setup('/sale/pos?order=o7', [200, { ...O7, status: 'voided' }]);
    s.ready.value = true;
    await settle();
    expect(s.open).not.toHaveBeenCalled();
    expect(s.linked.pending.value).toBe(true);
    expect(s.linked.error.value).toBe('Esa cuenta ya no está abierta: se cobró, se anuló o no existe.');
    s.linked.dismiss();
    expect(s.linked.pending.value).toBe(false);
    expect(s.linked.error.value).toBeNull();
  });

  it('an answer that arrives once the person left it changes nothing', async () => {
    const s = await setup('/sale/pos?order=o7');
    let answer!: (response: Response) => void;
    s.net.onApi(() => new Promise<Response>((resolve) => (answer = resolve)));
    s.ready.value = true;
    await settle();
    expect(s.reads()).toEqual([{ order_id: 'o7' }]);
    s.linked.dismiss();
    answer(Response.json(O7));
    await settle();
    expect(s.open).not.toHaveBeenCalled();
    expect(s.linked.pending.value).toBe(false);
  });

  it('another page’s «order» opens nothing', async () => {
    const s = await setup('/sale/sales?order=asc');
    s.ready.value = true;
    await settle();
    expect(s.linked.pending.value).toBe(false);
    expect(s.reads()).toEqual([]);
    expect(s.router.currentRoute.value.fullPath).toBe('/sale/sales?order=asc');
  });
});
