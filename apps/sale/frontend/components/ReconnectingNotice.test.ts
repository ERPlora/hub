// The band of every screen of the sale app while the live connection recovers (WORKBOOK «Estados de cada pantalla»,
// «Reconectando»): «Reconnecting…», over what is painted, which stays; nothing once the connection is back.
import { describe, expect, it } from 'vitest';

import { mountSale } from '../__tests__/mount-sale';
import ReconnectingNotice from './ReconnectingNotice.vue';

async function setup(status: string, locale: 'en' | 'es' = 'en') {
  return mountSale(ReconnectingNotice, { props: { status, testid: 'screen' }, locale });
}

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
});
