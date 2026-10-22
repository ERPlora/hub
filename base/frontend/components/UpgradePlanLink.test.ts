// «Upgrade plan» at the foot of the side menu (BASE-G169): this hub's plan page on erplora.com (`hub-home`,
// embedded by base/spa.py), for every profile, in a new tab. It sells, so only on the web: the app surfaces
// (and the store's copy) have no such button.
import { applySurface } from '@erplora/ui/shell';
import { afterEach, describe, expect, it } from 'vitest';

import { mountBase } from '../__tests__/mount-base';
import UpgradePlanLink from './UpgradePlanLink.vue';

const PLAN_URL = 'http://localhost:8001/store/plans?business=0199a1b2-0000-7000-8000-000000000001';

function embed(block: object | null) {
  document.head.innerHTML = block
    ? `<script id="hub-home" type="application/json">${JSON.stringify(block)}</script>`
    : '';
}

afterEach(() => {
  applySurface('web');
  document.head.innerHTML = '';
});

describe('UpgradePlanLink', () => {
  it("opens this hub's plan page on erplora.com in a new tab", async () => {
    embed({ name: 'Bar', plan_url: PLAN_URL });
    const m = await mountBase(UpgradePlanLink, { locale: 'es' });
    const link = m.wrapper.get('a[data-testid="upgrade-plan"]');
    expect(link.text()).toBe('Actualizar plan');
    expect([link.attributes('href'), link.attributes('target'), link.attributes('rel')]).toEqual([
      PLAN_URL,
      '_blank',
      'noopener',
    ]);
  });

  it("on the rail keeps only its icon, as the menu's other labels, and still says where it goes", async () => {
    embed({ name: 'Bar', plan_url: PLAN_URL });
    const m = await mountBase(UpgradePlanLink, { locale: 'es' });
    const link = m.wrapper.get('a[data-testid="upgrade-plan"]');
    // polish.css hides `.nav-label` on `ion-split-pane.rail`: the text goes, the icon stays.
    expect(link.get('.nav-label').text()).toBe('Actualizar plan');
    expect([link.attributes('title'), link.attributes('aria-label')]).toEqual(['Actualizar plan', 'Actualizar plan']);
  });

  it('paints nothing without the block (never a button that does nothing)', async () => {
    embed(null);
    const m = await mountBase(UpgradePlanLink);
    expect(m.wrapper.find('[data-testid="upgrade-plan"]').exists()).toBe(false);
  });

  it('paints nothing on an app surface: it sells', async () => {
    embed({ name: 'Bar', plan_url: PLAN_URL });
    applySurface('mobile');
    const m = await mountBase(UpgradePlanLink);
    expect(m.wrapper.find('[data-testid="upgrade-plan"]').exists()).toBe(false);
  });
});
