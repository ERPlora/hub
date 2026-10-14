// The eight units of measure with their step (WORKBOOK INVENTORY-F26), for the product form's «Unit of
// measure» and the step of every quantity field. They never change, so they are read once from
// `inventory.unit.list` (not followed live); a failed read says so and can be retried.
import { describe, expect, it } from 'vitest';
import { defineComponent, h } from 'vue';

import { flush, mountInventory, ok, refusal, UNITS } from '../__tests__/mount-inventory';
import { useUnits } from './useUnits';

async function setup(answer: () => Response) {
  let api: ReturnType<typeof useUnits> | undefined;
  const Probe = defineComponent({
    setup() {
      api = useUnits();
      return () => h('div');
    },
  });
  const pending = mountInventory(Probe);
  const m = await pending;
  return { ...m, api: () => api!, answer };
}

describe('useUnits', () => {
  it('reads the units once and finds one by its code', async () => {
    const s = await setup(() => ok(UNITS));
    s.net.onApi(() => ok(UNITS));
    s.api().retry();
    await flush();
    expect(s.calls('/api/inventory/units').length).toBeGreaterThanOrEqual(1);
    expect(s.query(s.calls('/api/inventory/units')[0])).toEqual({ limit: '100' });
    expect(s.api().status.value).toBe('ready');
    expect(s.api().units.value.map((u) => u.code)).toEqual(['ud', 'kg', 'g', 't', 'l', 'ml', 'min', 'h']);
    expect(s.api().unitOf('kg')?.increment).toBe('0.001');
    expect(s.api().unitOf('zz')).toBeUndefined();
  });

  it('a failed read says so and can be retried', async () => {
    const s = await setup(() => refusal(500, 'server_error', 'Boom'));
    s.net.onApi(() => refusal(500, 'server_error', 'Boom'));
    s.api().retry();
    await flush();
    expect([s.api().status.value, s.api().error.value?.message]).toEqual(['error', 'Boom']);
    s.net.onApi(() => ok(UNITS));
    s.api().retry();
    await flush();
    expect(s.api().status.value).toBe('ready');
  });
});
