import { toastError, toastInfo } from '@erplora/ui/shell';
import { describe, expect, it } from 'vitest';

import { flush } from '../../__tests__/mount-sale';
import { CHECK, freshEachTest, setup } from '../../__tests__/till';
import { deferred, line, order, product } from '../../components/pos/__tests__/fixtures';
import type { OrderOut } from '../../operations';
import { CURRENT_CHECK_KEY } from './useCurrentCheck';

freshEachTest();

describe('useTill: the check', () => {
  it('resumes another check: the device remembers it and the live result brings it', async () => {
    const s = await setup();
    s.till().resume('o9');
    expect(s.till().orderId.value).toBe('o9');
    expect(localStorage.getItem(CURRENT_CHECK_KEY)).toBe('o9');
    s.till().follow(order({ id: 'o9', version: 4 }));
    expect(s.till().order.value?.id).toBe('o9');
  });
});

describe('useTill: following the check live', () => {
  async function withCheck() {
    const s = await setup({ locale: 'en' });
    s.reply(CHECK);
    await s.till().addProduct(product({ id: 'p1' }), null);
    return s;
  }

  it('takes a newer version and never goes back to an older one', async () => {
    const s = await withCheck();
    const newer: OrderOut = order({ id: 'o1', version: 3, lines: [line({ quantity: '3.000', line_total: 450 })] });
    s.till().follow(newer);
    s.till().follow(order({ id: 'o1', version: 2 }));
    expect(s.till().order.value).toEqual(newer);
  });

  it('ignores another check’s result', async () => {
    const s = await withCheck();
    s.till().follow(order({ id: 'o7', version: 9 }));
    expect(s.till().order.value?.id).toBe('o1');
  });

  it('a check closed on another device lets the screen go and says so', async () => {
    const s = await withCheck();
    s.till().follow(order({ id: 'o1', version: 5, status: 'completed' }));
    expect(s.till().orderId.value).toBeNull();
    expect(toastError).toHaveBeenCalledWith('That check was closed on another device: the screen starts a new one.');
  });

  it('a closed check arriving while this screen voids it is left to that write: no «closed on another device»', async () => {
    const s = await withCheck();
    const answer = deferred();
    s.net.onApi(() => answer.promise);
    const voiding = s.till().voidCheck();
    await flush();
    s.till().follow(order({ id: 'o1', version: 5, status: 'voided' }));
    expect(toastError).not.toHaveBeenCalled();
    answer.resolve(Response.json(order({ id: 'o1', version: 5, status: 'voided' })));
    expect(await voiding).toEqual({ ok: true });
    expect(s.till().orderId.value).toBeNull();
    expect(toastError).not.toHaveBeenCalled();
  });

  it('a check joined with another one (Tables «Merge», here or on another device) is not «closed on another device»: the till follows the one that stays (hub#459)', async () => {
    const s = await withCheck();
    s.till().follow(order({ id: 'o1', version: 5, status: 'voided', merged_into_id: 'o2', lines: [] }));
    expect(toastError).not.toHaveBeenCalled();
    expect(toastInfo).toHaveBeenCalledWith('That check was joined with another one: the screen shows the joined check.');
    expect(s.till().orderId.value).toBe('o2');
    expect(s.till().order.value).toBeNull();
    expect(localStorage.getItem(CURRENT_CHECK_KEY)).toBe('o2');
    expect(s.joined).toEqual(['o2']);
    s.till().follow(order({ id: 'o2', version: 7 }));
    expect(s.till().order.value?.id).toBe('o2');
  });

  it('a check joined while this screen writes to it: the write answers first, then the till follows the one that stays', async () => {
    const s = await withCheck();
    const answer = deferred();
    s.net.onApi(() => answer.promise);
    const renaming = s.till().rename('Terrace');
    await flush();
    s.till().follow(order({ id: 'o1', version: 5, status: 'voided', merged_into_id: 'o2', lines: [] }));
    expect(s.till().orderId.value).toBe('o1');
    answer.resolve(Response.json(order({ id: 'o1', version: 4, label: 'Terrace' })));
    await renaming;
    await flush();
    expect(s.till().orderId.value).toBe('o2');
    expect(s.till().order.value).toBeNull();
    expect(s.joined).toEqual(['o2']);
    expect(toastError).not.toHaveBeenCalled();
  });

  it('a check closed on another device while this screen writes to it: once the write answers, the screen lets it go and says so', async () => {
    const s = await withCheck();
    const answer = deferred();
    s.net.onApi(() => answer.promise);
    const renaming = s.till().rename('Terrace');
    await flush();
    s.till().follow(order({ id: 'o1', version: 5, status: 'completed', lines: [] }));
    expect(s.till().orderId.value).toBe('o1');
    answer.resolve(Response.json(order({ id: 'o1', version: 4, label: 'Terrace' })));
    await renaming;
    await flush();
    expect(s.till().orderId.value).toBeNull();
    expect(toastError).toHaveBeenCalledWith('That check was closed on another device: the screen starts a new one.');
  });

  it('a check that no longer exists lets the screen go too', async () => {
    const s = await withCheck();
    s.till().gone();
    expect(s.till().orderId.value).toBeNull();
  });
});
