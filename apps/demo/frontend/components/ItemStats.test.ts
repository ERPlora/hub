// The figures above the demo list (DEMO-F05): «Open», «Done» and «Lines», followed live from
// `demo.item.stats` — every demo event re-runs it on the server and the new result comes through
// the stream. Only the page decides who sees them (the query asks for `demo.manage`).
import { IonChip } from '@ionic/vue';
import { describe, expect, it } from 'vitest';

import { BYE, errorFrame, flush, mountDemo } from '../__tests__/mount-demo';
import ItemStats from './ItemStats.vue';

const STATS = { total: 5, open: 3, done: 2, lines: 7 };

async function setup(locale: 'en' | 'es' = 'en') {
  const m = await mountDemo(ItemStats, { locale });
  const call = await m.live();
  const chip = (name: 'open' | 'done' | 'lines') => m.wrapper.find(`[data-testid="demo-stats-${name}"]`);
  const show = (data: unknown, rev?: number) => m.result(call, 'demo.item.stats', data, rev);
  return { ...m, call, chip, show };
}

describe('ItemStats: the live figures of the demo', () => {
  it('follows demo.item.stats, with no parameters', async () => {
    const s = await setup();
    expect(s.client.stream.subscriptions('demo.item.stats').map((sub) => sub.params)).toEqual([{}]);
  });

  it('says it is loading until the first result, then paints open, done and lines as ion-chips', async () => {
    const s = await setup();
    expect(s.wrapper.get('[data-testid="demo-stats"]').attributes('aria-busy')).toBe('true');
    expect(s.chip('open').text()).toBe('Open …');
    await s.show(STATS);
    expect(s.wrapper.get('[data-testid="demo-stats"]').attributes('aria-busy')).toBe('false');
    const chips = s.wrapper.findAllComponents(IonChip);
    expect(chips.map((c) => [c.attributes('data-testid'), c.text(), c.attributes('data-value')])).toEqual([
      ['demo-stats-open', 'Open 3', '3'],
      ['demo-stats-done', 'Done 2', '2'],
      ['demo-stats-lines', 'Lines 7', '7'],
    ]);
    expect(chips.map((c) => c.props('color'))).toEqual(['primary', 'success', 'medium']);
  });

  it('keeps label and value in one inline element, so the space between them survives the chip’s flex layout', async () => {
    const s = await setup();
    await s.show(STATS);
    for (const name of ['open', 'done', 'lines'] as const) {
      const children = [...s.chip(name).element.children];
      expect(children.map((c) => c.tagName), name).toEqual(['SPAN']);
      expect(children[0].querySelector('strong')?.textContent, name).toBe(String(STATS[name]));
    }
  });

  it('a new result from the server (a write anywhere in this business) updates the figures in place', async () => {
    const s = await setup();
    await s.show(STATS);
    await s.show({ total: 6, open: 4, done: 2, lines: 9 }, 2);
    expect([s.chip('open').text(), s.chip('done').text(), s.chip('lines').text()]).toEqual(['Open 4', 'Done 2', 'Lines 9']);
  });

  it('paints big numbers with the language’s grouping', async () => {
    const s = await setup();
    await s.show({ total: 1500, open: 1200, done: 300, lines: 25000 });
    expect(s.chip('lines').text()).toBe('Lines 25,000');
    expect(s.chip('lines').attributes('data-value')).toBe('25000');
  });

  it('keeps the figures while the stream reconnects', async () => {
    const s = await setup();
    await s.show(STATS);
    s.call.push(BYE);
    await flush();
    expect(s.chip('open').text()).toBe('Open 3');
  });

  it('when the figures cannot be loaded says so instead of painting stale or empty numbers', async () => {
    const s = await setup();
    await s.show(STATS);
    const id = s.client.stream.subscriptions('demo.item.stats')[0].id;
    s.call.push(errorFrame(id, 'permission_denied'));
    await flush();
    expect(s.chip('open').exists()).toBe(false);
    const failure = s.wrapper.get('[data-testid="demo-stats-error"]');
    expect([failure.text(), failure.attributes('role')]).toEqual(['The figures could not be loaded', 'alert']);
  });

  it('speaks Spanish', async () => {
    const s = await setup('es');
    await s.show(STATS);
    expect([s.chip('open').text(), s.chip('done').text(), s.chip('lines').text()]).toEqual([
      'Abiertos 3',
      'Hechos 2',
      'Líneas 7',
    ]);
  });
});
