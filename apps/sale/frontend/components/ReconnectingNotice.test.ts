// The band of every screen of the sale app while the connection is missing (WORKBOOK «Estados de cada pantalla»,
// «Reconectando»): «Reconnecting…», over what is painted, which stays, from the moment the device loses its network or
// the live connection drops; nothing once the connection is back.
import { afterEach, describe, expect, it, vi } from 'vitest';

import { mountSale } from '../__tests__/mount-sale';
import ReconnectingNotice from './ReconnectingNotice.vue';

async function setup(status: string, locale: 'en' | 'es' = 'en') {
  return mountSale(ReconnectingNotice, { props: { status, testid: 'screen' }, locale });
}

/** The device's network link as the browser tells it, and the event it fires when it changes. */
function network(up: boolean): void {
  vi.spyOn(window.navigator, 'onLine', 'get').mockReturnValue(up);
  window.dispatchEvent(new Event(up ? 'online' : 'offline'));
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('ReconnectingNotice', () => {
  it('«Reconnecting…» while the live connection recovers, in the reader’s language', async () => {
    const en = await setup('reconnecting');
    expect(en.find('screen-reconnecting').text()).toBe('Reconnecting…');
    const es = await setup('reconnecting', 'es');
    expect(es.find('screen-reconnecting').text()).toBe('Reconectando…');
  });

  it('a warning that stays on screen, never a failure', async () => {
    const m = await setup('reconnecting');
    expect(m.find('screen-reconnecting').attributes('data-tone')).toBe('warning');
  });

  it('says nothing while the connection is live, loading or failed for another reason', async () => {
    for (const status of ['live', 'loading', 'error']) {
      const m = await setup(status);
      expect(m.find('screen-reconnecting').exists()).toBe(false);
    }
  });

  it('the device without a network: «Reconnecting…» at once, before the live connection notices, until it is back', async () => {
    const m = await setup('live');
    network(false);
    await m.wrapper.vm.$nextTick();
    expect(m.find('screen-reconnecting').text()).toBe('Reconnecting…');
    network(true);
    await m.wrapper.vm.$nextTick();
    expect(m.find('screen-reconnecting').exists()).toBe(false);
  });

  it('opened without a network, it says so from the start', async () => {
    vi.spyOn(window.navigator, 'onLine', 'get').mockReturnValue(false);
    const m = await setup('loading');
    expect(m.find('screen-reconnecting').text()).toBe('Reconnecting…');
  });
});
