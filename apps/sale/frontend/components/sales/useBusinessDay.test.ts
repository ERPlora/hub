// `useBusinessDay()`: the day the Sales periods count from (SALE-F28): the hub's business day
// (`sale.business_day.get`, asked once, not live), read on demand; until it answers, the device's
// day. A failed read keeps the device's day and says so (`error`).
import { afterEach, describe, expect, it, vi } from 'vitest';
import { defineComponent, h } from 'vue';

import { flush, mountSale } from '../../__tests__/mount-sale';
import { useBusinessDay } from './useBusinessDay';

let captured: ReturnType<typeof useBusinessDay> | undefined;

const Host = defineComponent({
  setup() {
    captured = useBusinessDay();
    return () => h('div');
  },
});

async function setup() {
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date(2026, 9, 14, 9, 0));
  const m = await mountSale(Host);
  return { ...m, day: captured! };
}

afterEach(() => {
  vi.useRealTimers();
});

describe('useBusinessDay', () => {
  it('starts on the device’s day and asks nothing by itself', async () => {
    const s = await setup();
    expect(s.day.today.value).toBe('2026-10-14');
    expect(s.sent()).toEqual([]);
  });

  it('read() asks the hub its business day and takes it', async () => {
    const s = await setup();
    s.answer(200, { today: '2026-10-13' });
    await s.day.read();
    expect(s.sent()).toEqual([{ method: 'GET', path: '/api/sale/business_day', query: {}, body: undefined }]);
    expect(s.day.today.value).toBe('2026-10-13');
    expect(s.day.error.value).toBeNull();
  });

  it('a failed read keeps the last day and says why; the next good read clears it', async () => {
    const s = await setup();
    s.answer(503, { error: { code: 'unavailable', message: 'The hub is not answering.' } });
    await s.day.read();
    expect(s.day.today.value).toBe('2026-10-14');
    expect(s.day.error.value?.message).toBe('The hub is not answering.');
    s.answer(200, { today: '2026-10-14' });
    await s.day.read();
    await flush();
    expect(s.day.error.value).toBeNull();
  });

  it('an answer that is not a day changes nothing', async () => {
    const s = await setup();
    s.answer(200, { today: 'tomorrow' });
    await s.day.read();
    expect(s.day.today.value).toBe('2026-10-14');
  });
});
