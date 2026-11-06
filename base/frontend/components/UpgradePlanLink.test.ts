// «Upgrade plan» at the foot of the side menu (BASE-G169): this hub's plan page on erplora.com (`hub-home`,
// embedded by base/spa.py), for every profile, in a new tab. It sells, so only on the web: the app surfaces
// (and the store's copy) have no such button.
import { applySurface } from '@erplora/ui/shell';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { flush, mountBase, tap } from '../__tests__/mount-base';
import PlanUpgradeLink from './PlanUpgradeLink.vue';
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
  vi.restoreAllMocks();
});

describe('UpgradePlanLink', () => {
  it("opens this hub's plan page on erplora.com in a new tab", async () => {
    embed({ name: 'Bar', plan_url: PLAN_URL });
    const m = await mountBase(UpgradePlanLink, { locale: 'es' });
    const link = m.wrapper.get('a[data-testid="upgrade-plan"]');
    expect(link.text()).toBe('Mejorar plan');
    expect([link.attributes('href'), link.attributes('target'), link.attributes('rel')]).toEqual([
      PLAN_URL,
      '_blank',
      'noopener',
    ]);
  });

  it('its click asks for the pass to the plan and opens it, already signed in on erplora.com', async () => {
    embed({ name: 'Bar', plan_url: PLAN_URL });
    const tab = { opener: {}, location: { href: 'about:blank' } };
    vi.spyOn(window, 'open').mockReturnValue(tab as unknown as Window);
    const url = 'http://localhost:8001/hub-pass/?pass=abc';
    const m = await mountBase(UpgradePlanLink, { onApi: () => Response.json({ url }) });

    tap(m.wrapper.get('a[data-testid="upgrade-plan"]').element);
    await flush();

    expect(JSON.parse(m.net.api[0].init.body as string)).toEqual({ next: 'plan' });
    expect(tab.location.href).toBe(url);
  });

  it("is the platform's PlanUpgradeLink to this hub's plan page, not a copy of its own", async () => {
    embed({ name: 'Bar', plan_url: PLAN_URL });
    const m = await mountBase(UpgradePlanLink);
    const piece = m.wrapper.findComponent(PlanUpgradeLink);
    expect(piece.exists()).toBe(true);
    expect(piece.props('url')).toBe(PLAN_URL);
    expect(piece.attributes('data-testid')).toBe('upgrade-plan');
  });

  it('when the pass cannot be signed, it opens the plan page as usual', async () => {
    embed({ name: 'Bar', plan_url: PLAN_URL });
    const error = vi.spyOn(console, 'error').mockImplementation(() => {});
    const tab = { opener: {}, location: { href: 'about:blank' } };
    vi.spyOn(window, 'open').mockReturnValue(tab as unknown as Window);
    const m = await mountBase(UpgradePlanLink, {
      onApi: () => Response.json({ error: { code: 'base.saas_pass_needs_account', message: 'No.' } }, { status: 403 }),
    });

    tap(m.wrapper.get('a[data-testid="upgrade-plan"]').element);
    await flush();

    expect(tab.location.href).toBe(PLAN_URL);
    expect(error).toHaveBeenCalled();
  });

  it("on the rail keeps only its icon, as the menu's other labels, and still says where it goes", async () => {
    embed({ name: 'Bar', plan_url: PLAN_URL });
    const m = await mountBase(UpgradePlanLink, { locale: 'es' });
    const link = m.wrapper.get('a[data-testid="upgrade-plan"]');
    // polish.css hides `.nav-label` on `ion-split-pane.rail`: the text goes, the icon stays.
    expect(link.get('.nav-label').text()).toBe('Mejorar plan');
    expect([link.attributes('title'), link.attributes('aria-label')]).toEqual(['Mejorar plan', 'Mejorar plan']);
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
