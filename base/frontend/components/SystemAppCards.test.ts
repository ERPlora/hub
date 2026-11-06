// The cards the apps on put in System › «Usage and plan» (hub#683; the old hub's «Your printer» of «Resources»): base
// follows `base.system.cards` live and mounts each card's component of its app, in the server's order; what a card says
// is its app's. None while the list loads or when no app puts one; a card whose component its app lacks is left out
// and the others stay; a list that cannot be read hides the cards (the old hub's rule: «the unreadable list of apps
// leaves the card hidden»), and the rest of the tab says its own.
import { afterEach, describe, expect, it, vi } from 'vitest';

import { errorFrame, flush, mountBase, subId } from '../__tests__/mount-base';
import SystemAppCards from './SystemAppCards.vue';

// A component whose chunk does not arrive (a deploy between the list and the load), as `Broken` of any app.
vi.mock('../lib/app-components', async (importOriginal) => {
  const real = await importOriginal<typeof import('../lib/app-components')>();
  return {
    appComponent: (app: string, name: string) =>
      name === 'Broken' ? () => Promise.reject(new Error('the chunk did not arrive')) : real.appComponent(app, name),
  };
});

const OP = 'base.system.cards';
const STATS = { key: 'demo.stats', app: 'demo', component: 'ItemStats' };

async function setup() {
  const m = await mountBase(SystemAppCards);
  const call = await m.live();
  return { ...m, call };
}

const cards = (m: Awaited<ReturnType<typeof setup>>) =>
  m.wrapper.findAll('[data-testid^="system-app-card-"]').map((card) => card.attributes('data-testid'));

afterEach(() => vi.restoreAllMocks());

describe('SystemAppCards', () => {
  it('follows the cards of the apps on, live', async () => {
    const m = await setup();
    expect(m.client.stream.subscriptions(OP)).toHaveLength(1);
    expect(cards(m)).toEqual([]);
  });

  it('mounts each card’s component of its app, in the server’s order', async () => {
    const m = await setup();
    await m.result(m.call, OP, { cards: [STATS, { ...STATS, key: 'demo.lines' }] });
    expect(cards(m)).toEqual(['system-app-card-demo.stats', 'system-app-card-demo.lines']);
    await vi.waitFor(() => expect(m.wrapper.findAll('[data-testid="demo-stats"]')).toHaveLength(2));
  });

  it('shows none when no app on puts one, and takes one away when its app goes off', async () => {
    const m = await setup();
    await m.result(m.call, OP, { cards: [STATS] });
    expect(cards(m)).toEqual(['system-app-card-demo.stats']);
    await m.result(m.call, OP, { cards: [] }, 2);
    expect(cards(m)).toEqual([]);
  });

  it('leaves out a card whose component its app does not have, and keeps the others', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const m = await setup();
    await m.result(m.call, OP, { cards: [{ key: 'demo.nope', app: 'demo', component: 'Nope' }, STATS] });
    expect(cards(m)).toEqual(['system-app-card-demo.stats']);
    expect(warn).toHaveBeenCalledWith(expect.stringContaining('demo.nope'));
  });

  it('leaves out a card whose component fails to load, and keeps the others', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const m = await setup();
    await m.result(m.call, OP, { cards: [{ key: 'demo.broken', app: 'demo', component: 'Broken' }, STATS] });
    await vi.waitFor(() => expect(cards(m)).toEqual(['system-app-card-demo.stats']));
    expect(warn).toHaveBeenCalledWith(expect.stringContaining('demo.broken could not load'), expect.any(Error));
  });

  it('hides the cards when their list cannot be read', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    const m = await setup();
    await m.result(m.call, OP, { cards: [STATS] });
    m.call.push(errorFrame(subId(m.client, OP), 'server_error'));
    await flush();
    expect(cards(m)).toEqual([]);
    expect(m.wrapper.text()).toBe('');
  });
});
