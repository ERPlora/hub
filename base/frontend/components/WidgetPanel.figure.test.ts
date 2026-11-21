import { StatCard } from '@erplora/ui/components';
import { describe, expect, it, vi } from 'vitest';

import type { WidgetDef } from '../operations/home';
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

async function panel(fields: Partial<WidgetDef> = {}, props: { variant?: 'live' | 'soft' } = {}, locale: 'en' | 'es' = 'en') {
  return mountBase(WidgetPanel, { props: { widget: widget(fields), ...props }, locale });
}

const STATS = { total: 5, open: 3, done: 2, lines: 7 };

describe('WidgetPanel as a figure card', () => {
  it("is the library's figure card with the panel's title, icon and figure, in the colour its app declares", async () => {
    const m = await panel({ options: { format: 'number', tone: 2 } });
    const call = await m.live();
    await m.result(call, 'demo.item.stats', STATS);
    const card = m.wrapper.getComponent(StatCard);
    expect(card.props()).toMatchObject({ label: 'Open items', icon: 'ion:flask-outline', value: '3', tone: 2, variant: 'soft' });
    expect(card.attributes()).toMatchObject({ 'data-testid': 'widget', 'data-key': 'demo.open_items', 'data-tone': '2' });
    expect(card.classes()).toContain('widget--sm');
    expect(m.wrapper.find('.widget').exists()).toBe(false);
  });

  it('paints the gradient of its colour in the main row of the Home', async () => {
    const m = await panel({ options: { tone: 1 } }, { variant: 'live' });
    const call = await m.live();
    await m.result(call, 'demo.item.stats', STATS);
    expect(m.wrapper.get('.ep-stat-card').classes()).toContain('ep-stat-card--live');
  });

  it('says what a stat counts under its title', async () => {
    const m = await panel({ kind: 'stat', options: { label: 'Waiting' } });
    const call = await m.live();
    await m.result(call, 'demo.item.stats', STATS);
    expect(m.wrapper.getComponent(StatCard).props()).toMatchObject({ value: '3', note: 'Waiting' });
  });

  it('draws a sparkline under its last value', async () => {
    const m = await panel({ kind: 'sparkline', map: { series: 'n' } });
    const call = await m.live();
    await m.result(call, 'demo.item.stats', [{ n: 1 }, { n: 3 }]);
    expect(m.wrapper.getComponent(StatCard).props()).toMatchObject({ value: '3', sparkline: [1, 3] });
    expect(m.wrapper.find('.ep-stat-card__spark polyline').exists()).toBe(true);
  });

  it('is loading until its data comes, and says «No data» when its value is missing', async () => {
    const m = await panel({ map: { value: 'missing' } }, {}, 'es');
    expect(m.wrapper.get('.ep-stat-card').attributes('data-state')).toBe('loading');
    const call = await m.live();
    await m.result(call, 'demo.item.stats', STATS);
    expect(m.wrapper.get('.ep-stat-card').attributes('data-state')).toBe('empty');
    expect(m.wrapper.get('.ep-stat-card__empty').text()).toBe('Sin datos');
  });

  it('a failed read says so with «Retry», never the figure it had, and Retry follows it again', async () => {
    const m = await panel();
    const call = await m.live();
    await m.result(call, 'demo.item.stats', STATS);
    call.push(errorFrame(subId(m.client, 'demo.item.stats'), 'internal'));
    await flush();
    expect(m.wrapper.get('.ep-stat-card').attributes('data-state')).toBe('error');
    expect(m.wrapper.find('.ep-stat-card__value').text()).not.toContain('3');
    const reconnect = vi.spyOn(m.client.stream, 'reconnect');
    await m.wrapper.get('.ep-stat-card__retry').trigger('click');
    expect(reconnect).toHaveBeenCalledTimes(1);
  });

  it('a panel asked once asks again on «Retry»', async () => {
    let answers = 0;
    const m = await mountBase(WidgetPanel, {
      props: { widget: widget({ live: false }) },
      onApi: () => (answers++ === 0 ? new Response('boom', { status: 500 }) : Response.json(STATS)),
    });
    await flush();
    await flush();
    expect(m.wrapper.get('.ep-stat-card').attributes('data-state')).toBe('error');
    await m.wrapper.get('.ep-stat-card__retry').trigger('click');
    await flush();
    await flush();
    expect(m.net.api).toHaveLength(2);
    expect(m.wrapper.get('.ep-stat-card__value').text()).toBe('3');
  });

  it('keeps a stat coloured by its severity on its own panel', async () => {
    const m = await panel({ kind: 'stat', map: { value: 'open', severity: 'tone' } });
    const call = await m.live();
    await m.result(call, 'demo.item.stats', { ...STATS, tone: 'warning' });
    expect(m.wrapper.findComponent(StatCard).exists()).toBe(false);
    expect(m.wrapper.get('.widget-stat').attributes('data-severity')).toBe('warning');
  });
});
