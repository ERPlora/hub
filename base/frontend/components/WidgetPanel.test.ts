// One panel of the Home's board (BASE-G166, BASE-G168): its title and icon, and its data — followed live when
// its operation is a live query (a write anywhere re-runs it on the server), asked once when it is not. A
// failed read says «Unavailable», never the old figure; no rows say «No data». A panel of its own component
// mounts that component of its app.
import { HubIcon } from '@erplora/ui/shell';
import { describe, expect, it, vi } from 'vitest';

import type { WidgetDef } from '../operations';
import { errorFrame, flush, mountBase, subId } from '../__tests__/mount-base';
import WidgetPanel from './WidgetPanel.vue';

function widget(fields: Partial<WidgetDef> = {}): WidgetDef {
  return {
    key: 'demo.open_items',
    app: 'demo',
    title: 'Open items',
    icon: 'ion:flask-outline',
    category: 'Demo',
    size: 'sm',
    default: true,
    kind: 'kpi',
    operation: 'demo.item.stats',
    params: {},
    map: { value: 'open' },
    options: {},
    component: null,
    refresh_on: ['demo.item.created'],
    live: true,
    ...fields,
  };
}

async function panel(fields: Partial<WidgetDef> = {}, locale: 'en' | 'es' = 'en') {
  return mountBase(WidgetPanel, { props: { widget: widget(fields) }, locale });
}

const value = (wrapper: { find: (s: string) => { exists: () => boolean; text: () => string } }) =>
  wrapper.find('[data-testid="widget-value"]');

describe('WidgetPanel', () => {
  it('heads the panel with its title and its icon', async () => {
    const m = await panel();
    expect(m.wrapper.get('[data-testid="widget-title"]').text()).toBe('Open items');
    expect(m.wrapper.getComponent(HubIcon).props('name')).toBe('ion:flask-outline');
  });

  it('follows a live operation with its params and repaints each new result, never emptied meanwhile', async () => {
    const m = await panel({ params: { status: 'open' } });
    const call = await m.live();
    expect(m.client.stream.subscriptions('demo.item.stats').map((sub) => sub.params)).toEqual([{ status: 'open' }]);
    await m.result(call, 'demo.item.stats', { total: 5, open: 3, done: 2, lines: 7 });
    expect(value(m.wrapper).text()).toBe('3');
    await m.result(call, 'demo.item.stats', { total: 6, open: 4, done: 2, lines: 7 }, 2);
    expect(value(m.wrapper).text()).toBe('4');
  });

  it('asks once for an operation that is no live query', async () => {
    const m = await mountBase(WidgetPanel, {
      props: { widget: widget({ live: false }) },
      onApi: () => Response.json({ total: 2, open: 1, done: 1, lines: 0 }),
    });
    await flush();
    await flush();
    expect(m.client.stream.subscriptions('demo.item.stats')).toEqual([]);
    expect(m.net.api.map((call) => call.url)).toEqual(['/api/demo/items/stats']);
    expect(value(m.wrapper).text()).toBe('1');
  });

  it('a failed read is «Unavailable», not the figure it had', async () => {
    const m = await panel();
    const call = await m.live();
    await m.result(call, 'demo.item.stats', { total: 5, open: 3, done: 2, lines: 7 });
    call.push(errorFrame(subId(m.client, 'demo.item.stats'), 'internal'));
    await flush();
    expect(value(m.wrapper).exists()).toBe(false);
    expect(m.wrapper.get('[data-testid="widget-error"]').text()).toBe('Unavailable');
  });

  it('without the mapped value: «No data»', async () => {
    const m = await panel({ map: { value: 'missing' } }, 'es');
    const call = await m.live();
    await m.result(call, 'demo.item.stats', { total: 5 });
    expect(m.wrapper.get('[data-testid="widget-empty"]').text()).toBe('Sin datos');
  });

  it('paints a bar-list as one bar per row, as wide as its share', async () => {
    const m = await panel({ kind: 'bar-list', map: { label: 'name', value: 'n' } });
    const call = await m.live();
    await m.result(call, 'demo.item.stats', { rows: [{ name: 'Café', n: 4 }, { name: 'Té', n: 1 }] });
    const bars = m.wrapper.findAll('[data-testid="widget-bar"]');
    expect(bars.map((bar) => bar.text())).toEqual(['Café4', 'Té1']);
    expect(bars[1].get('.widget-bar-fill').attributes('style')).toContain('width: 25%');
  });

  it('paints a timeline as one entry per row', async () => {
    const m = await panel({ kind: 'timeline', map: { title: 'who', time: 'at' } });
    const call = await m.live();
    await m.result(call, 'demo.item.stats', [{ who: 'Ana', at: '10:00' }]);
    expect(m.wrapper.get('[data-testid="widget-entry"]').text()).toContain('Ana');
  });

  it('paints a sparkline as a line over its series', async () => {
    const m = await panel({ kind: 'sparkline', map: { series: 'n' } });
    const call = await m.live();
    await m.result(call, 'demo.item.stats', [{ n: 1 }, { n: 3 }]);
    expect(m.wrapper.get('[data-testid="widget-sparkline"] polyline').attributes('points')).toBe('0,40 100,0');
  });

  // BASE-F06 (the old hub's gh:hub#2392): a chart of business days says each day in the person's language, never
  // `2026-10-23`, and the amount of the chosen bar — the last one (today) until another is tapped or focused.
  describe('a chart of days', () => {
    const chart = { kind: 'chart', map: { label: 'day', value: 'total' }, options: { format: 'currency' } } as const;
    const week = { rows: [{ day: '2026-10-21', total: 1250 }, { day: '2026-10-22', total: 0 }, { day: '2026-10-23', total: 500 }] };
    const bars = (wrapper: { findAll: (s: string) => { text: () => string }[] }) => wrapper.findAll('[data-testid="widget-chart-bar"]');
    const readout = (wrapper: { get: (s: string) => { text: () => string } }) => [
      wrapper.get('[data-testid="widget-chart-day"]').text(),
      wrapper.get('[data-testid="widget-chart-amount"]').text(),
    ];

    it("names each bar by its weekday and says the last bar's day and amount", async () => {
      const m = await panel(chart, 'es');
      const call = await m.live();
      await m.result(call, 'demo.item.stats', week);
      const found = m.wrapper.findAll('[data-testid="widget-chart-bar"]');
      expect(found.map((bar) => bar.text())).toEqual(['mié', 'jue', 'vie']);
      expect(found.map((bar) => bar.attributes('aria-label'))).toEqual(['mié, 21 oct: 12,50\u00a0€', 'jue, 22 oct: 0,00\u00a0€', 'vie, 23 oct: 5,00\u00a0€']);
      expect(found.map((bar) => bar.attributes('aria-pressed'))).toEqual(['false', 'false', 'true']);
      expect(readout(m.wrapper)).toEqual(['vie, 23 oct', '5,00\u00a0€']);
      expect(m.wrapper.text()).not.toContain('2026-10');
    });

    it('a tapped or focused bar says its own day and amount', async () => {
      const m = await panel(chart, 'en');
      const call = await m.live();
      await m.result(call, 'demo.item.stats', week);
      const found = m.wrapper.findAll('[data-testid="widget-chart-bar"]');
      await found[0].trigger('click');
      expect(readout(m.wrapper)).toEqual(['Wed, Oct 21', '€12.50']);
      expect(found.map((bar) => bar.attributes('aria-pressed'))).toEqual(['true', 'false', 'false']);
      await found[1].trigger('focus');
      expect(readout(m.wrapper)).toEqual(['Thu, Oct 22', '€0.00']);
    });

    it('keeps the chosen day when the chart repaints, and goes back to the last one when that day is gone', async () => {
      const m = await panel(chart, 'es');
      const call = await m.live();
      await m.result(call, 'demo.item.stats', week);
      await m.wrapper.findAll('[data-testid="widget-chart-bar"]')[0].trigger('click');
      await m.result(call, 'demo.item.stats', { rows: [...week.rows.slice(0, 2), { day: '2026-10-23', total: 750 }] }, 2);
      expect(readout(m.wrapper)).toEqual(['mié, 21 oct', '12,50\u00a0€']);
      await m.result(call, 'demo.item.stats', { rows: [{ day: '2026-10-24', total: 300 }] }, 3);
      expect(bars(m.wrapper).map((bar) => bar.text())).toEqual(['sáb']);
      expect(readout(m.wrapper)).toEqual(['sáb, 24 oct', '3,00\u00a0€']);
    });
  });

  it('mounts the component a panel names, from its app', async () => {
    const m = await panel({ kind: null, operation: null, component: 'ItemStats', live: false });
    await vi.waitFor(() => expect(m.wrapper.find('[data-testid="demo-stats"]').exists()).toBe(true));
  });

  it('a component its app does not have is «Unavailable»', async () => {
    const m = await panel({ kind: null, operation: null, component: 'Nope', live: false });
    await flush();
    expect(m.wrapper.get('[data-testid="widget-error"]').text()).toBe('Unavailable');
  });
});
