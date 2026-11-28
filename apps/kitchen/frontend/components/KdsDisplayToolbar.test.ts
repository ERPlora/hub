// The bar of the kitchen display (KITCHEN-F10, F15): the three views as Ionic segment tabs with their counts
// («Tickets» and «Ready»; «All-Day» without one), «Full screen» when the device offers it, named by what it does, and,
// with dishes of more than one station or one chosen, the stations («All», each by its name and colour, «No station»).
// It says what was chosen; the page decides.
import { describe, expect, it } from 'vitest';

import { click, ionValue, mountKitchen, said } from '../__tests__/mount-kitchen';
import type { StationChipOut } from '../operations/board';
import KdsDisplayToolbar from './KdsDisplayToolbar.vue';

const GRILL: StationChipOut = { id: 'st-grill', name: 'Grill', color: '#E03131' };
const NONE: StationChipOut = { id: null, name: '', color: '' };

async function setup(props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const m = await mountKitchen(KdsDisplayToolbar, {
    props: { view: 'tickets', station: '', stations: [], counts: { tickets: 2, ready: 1 }, fullscreenOffered: true, fullscreen: false, ...props },
    locale,
  });
  const change = (testid: string, value: string) => ionValue(m.find(testid).element, value);
  const words = (testid: string) => said(m.find(testid).element);
  return { ...m, change, words, emitted: () => m.wrapper.emitted() };
}

describe('KdsDisplayToolbar', () => {
  it('has the three views as tabs, «Tickets» and «Ready» with their counts', async () => {
    const s = await setup({ view: 'ready' });
    expect(s.find('kitchen-display-views').element.tagName.toLowerCase()).toBe('ion-segment');
    expect((s.find('kitchen-display-views').element as HTMLElement & { value?: string }).value).toBe('ready');
    expect([s.find('kitchen-display-count-tickets').text(), s.find('kitchen-display-count-ready').text()]).toEqual(['2', '1']);
    expect(s.words('kitchen-display-views')).toContain('All-Day');
  });

  it('says which view was chosen, and ignores what is not a view', async () => {
    const s = await setup();
    await s.change('kitchen-display-views', 'allday');
    await s.change('kitchen-display-views', 'nonsense');
    expect(s.emitted()['update:view']).toEqual([['allday']]);
  });

  it('offers «Full screen» only where the device can, named by what it does', async () => {
    const s = await setup();
    expect(s.find('kitchen-display-fullscreen').attributes('aria-label')).toBe('Full screen');
    await click(s.find('kitchen-display-fullscreen').element);
    expect(s.emitted().fullscreen).toHaveLength(1);
    expect((await setup({ fullscreen: true })).find('kitchen-display-fullscreen').attributes('aria-label')).toBe('Exit full screen');
    expect((await setup({ fullscreenOffered: false })).find('kitchen-display-fullscreen').exists()).toBe(false);
  });

  it('shows the stations with more than one, or with one chosen, and says which one was chosen', async () => {
    expect((await setup({ stations: [GRILL] })).find('kitchen-display-stations').exists()).toBe(false);
    expect((await setup({ stations: [GRILL], station: 'st-grill' })).find('kitchen-display-stations').exists()).toBe(true);
    const s = await setup({ stations: [GRILL, NONE] });
    expect(s.words('kitchen-display-stations')).toContain('All');
    expect(s.words('kitchen-display-stations')).toContain('Grill');
    expect(s.words('kitchen-display-stations')).toContain('No station');
    expect(s.find('kitchen-display-station-st-grill').find('.ep-station-dot').attributes('style')).toContain('background');
    await s.change('kitchen-display-stations', 'st-grill');
    await s.change('kitchen-display-stations', '__all');
    await s.change('kitchen-display-stations', 'none');
    expect(s.emitted()['update:station']).toEqual([['st-grill'], [''], ['none']]);
  });

  it('speaks Spanish', async () => {
    const s = await setup({ stations: [GRILL, NONE] }, 'es');
    expect(s.words('kitchen-display-views')).toContain('Comandas');
    expect(s.words('kitchen-display-views')).toContain('Listas');
    expect(s.words('kitchen-display-views')).toContain('Resumen');
    expect(s.words('kitchen-display-stations')).toContain('Todas');
    expect(s.words('kitchen-display-stations')).toContain('Sin estación');
    expect(s.find('kitchen-display-fullscreen').attributes('aria-label')).toBe('Pantalla completa');
  });
});
