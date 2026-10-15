// Kitchen → History, «Kitchen history» (WORKBOOK «Pantallas · Historial»; KITCHEN-F25): what happened in
// the kitchen, newest first — Action, Ticket (its number), Dish, Who, Notes and When (the business's date and
// time) —, «Search ticket or notes…» and a filter by action. Whoever may not read it is told so.
import { DataTable } from '@erplora/ui/components';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

import { entry, NOW, SETTINGS } from '../__tests__/kitchen';
import { errorFrame, flush, type MountOptions, mountKitchen, page, VIEWER } from '../__tests__/mount-kitchen';
import HistoryPage from './HistoryPage.vue';

/** A prop of a mounted component, whatever its type (a generic component's props read as `never`). */
const prop = (wrapper: { props: () => unknown }, name: string): unknown => (wrapper.props() as Record<string, unknown>)[name];

const OP = 'kitchen.log.list';

async function setup(options: MountOptions = {}) {
  const m = await mountKitchen(HistoryPage, { path: '/kitchen/history', ...options });
  await m.live();
  const table = () => m.wrapper.findComponent(DataTable as unknown as Component);
  const show = async (rows: unknown[]) => {
    await m.result('kitchen.settings.get', SETTINGS);
    await m.result(OP, page(rows));
  };
  return { ...m, table, show };
}

describe('HistoryPage', () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(NOW);
  });
  afterEach(() => vi.useRealTimers());

  it('lists what happened with the old columns, in the business’s time', async () => {
    const s = await setup();
    expect(s.find('kitchen-history-title').text()).toBe('Kitchen history');
    await s.show([
      entry('l2', { action: 'item_voided', item_name: 'Fries', notes: 'Cold', created_at: '2026-10-14T10:58:00Z' }),
      entry('l1', { action: 'item_ready', item_name: 'Burger', actor: 'marta', station_name: 'Grill' }),
    ]);
    expect((prop(s.table(), 'columns') as Array<{ label: string }>).map((c) => c.label)).toEqual(['Action', 'Ticket', 'Dish', 'Who', 'Notes', 'When']);
    const text = s.wrapper.text();
    for (const words of ['Dish voided', 'Fries', 'Cold', '10/14/26, 12:58', 'Dish ready', 'marta', 'System']) expect(text, words).toContain(words);
  });

  it('searches and filters by action on the server', async () => {
    const s = await setup();
    await s.show([]);
    s.table().vm.$emit('update:search', '0012');
    s.table().vm.$emit('filtersChange', { action: 'cancelled' });
    await flush();
    await s.reopen();
    expect(s.params(OP)).toEqual([{ search: '0012', action: 'cancelled', limit: 50, offset: 0 }]);
  });

  it('says when there is nothing yet', async () => {
    const s = await setup();
    await s.show([]);
    expect(s.find('kitchen-history-empty').text()).toContain('No recent kitchen activity.');
  });

  it('tells whoever may not read it', async () => {
    const s = await setup({ session: VIEWER });
    s.net.lastStream().push(errorFrame(s.subId(OP), 'permission_denied'));
    await flush();
    expect(s.find('kitchen-history-forbidden').exists()).toBe(true);
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    await s.show([entry('l1')]);
    expect(s.find('kitchen-history-title').text()).toBe('Historial de cocina');
    expect(s.wrapper.text()).toContain('Recibida');
  });
});
