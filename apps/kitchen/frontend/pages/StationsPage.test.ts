// Kitchen → Stations (WORKBOOK «Pantallas · Estaciones»; KITCHEN-F01 to F04): the stations — Station (with
// its colour), Destination, Printer, In progress and Active —, «Search station…», «Add station», Edit (also
// a tap on the row) and Delete (asks first; a refusal shows in the dialog). Under it, the routing: what goes
// to each station, «Route» and «Remove». The actions only for whoever runs the stations.
import { ConfirmDialog, DataTable } from '@erplora/ui/components';
import { describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

import { route, station } from '../__tests__/kitchen';
import { EMPLOYEE, type MountOptions, mountKitchen, page, settle } from '../__tests__/mount-kitchen';
import RouteFormModal from '../components/RouteFormModal.vue';
import StationFormModal from '../components/StationFormModal.vue';
import type { RouteOut, StationOut } from '../operations';
import StationsPage from './StationsPage.vue';
import { listFillProblems } from '../../../../frontend/testing/list-fill';

/** A prop of a mounted component, whatever its type (a generic component's props read as `never`). */
const prop = (wrapper: { props: () => unknown }, name: string): unknown => (wrapper.props() as Record<string, unknown>)[name];

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const GRILL = station('st-grill', { name: 'Grill', in_progress: 3, routes: 1 });
const BAR = station('st-bar', { name: 'Bar', destination: 'printer', printer_usage: 'bar', printer_name: 'Bar printer', is_active: false });
const BURGER = route('p1');

async function setup(options: MountOptions = {}) {
  const m = await mountKitchen(StationsPage, { path: '/kitchen/stations', ...options });
  await m.live();
  const tables = () => m.wrapper.findAllComponents(DataTable as unknown as Component);
  const stations = () => tables().find((t) => prop(t, 'testid') === 'kitchen-stations')!;
  const routing = () => tables().find((t) => prop(t, 'testid') === 'kitchen-routing')!;
  const show = async (rows: StationOut[], routes: RouteOut[] = []) => {
    await m.result('kitchen.station.list', page(rows), { sort: 'sort_order' });
    await m.result('kitchen.station.list', page(rows), { is_active: true });
    await m.result('kitchen.routing.list', page(routes));
  };
  const act = async (table: ReturnType<typeof stations>, actionId: string, row: unknown) => {
    table.vm.$emit('action', { actionId, row });
    await settle();
  };
  return { ...m, stations, routing, show, act };
}

describe('StationsPage', () => {
  it('lists the stations with the old columns and the routing under them', async () => {
    const s = await setup();
    await s.show([GRILL, BAR], [BURGER]);
    expect((prop(s.stations(), 'columns') as Array<{ label: string }>).map((c) => c.label)).toEqual([
      'Station',
      'Destination',
      'Printer',
      'In progress',
      'Active',
    ]);
    const text = s.wrapper.text();
    for (const words of ['Grill', 'Screen and paper', 'Kitchen', 'Bar printer', 'Paper only', 'Yes', 'No', 'Burger']) expect(text, words).toContain(words);
    expect(prop(s.stations(), 'searchPlaceholder')).toBe('Search station…');
    expect(s.find('kitchen-routing-title').text()).toBe('Product/category routing → station');
  });

  it('adds, edits and routes from the stations', async () => {
    const s = await setup();
    await s.show([GRILL]);
    s.stations().vm.$emit('primaryAction');
    await settle();
    expect(s.wrapper.findComponent(StationFormModal).props()).toMatchObject({ open: true, station: null });
    s.stations().vm.$emit('rowClick', GRILL);
    await settle();
    expect(prop(s.wrapper.findComponent(StationFormModal), 'station')).toEqual(GRILL);
    await s.act(s.stations(), 'route', GRILL);
    expect(s.wrapper.findComponent(RouteFormModal).props()).toMatchObject({ open: true, station: 'st-grill' });
  });

  it('deletes a station after asking, and shows a refusal in the dialog', async () => {
    const s = await setup();
    await s.show([GRILL]);
    await s.act(s.stations(), 'delete', GRILL);
    const dialog = s.wrapper.findAllComponents(ConfirmDialog).find((d) => prop(d, 'testid') === 'kitchen-stations-delete')!;
    expect(prop(dialog, 'title')).toBe('Delete «Grill»?');
    expect(prop(dialog, 'message')).toBe(
      'The station leaves the list and stops receiving tickets. Tickets already sent keep it in their history.',
    );
    s.answer(409, { error: { code: 'kitchen.station_in_use', message: 'This station cannot be deleted.' } });
    dialog.vm.$emit('confirm');
    await settle();
    expect(s.sent().map((call) => [call.path, call.body])).toEqual([['/api/kitchen/stations/delete', { station_id: 'st-grill' }]]);
    expect(prop(dialog, 'error')).toMatchObject({ code: 'kitchen.station_in_use' });
  });

  it('removes a route', async () => {
    const s = await setup();
    await s.show([GRILL], [BURGER, route('c1', { kind: 'category', target_name: 'Drinks' })]);
    s.answer(200, BURGER);
    await s.act(s.routing(), 'remove', BURGER);
    expect(s.sent().map((call) => [call.path, call.body])).toEqual([['/api/kitchen/routing/clear', { product_id: 'p1' }]]);
  });

  it('a cook sees the stations but runs none of them', async () => {
    const s = await setup({ session: EMPLOYEE });
    await s.show([GRILL], [BURGER]);
    expect(prop(s.stations(), 'actions')).toEqual([]);
    expect(prop(s.stations(), 'primaryAction')).toBeUndefined();
    expect(prop(s.routing(), 'actions')).toEqual([]);
  });

  it('says when there is nothing yet', async () => {
    const s = await setup();
    await s.show([]);
    expect(s.find('kitchen-stations-empty').text()).toContain('No stations.');
    expect(s.find('kitchen-routing-empty').text()).toContain('Nothing routed yet');
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    await s.show([GRILL]);
    expect(prop(s.stations(), 'searchPlaceholder')).toBe('Buscar estación…');
    expect(s.wrapper.text()).toContain('Pantalla y papel');
  });
});

describe('StationsPage: the list fills the page (FIX-DATATABLE-HUB)', () => {
  it('AppPage `fill` and its DataTable `fill`, only stacks between them: from the topbar to the tabbar', async () => {
    const s = await setup();
    expect(listFillProblems(s.wrapper)).toEqual([]);
  });
});
