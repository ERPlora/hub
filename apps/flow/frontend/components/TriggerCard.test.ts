// «When this happens…» (WORKBOOK FLOW-F10): the first card of the column says in words when the
// automation starts and opens to choose it — something happens (from the events of this business, in
// words, with «Only when…»), a schedule (every day, week or month at a time), once at a date and time,
// or only by hand —; the server's refusals show next to the field.
import { Combo } from '@erplora/ui/components';
import { describe, expect, it } from 'vitest';

import type { CatalogOut, Trigger } from '../operations';
import { click, ionValue, mountFlow } from '../__tests__/mount-flow';
import ConditionRows from './ConditionRows.vue';
import TriggerCard from './TriggerCard.vue';

const CATALOG = {
  events: [
    { name: 'sale.sale.completed', app: 'sale', app_name: 'Sales' },
    { name: 'customer.group.deleted', app: 'customer', app_name: 'Customers' },
  ],
  actions: [],
} as CatalogOut;

async function setup(modelValue: Trigger, open = true, errors: Record<string, string> = {}) {
  const m = await mountFlow(TriggerCard, { props: { modelValue, open, catalog: CATALOG, choices: [], steps: [], errors } });
  const emitted = () => (m.wrapper.emitted('update:modelValue') ?? []).map(([value]) => value);
  return { ...m, emitted };
}

describe('TriggerCard', () => {
  it('says when it starts and opens on a tap', async () => {
    const s = await setup({ kind: 'event', event: 'sale.sale.completed' }, false);
    expect(s.find('flow-trigger-open').text()).toContain('When this happens…');
    expect(s.find('flow-trigger-open').text()).toContain('When a sale is charged');
    expect(s.find('flow-trigger-panel').exists()).toBe(false);
    await click(s.find('flow-trigger-open').element);
    expect(s.wrapper.emitted('toggle')).toHaveLength(1);
  });

  it('chooses what happens among the events of this business, in words, and its «Only when…»', async () => {
    const s = await setup({ kind: 'event', event: '' });
    const combo = s.wrapper.findComponent(Combo);
    expect(combo.props('options')).toEqual([
      { id: 'customer.group.deleted', label: 'Customers: group deleted', hint: 'Customers · customer.group.deleted' },
      { id: 'sale.sale.completed', label: 'a sale is charged', hint: 'Sales · sale.sale.completed' },
    ]);
    combo.vm.$emit('update:modelValue', { id: 'sale.sale.completed', label: 'a sale is charged' });
    expect(s.emitted()).toEqual([{ kind: 'event', event: 'sale.sale.completed' }]);
    s.wrapper.findComponent(ConditionRows).vm.$emit('update:modelValue', { 'input.total': { gt: 10000 } });
    expect(s.emitted().at(-1)).toEqual({ kind: 'event', event: '', filter: { 'input.total': { gt: 10000 } } });
  });

  it('a schedule: how often, which day and what time', async () => {
    const s = await setup({ kind: 'manual' });
    await ionValue(s.find('flow-trigger-kind').element, 'schedule');
    expect(s.emitted().at(-1)).toEqual({ kind: 'schedule', every: 'day', time: '09:00' });
    await s.wrapper.setProps({ modelValue: { kind: 'schedule', every: 'day', time: '09:00' } });
    await ionValue(s.find('flow-trigger-every').element, 'week');
    expect(s.emitted().at(-1)).toEqual({ kind: 'schedule', every: 'week', weekday: 0, time: '09:00' });
    await s.wrapper.setProps({ modelValue: { kind: 'schedule', every: 'week', weekday: 0, time: '09:00' } });
    await ionValue(s.find('flow-trigger-weekday').element, 4);
    await ionValue(s.find('flow-trigger-time').element, '18:30', 'ionInput');
    expect(s.emitted().slice(-2)).toEqual([
      { kind: 'schedule', every: 'week', weekday: 4, time: '09:00' },
      { kind: 'schedule', every: 'week', weekday: 0, time: '18:30' },
    ]);
    await ionValue(s.find('flow-trigger-every').element, 'month');
    expect(s.emitted().at(-1)).toEqual({ kind: 'schedule', every: 'month', day: 1, time: '09:00' });
  });

  it('once at a date and time, sent with its offset', async () => {
    const s = await setup({ kind: 'at', at: '' });
    await ionValue(s.find('flow-trigger-at').element, '2026-11-01T09:00', 'ionInput');
    const sent = s.emitted().at(-1) as { kind: string; at: string };
    expect(sent.kind).toBe('at');
    expect(new Date(sent.at).getTime()).toBe(new Date('2026-11-01T09:00').getTime());
  });

  it('shows the server’s refusals next to their field', async () => {
    const s = await setup({ kind: 'event', event: 'spa.sauna.heated' }, true, { 'trigger.event': 'That does not happen in this business.' });
    expect(s.wrapper.findComponent(Combo).props('errorText')).toBe('That does not happen in this business.');
    const at = await setup({ kind: 'at', at: '2020-01-01T09:00:00Z' }, true, { 'trigger.at': 'That date and time has already passed.' });
    expect(at.find('flow-trigger-error').text()).toBe('That date and time has already passed.');
  });
});
