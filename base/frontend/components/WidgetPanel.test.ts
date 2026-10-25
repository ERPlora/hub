// One panel of the Home's board (BASE-G166, BASE-G168): its title and icon, and its data — followed live when
// its operation is a live query (a write anywhere re-runs it on the server), asked once when it is not. A
// failed read says «Unavailable», never the old figure; no rows say «No data». A panel of its own component
// mounts that component of its app.
import { HubIcon } from '@erplora/ui/shell';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { WidgetDef } from '../operations';
import { business, errorFrame, flush, mountBase, POLISH, subId } from '../__tests__/mount-base';
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

  // FIX-HUB-HOME-WIDGET-OPTIONS-LAZY-TEXT: a stat says under its figure what it counts, the text its app gives in
  // `options.label` (already in the reader's language: base translates it); one without it says nothing more.
  it('says under the figure of a stat what it counts, in its severity', async () => {
    const stat = { kind: 'stat', map: { value: 'open', severity: 'tone' }, options: { format: 'number', label: 'En cola de contingencia' } } as const;
    const m = await panel(stat, 'es');
    const call = await m.live();
    await m.result(call, 'demo.item.stats', { total: 5, open: 3, done: 2, lines: 7, tone: 'warning' });
    expect(value(m.wrapper).text()).toBe('3');
    expect(m.wrapper.get('[data-testid="widget-label"]').text()).toBe('En cola de contingencia');
    expect(m.wrapper.get('.widget-stat').attributes('data-severity')).toBe('warning');

    const bare = await panel({ kind: 'stat', map: { value: 'open' } }, 'es');
    const again = await bare.live();
    await bare.result(again, 'demo.item.stats', { total: 5, open: 3, done: 2, lines: 7 });
    expect(value(bare.wrapper).text()).toBe('3');
    expect(bare.wrapper.find('[data-testid="widget-label"]').exists()).toBe(false);
  });

  // The old hub's gh:hub#1105: a kpi under its own title never repeats `options.label` as a second heading.
  it('a kpi paints only its figure under its title, never its `options.label`', async () => {
    const m = await panel({ options: { format: 'number', label: 'Records pending submission to the AEAT' } });
    const call = await m.live();
    await m.result(call, 'demo.item.stats', { total: 5, open: 3, done: 2, lines: 7 });
    expect(value(m.wrapper).text()).toBe('3');
    expect(m.wrapper.find('[data-testid="widget-label"]').exists()).toBe(false);
    expect(m.wrapper.text()).not.toContain('Records pending submission to the AEAT');
  });

  it('paints a bar-list as one bar per row, as wide as its share', async () => {
    const m = await panel({ kind: 'bar-list', map: { label: 'name', value: 'n' } });
    const call = await m.live();
    await m.result(call, 'demo.item.stats', { rows: [{ name: 'Café', n: 4 }, { name: 'Té', n: 1 }] });
    const bars = m.wrapper.findAll('[data-testid="widget-bar"]');
    expect(bars.map((bar) => bar.text())).toEqual(['Café4', 'Té1']);
    expect(bars[1].get('.widget-bar-fill').attributes('style')).toContain('width: 25%');
  });

  // BASE-F06: Cash register's «Recent discrepancies» painted a session closed without a count as «0,00 €». A row
  // without its value says «—» and has no bar (an empty track would read as a zero); a real 0 keeps both.
  it('paints a bar-list row without its value as «—» with no bar, and a real 0 as an amount on its track', async () => {
    const m = await panel({ kind: 'bar-list', map: { label: 'number', value: 'difference' }, options: { valueFormat: 'currency' } }, 'es');
    const call = await m.live();
    await m.result(call, 'base.business.get', business());
    await m.result(call, 'demo.item.stats', { rows: [{ number: 'CS-2', difference: null }, { number: 'CS-1', difference: 0 }] });
    const [uncounted, even] = m.wrapper.findAll('[data-testid="widget-bar"]');
    expect(uncounted.get('.widget-bar-text').text()).toBe('—');
    expect(uncounted.find('.widget-bar-track').exists()).toBe(false);
    expect(even.get('.widget-bar-text').text()).toBe('0,00 €');
    expect(even.get('.widget-bar-fill').attributes('style')).toContain('width: 0%');
    expect(m.wrapper.text()).not.toContain('null');
  });

  // BASE-F06: a drawer 0,40 € short painted with a bar as long as one 5,50 € over (its width was negative, which the
  // browser drops) and no sign. The bar is as long as the size of its value, red when short and green when over, and
  // the amount still says the sign; a list with no negatives keeps its bars as they were.
  it('paints a bar-list with negatives by size, the shortfall red and the surplus green, with the sign in its text', async () => {
    const m = await panel({ kind: 'bar-list', map: { label: 'number', value: 'difference' }, options: { valueFormat: 'currency' } }, 'es');
    const call = await m.live();
    await m.result(call, 'base.business.get', business());
    await m.result(call, 'demo.item.stats', { rows: [{ number: 'CS-2', difference: 550 }, { number: 'CS-1', difference: -40 }] });
    const [over, short] = m.wrapper.findAll('[data-testid="widget-bar"]');
    expect(short.get('.widget-bar-text').text()).toBe('-0,40 €');
    expect(short.get('.widget-bar-fill').attributes('style')).toContain('width: 7.3%');
    expect(short.get('.widget-bar-fill').classes()).toContain('widget-bar-fill--negative');
    expect(over.get('.widget-bar-fill').attributes('style')).toContain('width: 100%');
    expect(over.get('.widget-bar-fill').classes()).toContain('widget-bar-fill--positive');

    const plain = await panel({ kind: 'bar-list', map: { label: 'name', value: 'n' } });
    const again = await plain.live();
    await plain.result(again, 'demo.item.stats', { rows: [{ name: 'Café', n: 4 }, { name: 'Té', n: 1 }] });
    const fills = plain.wrapper.findAll('.widget-bar-fill');
    expect(fills.map((fill) => fill.classes())).toEqual([['widget-bar-fill'], ['widget-bar-fill']]);
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

  // BASE-G98: a panel's amounts are in the business's currency (`base.business.get`, the same subscription for every
  // panel of the tab), never a fixed euro; until the business is known, the amount without a symbol.
  describe("the business's currency", () => {
    const money = { map: { value: 'total' }, options: { format: 'currency' } } as const;

    it('writes the amount in the currency of a Polish business, and in euros in a Spanish one', async () => {
      const m = await panel(money, 'es');
      const call = await m.live();
      expect(m.client.stream.subscriptions('base.business.get').map((sub) => sub.params)).toEqual([{}]);
      await m.result(call, 'demo.item.stats', { total: 1250 });
      expect(value(m.wrapper).text()).toBe('12,50');
      await m.result(call, 'base.business.get', business(POLISH));
      expect(value(m.wrapper).text()).toBe('12,50\u00a0zł');
      await m.result(call, 'base.business.get', business(), 2);
      expect(value(m.wrapper).text()).toBe('12,50\u00a0€');
    });

    it('with the decimals of its currency', async () => {
      const m = await panel(money, 'en');
      const call = await m.live();
      await m.result(call, 'base.business.get', business({ country: 'JP', currency: 'JPY', currency_decimals: 0 }));
      await m.result(call, 'demo.item.stats', { total: 123400 });
      expect(value(m.wrapper).text()).toBe('¥1,234');
    });
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
      await m.result(call, 'base.business.get', business());
      await m.result(call, 'demo.item.stats', week);
      const found = m.wrapper.findAll('[data-testid="widget-chart-bar"]');
      expect(found.map((bar) => bar.text())).toEqual(['mié', 'jue', 'vie']);
      expect(found.map((bar) => bar.attributes('aria-label'))).toEqual(['mié, 21 oct: 12,50\u00a0€', 'jue, 22 oct: 0,00\u00a0€', 'vie, 23 oct: 5,00\u00a0€']);
      expect(found.map((bar) => bar.attributes('aria-pressed'))).toEqual(['false', 'false', 'true']);
      expect(readout(m.wrapper)).toEqual(['vie, 23 oct', '5,00\u00a0€']);
      expect(m.wrapper.text()).not.toContain('2026-10');
      // No day below zero: the bars keep their one colour.
      expect(m.wrapper.findAll('.widget-chart-bar').map((bar) => bar.classes())).toEqual([['widget-chart-bar'], ['widget-chart-bar'], ['widget-chart-bar']]);
    });

    it('a tapped or focused bar says its own day and amount', async () => {
      const m = await panel(chart, 'en');
      const call = await m.live();
      await m.result(call, 'base.business.get', business());
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
      await m.result(call, 'base.business.get', business());
      await m.result(call, 'demo.item.stats', week);
      await m.wrapper.findAll('[data-testid="widget-chart-bar"]')[0].trigger('click');
      await m.result(call, 'demo.item.stats', { rows: [...week.rows.slice(0, 2), { day: '2026-10-23', total: 750 }] }, 2);
      expect(readout(m.wrapper)).toEqual(['mié, 21 oct', '12,50\u00a0€']);
      await m.result(call, 'demo.item.stats', { rows: [{ day: '2026-10-24', total: 300 }] }, 3);
      expect(bars(m.wrapper).map((bar) => bar.text())).toEqual(['sáb']);
      expect(readout(m.wrapper)).toEqual(['sáb, 24 oct', '3,00\u00a0€']);
    });

    it('a day without its value says «—» and has no bar, never a bar of 0', async () => {
      const m = await panel(chart, 'es');
      const call = await m.live();
      await m.result(call, 'base.business.get', business());
      await m.result(call, 'demo.item.stats', { rows: [{ day: '2026-10-22', total: null }, { day: '2026-10-23', total: 500 }] });
      const [missing, friday] = m.wrapper.findAll('[data-testid="widget-chart-bar"]');
      expect(missing.attributes('aria-label')).toBe('jue, 22 oct: —');
      expect(missing.find('.widget-chart-bar').exists()).toBe(false);
      expect(friday.find('.widget-chart-bar').exists()).toBe(true);
      await missing.trigger('click');
      expect(readout(m.wrapper)).toEqual(['jue, 22 oct', '—']);
    });

    it('a day below zero has a bar as tall as its size, red, and its amount says the sign', async () => {
      const m = await panel(chart, 'es');
      const call = await m.live();
      await m.result(call, 'base.business.get', business());
      await m.result(call, 'demo.item.stats', { rows: [{ day: '2026-10-22', total: -200 }, { day: '2026-10-23', total: 500 }] });
      const [refunds, friday] = m.wrapper.findAll('[data-testid="widget-chart-bar"]');
      expect(refunds.attributes('aria-label')).toBe('jue, 22 oct: -2,00 €');
      expect(refunds.get('.widget-chart-bar').attributes('style')).toContain('height: 40%');
      expect(refunds.get('.widget-chart-bar').classes()).toContain('widget-chart-bar--negative');
      expect(friday.get('.widget-chart-bar').classes()).toContain('widget-chart-bar--positive');
    });
  });

  // BASE-F06, BASE-F09: Sales' «Recent activity» painted `2026-10-23T02:23:55.572622Z`. Each moment in the device's
  // time and the person's language, the instant whole in its `<time>`. The device is pinned to Madrid and its clock
  // to Friday 23 Oct 2026, 12:00 there.
  describe('a timeline of moments', () => {
    const timeline = { kind: 'timeline', map: { title: 'who', time: 'at' } } as const;
    const TODAY = '2026-10-23T02:23:55.572622Z';
    const YESTERDAY = '2026-10-22T16:10:00Z';
    const zone = process.env.TZ;
    const times = (wrapper: { findAll: (s: string) => { text: () => string; attributes: (name: string) => string | undefined }[] }) =>
      wrapper.findAll('[data-testid="widget-entry"] time').map((time) => [time.text(), time.attributes('datetime'), time.attributes('title')]);

    beforeEach(() => {
      process.env.TZ = 'Europe/Madrid';
      vi.useFakeTimers({ toFake: ['Date', 'setInterval', 'clearInterval'] });
      vi.setSystemTime(new Date('2026-10-23T10:00:00Z'));
    });

    afterEach(() => {
      vi.useRealTimers();
      if (zone === undefined) delete process.env.TZ;
      else process.env.TZ = zone;
    });

    it('says when each entry happened in local time, the instant whole in its <time>, never the raw ISO', async () => {
      const m = await panel(timeline, 'es');
      const call = await m.live();
      await m.result(call, 'demo.item.stats', [{ who: '20261023-0002', at: TODAY }, { who: '20261022-0001', at: YESTERDAY }]);
      expect(times(m.wrapper)).toEqual([
        ['4:23', TODAY, '23 oct 2026, 4:23'],
        ['Ayer 18:10', YESTERDAY, '22 oct 2026, 18:10'],
      ]);
      expect(m.wrapper.text()).not.toContain('2026-10-2');
    });

    it("says it in English for an English reader", async () => {
      const m = await panel(timeline, 'en');
      const call = await m.live();
      await m.result(call, 'demo.item.stats', [{ who: 'A', at: TODAY }, { who: 'B', at: YESTERDAY }]);
      expect(times(m.wrapper).map(([text]) => text)).toEqual(['4:23 AM', 'Yesterday 6:10 PM']);
    });

    it("a Home left open past midnight moves today's entries to yesterday", async () => {
      vi.setSystemTime(new Date('2026-10-23T21:59:30Z'));
      const m = await panel(timeline, 'es');
      const call = await m.live();
      await m.result(call, 'demo.item.stats', [{ who: 'A', at: '2026-10-23T21:00:00Z' }]);
      expect(times(m.wrapper).map(([text]) => text)).toEqual(['23:00']);
      vi.advanceTimersByTime(60_000);
      await flush();
      expect(times(m.wrapper).map(([text]) => text)).toEqual(['Ayer 23:00']);
    });

    it('keeps its minute clock only while it is mounted', async () => {
      const m = await panel(timeline, 'es');
      expect(vi.getTimerCount()).toBe(1);
      m.wrapper.unmount();
      expect(vi.getTimerCount()).toBe(0);
    });

    it('a panel that is no timeline keeps no clock', async () => {
      await panel({}, 'es');
      expect(vi.getTimerCount()).toBe(0);
    });

    it('a time that is no date is painted as it came, outside a <time>', async () => {
      const m = await panel(timeline, 'es');
      const call = await m.live();
      await m.result(call, 'demo.item.stats', [{ who: 'Ana', at: '10:00' }]);
      expect(m.wrapper.findAll('[data-testid="widget-entry"] time')).toHaveLength(0);
      expect(m.wrapper.get('[data-testid="widget-entry-time"]').text()).toBe('10:00');
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
