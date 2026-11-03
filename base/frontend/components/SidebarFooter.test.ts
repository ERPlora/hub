// base's piece of the side menu's foot (`createShell({ chrome: { sidebarFooter } })`, BASE-F11): «Upgrade plan», then
// right below it «Manage on erplora.com». Each decides for itself whether it shows (UpgradePlanLink.test.ts,
// ManageLink.test.ts); here, their order and that one never takes the other with it.
import { applySurface } from '@erplora/ui/shell';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { flush, mountBase } from '../__tests__/mount-base';
import { forgetAppDistribution } from '../lib/management';
import SidebarFooter from './SidebarFooter.vue';

const PLAN_URL = 'http://localhost:8001/store/plans?business=0199a1b2-0000-7000-8000-000000000001';
const MANAGE_URL = 'http://localhost:8001/dashboard/businesses/0199a1b2-0000-7000-8000-000000000001';

type TauriWindow = { __TAURI__?: { core: { invoke: (command: string, args?: unknown) => Promise<unknown> } } };

function embed(block: object) {
  document.head.innerHTML = `<script id="hub-home" type="application/json">${JSON.stringify(block)}</script>`;
}

const order = (root: Element) =>
  [...root.querySelectorAll('[data-testid="upgrade-plan"], [data-testid="menu-manage"]')].map((link) => link.getAttribute('data-testid'));

afterEach(() => {
  applySurface('web');
  delete (window as TauriWindow).__TAURI__;
  forgetAppDistribution();
  document.head.innerHTML = '';
});

describe('SidebarFooter', () => {
  it('«Upgrade plan», then right below it «Manage on erplora.com»', async () => {
    embed({ name: 'Bar', plan_url: PLAN_URL, manage_url: MANAGE_URL });
    const m = await mountBase(SidebarFooter, { locale: 'es' });
    expect(order(m.wrapper.element.parentElement!)).toEqual(['upgrade-plan', 'menu-manage']);
  });

  it('in the installed app, only «Manage on erplora.com»: «Upgrade plan» sells', async () => {
    embed({ name: 'Bar', plan_url: PLAN_URL, manage_url: MANAGE_URL });
    applySurface('desktop');
    const invoke = vi.fn(async (command: string) => (command === 'device_context' ? { id: 'd1', distribution: 'direct' } : undefined));
    (window as TauriWindow).__TAURI__ = { core: { invoke } };
    const m = await mountBase(SidebarFooter);
    await flush();
    expect(order(m.wrapper.element.parentElement!)).toEqual(['menu-manage']);
  });

  it('without the way to the panel (an employee, a PIN session), «Upgrade plan» stays alone', async () => {
    embed({ name: 'Bar', plan_url: PLAN_URL, manage_url: '' });
    const m = await mountBase(SidebarFooter);
    expect(order(m.wrapper.element.parentElement!)).toEqual(['upgrade-plan']);
  });
});
