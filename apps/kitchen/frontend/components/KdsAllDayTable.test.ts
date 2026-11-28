// «All-Day» on the kitchen display (KITCHEN-F15): each dish and how many are left to cook, in the order the server
// sends (most first); in «All» with its station («No station» without one), and with a station chosen without the
// column. Until the server answers it says it is loading; with nothing left, «Nothing left to cook.».
import { describe, expect, it } from 'vitest';

import { mountKitchen } from '../__tests__/mount-kitchen';
import type { AllDayRowOut } from '../operations/board';
import KdsAllDayTable from './KdsAllDayTable.vue';

const row = (fields: Partial<AllDayRowOut> = {}): AllDayRowOut => ({
  product_id: null,
  name: 'Burger',
  unit: 'ud',
  station_id: null,
  station_name: '',
  quantity: '3.000',
  ...fields,
});

async function setup(rows: AllDayRowOut[] | undefined, showStation = true, locale: 'en' | 'es' = 'en') {
  return mountKitchen(KdsAllDayTable, { props: { rows, showStation }, locale });
}

describe('KdsAllDayTable', () => {
  it('lists each dish with its station and how many are left, in the order the server sends', async () => {
    const s = await setup([row({ name: 'Steak', station_name: 'Grill', quantity: '5.000' }), row({ name: 'Salad', product_id: 'p2' })]);
    const table = s.find('kitchen-display-allday');
    expect(table.findAll('th').map((th) => th.text())).toEqual(['Dish', 'Station', 'Left']);
    expect(table.findAll('tbody tr').map((tr) => tr.findAll('td').map((td) => td.text()))).toEqual([
      ['Steak', 'Grill', '5'],
      ['Salad', 'No station', '3'],
    ]);
  });

  it('says what is left of a dish sold by measure with its unit', async () => {
    const rows = [row({ name: 'Prawns', unit: 'kg', quantity: '0.350' }), row({ name: 'Burger', quantity: '2.000' })];
    const cells = async (locale: 'en' | 'es') =>
      (await setup(rows, false, locale)).find('kitchen-display-allday').findAll('tbody tr').map((tr) => tr.findAll('td').map((td) => td.text()));
    expect(await cells('en')).toEqual([['Prawns', '0.35 kg'], ['Burger', '2']]);
    expect(await cells('es')).toEqual([['Prawns', '0,35 kg'], ['Burger', '2']]);
  });

  it('leaves the station out when one is chosen', async () => {
    const s = await setup([row()], false);
    expect(s.find('kitchen-display-allday').findAll('th').map((th) => th.text())).toEqual(['Dish', 'Left']);
  });

  it('says it is loading until the server answers, and «Nothing left to cook.» with nothing left', async () => {
    const loading = await setup(undefined);
    expect(loading.find('kitchen-display-allday-loading').attributes('role')).toBe('status');
    expect(loading.find('kitchen-display-allday-loading').text()).toBe('Loading the display…');
    expect(loading.find('kitchen-display-empty').exists()).toBe(false);
    const empty = await setup([]);
    expect(empty.find('kitchen-display-empty').text()).toContain('Nothing left to cook.');
    expect(empty.find('kitchen-display-allday').exists()).toBe(false);
  });

  it('speaks Spanish', async () => {
    const s = await setup([row({ quantity: '1500.000' })], true, 'es');
    expect(s.find('kitchen-display-allday').findAll('th').map((th) => th.text())).toEqual(['Plato', 'Estación', 'Faltan']);
    expect(s.find('kitchen-display-allday').findAll('td').map((td) => td.text())).toEqual(['Burger', 'Sin estación', '1.500']);
    expect((await setup([], true, 'es')).find('kitchen-display-empty').text()).toContain('No queda nada por cocinar.');
  });
});
