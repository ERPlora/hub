// The period of a tips screen: «Today» to begin with, «7 days» or «30 days», counted back from the hub's business day,
// which is read on opening and again on every pick; anything else picked leaves the period as it was.
import { describe, expect, it } from 'vitest';
import { defineComponent, h } from 'vue';

import { flush } from '../../../../base/frontend/__tests__/mount-in-shell';
import { mountTip, onTheTwentyFifth } from '../__tests__/mount-tip';
import { usePeriod } from './usePeriod';

let period: ReturnType<typeof usePeriod>;

const Host = defineComponent({
  setup() {
    period = usePeriod();
    return () => h('p', JSON.stringify(period.bounds.value));
  },
});

onTheTwentyFifth();

async function setup() {
  const m = await mountTip(Host, { answers: { '/api/sale/business_day': [200, { today: '2026-11-24' }] } });
  await flush();
  return m;
}

describe('usePeriod', () => {
  it('starts on today, the hub’s business day once it answers', async () => {
    const s = await setup();
    expect(period.period.value).toBe('today');
    expect(period.bounds.value).toEqual({ date_from: '2026-11-24', date_to: '2026-11-24' });
    expect(s.sent().filter((call) => call.path === '/api/sale/business_day')).toHaveLength(1);
  });

  it('counts 7 and 30 days back from it, asking the day again on every pick', async () => {
    const s = await setup();
    period.pick('week');
    await flush();
    expect(period.bounds.value).toEqual({ date_from: '2026-11-18', date_to: '2026-11-24' });
    period.pick('month');
    await flush();
    expect(period.bounds.value).toEqual({ date_from: '2026-10-26', date_to: '2026-11-24' });
    expect(s.sent().filter((call) => call.path === '/api/sale/business_day')).toHaveLength(3);
  });

  it('keeps the period when something else is picked', async () => {
    await setup();
    period.pick('all');
    expect(period.period.value).toBe('today');
  });
});
