// «My apps» on the Home (BASE-G165, hub#367): one tile per app this person can open (the list of the topbar's
// «My apps»), the most opened in this browser first; «Add apps» last, to Apps, once that screen exists; on a
// phone with six apps or more, four and «View all apps». Never «no apps» when the list could not be read.
import { HubIcon, type SessionMe } from '@erplora/ui/shell';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { flush, memoryStorage, mountBase, OWNER } from '../__tests__/mount-base';
import HomeMyApps from './HomeMyApps.vue';

function withApps(...ids: string[]): SessionMe {
  return {
    ...OWNER,
    apps: ids.map((id) => ({ label: id, state: id.startsWith('wait') ? 'activating' : 'on' })),
    menu: ids.map((id) => ({
      id,
      label: `App ${id}`,
      items: [{ path: `/${id}/home`, label: 'Home', icon: id === 'demo' ? 'ion:flask-outline' : 'cube-outline' }],
    })),
  };
}

const tiles = (wrapper: { findAll: (s: string) => { text: () => string }[] }) =>
  wrapper.findAll('[data-testid="home-my-app"]').map((tile) => tile.text());

beforeEach(() => vi.stubGlobal('localStorage', memoryStorage()));
afterEach(() => vi.unstubAllGlobals());

describe('HomeMyApps', () => {
  it('paints one tile per app the person can open, with its icon and its whole name on hover', async () => {
    const m = await mountBase(HomeMyApps, { session: withApps('demo', 'sale') });
    expect(m.wrapper.get('h2').text()).toBe('My apps');
    expect(tiles(m.wrapper)).toEqual(['App demo', 'App sale']);
    const first = m.wrapper.get('[data-testid="home-my-app"]');
    expect(first.attributes('title')).toBe('App demo');
    expect(first.attributes('href')).toBe('/demo/home');
    // A bare name of the menu is Ionicons (`iconName`).
    expect(m.wrapper.findAllComponents(HubIcon).map((icon) => icon.props('name'))).toEqual([
      'ion:flask-outline',
      'ion:cube-outline',
    ]);
  });

  it('opens the app on a tap and counts it, so the most opened come first in this browser', async () => {
    localStorage.setItem('hub-app-usage', JSON.stringify({ sale: 2 }));
    const m = await mountBase(HomeMyApps, { session: withApps('demo', 'sale', 'tax') });
    expect(tiles(m.wrapper)).toEqual(['App sale', 'App demo', 'App tax']);
    await m.wrapper.findAll('[data-testid="home-my-app"]')[2].trigger('click');
    await flush();
    expect(m.router.currentRoute.value.path).toBe('/tax/home');
    expect(JSON.parse(localStorage.getItem('hub-app-usage') ?? '{}')).toEqual({ sale: 2, tax: 1 });
  });

  it('an app still activating says so and opens nothing', async () => {
    const m = await mountBase(HomeMyApps, { session: withApps('demo', 'waiting') });
    const tile = m.wrapper.findAll('[data-testid="home-my-app"]')[1];
    expect(tile.text()).toContain('Activating…');
    expect(tile.attributes('href')).toBeUndefined();
  });

  it('ends with «Add apps» to Apps only once the router has that screen', async () => {
    const without = await mountBase(HomeMyApps, { session: withApps('demo') });
    expect(without.wrapper.find('[data-testid="home-my-apps-add"]').exists()).toBe(false);
    without.wrapper.unmount();
    const withScreen = await mountBase(HomeMyApps, { session: withApps('demo'), routes: ['/apps'] });
    const add = withScreen.wrapper.get('[data-testid="home-my-apps-add"]');
    expect([add.text(), add.attributes('href')]).toEqual(['Add apps', '/apps']);
  });

  it('on a phone with six apps or more: the first four and «View all apps», which shows the rest', async () => {
    vi.stubGlobal('matchMedia', () => ({ matches: true, addEventListener: () => {}, removeEventListener: () => {} }));
    const m = await mountBase(HomeMyApps, { session: withApps('a', 'b', 'c', 'd', 'e', 'f') });
    expect(tiles(m.wrapper)).toEqual(['App a', 'App b', 'App c', 'App d']);
    await m.wrapper.get('[data-testid="home-my-apps-all"]').trigger('click');
    expect(tiles(m.wrapper)).toHaveLength(6);
    expect(m.wrapper.find('[data-testid="home-my-apps-all"]').exists()).toBe(false);
  });

  it('on a phone with five apps, all of them', async () => {
    vi.stubGlobal('matchMedia', () => ({ matches: true, addEventListener: () => {}, removeEventListener: () => {} }));
    const m = await mountBase(HomeMyApps, { session: withApps('a', 'b', 'c', 'd', 'e') });
    expect(tiles(m.wrapper)).toHaveLength(5);
    expect(m.wrapper.find('[data-testid="home-my-apps-all"]').exists()).toBe(false);
  });

  it('without apps, says where they will show up', async () => {
    const m = await mountBase(HomeMyApps, { session: withApps(), locale: 'es' });
    expect(m.wrapper.get('[data-testid="home-my-apps-empty"]').text()).toBe(
      'Aquí aparecerán tus apps. Añade las que necesite tu negocio.',
    );
  });

  it('while the session loads: grey tiles and «Loading your apps…» for a screen reader', async () => {
    const m = await mountBase(HomeMyApps, { session: null, status: 'loading' });
    expect(m.wrapper.findAll('[data-testid="home-my-apps-skeleton"]').length).toBeGreaterThan(0);
    expect(m.wrapper.get('[role="status"]').text()).toBe('Loading your apps…');
    expect(m.wrapper.find('[data-testid="home-my-apps-empty"]').exists()).toBe(false);
  });

  it('a session that could not be read says so, never «no apps»', async () => {
    const m = await mountBase(HomeMyApps, { session: null, status: 'error' });
    expect(m.wrapper.get('[data-testid="home-my-apps-error"]').text()).toBe(
      'Could not load your apps. Reload the page; if it keeps failing, sign in again.',
    );
    expect(m.wrapper.find('[data-testid="home-my-apps-empty"]').exists()).toBe(false);
  });
});
