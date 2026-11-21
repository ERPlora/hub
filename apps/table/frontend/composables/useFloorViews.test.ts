import { describe, expect, it } from 'vitest';
import { defineComponent, h, nextTick, ref, shallowRef } from 'vue';

import { mountTable } from '../__tests__/mount-table';
import { business, NOW, occupied, SETTINGS, tableRow } from '../__tests__/tables';
import type { TableOut } from '../operations';
import { useFloorViews } from './useFloorViews';

async function setup() {
  const tables = shallowRef<TableOut[]>([occupied({ id: 't2', number: '2' }), tableRow({ id: 't1', number: '1' })]);
  const now = ref(NOW);
  const pick = shallowRef<((table: TableOut) => boolean) | null>(null);
  let views!: ReturnType<typeof useFloorViews>;
  const host = defineComponent({
    setup() {
      views = useFloorViews(
        () => tables.value,
        () => ({ now: now.value, settings: SETTINGS, timeZone: 'Europe/Madrid', pick: pick.value }),
      );
      return () => h('div');
    },
  });
  const m = await mountTable(host);
  return { ...m, tables, now, pick, views: () => views.value };
}

describe('useFloorViews', () => {
  it('paints each table in the app’s language, in the order it is given, and follows a change of language', async () => {
    const s = await setup();
    expect(s.views().map((view) => [view.id, view.short, view.statusLabel])).toEqual([
      ['t2', '0:35', 'Occupied'],
      ['t1', 'Available', 'Available'],
    ]);
    await s.setLocale('es');
    expect(s.views().map((view) => view.statusLabel)).toEqual(['Ocupada', 'Disponible']);
  });

  it('follows the clock, the rows and the destination being picked', async () => {
    const s = await setup();
    s.now.value = new Date(NOW.getTime() + 25 * 60_000);
    s.pick.value = (table) => table.status === 'available';
    await nextTick();
    expect(s.views().map((view) => [view.short, view.pickable])).toEqual([
      ['1:00', false],
      ['Available', true],
    ]);
    s.tables.value = [tableRow({ id: 't9' })];
    await nextTick();
    expect(s.views().map((view) => view.id)).toEqual(['t9']);
  });

  it('writes the bill of an occupied table in the business currency once the business answers', async () => {
    const s = await setup();
    await s.live();
    expect(s.views().map((view) => view.amount)).toEqual([undefined, undefined]);
    await s.result('base.business.get', business());
    expect(s.views().map((view) => view.amount)).toEqual(['€42.50', undefined]);
    s.tables.value = [occupied({ id: 't2', number: '2', amount: 5600 })];
    await nextTick();
    expect(s.views()[0].amount).toBe('€56.00');
  });
});
