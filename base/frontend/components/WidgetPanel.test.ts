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
