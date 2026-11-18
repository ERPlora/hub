import { describe, expect, it } from 'vitest';

import { flush, mountTable } from '../__tests__/mount-table';
import { occupied, tableRow, zoneRow } from '../__tests__/tables';
import FloorZoneTabs from './FloorZoneTabs.vue';

const ZONES = [zoneRow({ id: 'z1', name: 'Dining room', color: 'primary' }), zoneRow({ id: 'z2', name: 'Terrace', color: 'tertiary' })];
const TABLES = [
  tableRow({ id: 't1' }),
  occupied({ id: 't4' }),
  tableRow({ id: 't9', is_active: false, in_service: false }),
  tableRow({ id: 't7', zone_id: 'z2' }),
];

async function tabs(locale: 'en' | 'es' = 'en') {
  const m = await mountTable(FloorZoneTabs, { props: { zones: ZONES, active: 'z1', tables: TABLES }, locale });
  const tab = (id: string) => m.wrapper.find(`[data-testid="table-floor-zone-tab-${id}"]`);
  const part = (id: string, name: string) => tab(id).find(`[data-part="${name}"]`);
  return { ...m, tab, part, strip: () => m.wrapper.find('[data-testid="table-floor-zones"]') };
}

describe('FloorZoneTabs', () => {
  it('names each zone with a dot of its colour and its occupied tables over those in service', async () => {
    const z = await tabs();
    expect([z.part('z1', 'zone-name').text(), z.part('z1', 'zone-count').text()]).toEqual(['Dining room', '1/2']);
    expect([z.part('z2', 'zone-name').text(), z.part('z2', 'zone-count').text()]).toEqual(['Terrace', '0/1']);
    expect((z.tab('z2').find('.zone-tab').element as HTMLElement).style.getPropertyValue('--zone-color')).toBe('var(--ion-color-tertiary)');
    expect(z.part('z1', 'zone-count').attributes('aria-hidden')).toBe('true');
    expect(z.part('z1', 'zone-count-said').text()).toBe('1 of 2 tables occupied');
    expect(z.strip().attributes('aria-label')).toBe('Zones');
  });

  it('tells the page which zone was chosen', async () => {
    const z = await tabs();
    z.strip().element.dispatchEvent(new CustomEvent('ionChange', { detail: { value: 'z2' }, bubbles: true }));
    await flush();
    expect(z.wrapper.emitted('change')).toEqual([['z2']]);
  });

  it('fades the edge with more zones behind it', async () => {
    const z = await tabs();
    const strip = z.strip().element;
    Object.defineProperty(strip, 'clientWidth', { configurable: true, value: 300 });
    Object.defineProperty(strip, 'scrollWidth', { configurable: true, value: 700 });
    strip.dispatchEvent(new Event('scroll'));
    await flush();
    expect(z.strip().classes()).toContain('table-floor__zones--more-right');
    expect(z.strip().classes()).not.toContain('table-floor__zones--more-left');
  });

  it('speaks Spanish', async () => {
    const z = await tabs('es');
    expect(z.part('z2', 'zone-count-said').text()).toBe('0 de 1 mesa ocupada');
    expect(z.strip().attributes('aria-label')).toBe('Zonas');
  });
});
