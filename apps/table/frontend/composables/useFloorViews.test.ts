import { createShellI18n } from '@erplora/ui/shell';
import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';
import { defineComponent, h, nextTick, ref, shallowRef } from 'vue';

import { NOW, occupied, SETTINGS, tableRow } from '../__tests__/tables';
import en from '../locale/en.json';
import es from '../locale/es.json';
import type { TableOut } from '../operations';
import { useFloorViews } from './useFloorViews';

function setup() {
  const i18n = createShellI18n({ locale: 'en', messages: { en, es } });
  const tables = shallowRef<TableOut[]>([occupied({ id: 't2', number: '2' }), tableRow({ id: 't1', number: '1' })]);
  const now = ref(NOW);
  const pick = shallowRef<((table: TableOut) => boolean) | null>(null);
  let views!: ReturnType<typeof useFloorViews>;
  mount(
    defineComponent({
      setup() {
        views = useFloorViews(
          () => tables.value,
          () => ({ now: now.value, settings: SETTINGS, timeZone: 'Europe/Madrid', pick: pick.value }),
        );
        return () => h('div');
      },
    }),
    { global: { plugins: [i18n] } },
  );
  return { i18n, tables, now, pick, views: () => views.value };
}

describe('useFloorViews', () => {
  it('paints each table in the app’s language, in the order it is given, and follows a change of language', async () => {
    const s = setup();
    expect(s.views().map((view) => [view.id, view.short, view.statusLabel])).toEqual([
      ['t2', '0:35', 'Occupied'],
      ['t1', 'Available', 'Available'],
    ]);
    s.i18n.global.locale.value = 'es';
    await nextTick();
    expect(s.views().map((view) => view.statusLabel)).toEqual(['Ocupada', 'Disponible']);
  });

  it('follows the clock, the rows and the destination being picked', async () => {
    const s = setup();
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
});
