// The Home (BASE-G127; the old hub's dashboard, PLAN-HUB round 2026-10-21): headed by the business's name (a
// greeting by the hour while it has none) and today's date; «Summary» = «My apps», «Finish setting up your
// business» and the board; «Activity» = the last sales. The tab is in the address: `/#actividad` opens it.
import { AppPage } from '@erplora/ui/shell';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { flush, mountBase } from '../__tests__/mount-base';
import HomePage from './HomePage.vue';

const STUBS = { HomeMyApps: true, SetupChecklist: true, WidgetBoard: true, HomeActivity: true };

function embed(name: string) {
  document.head.innerHTML = `<script id="hub-home" type="application/json">${JSON.stringify({ name, plan_url: 'x' })}</script>`;
}

async function home(options: { path?: string; locale?: 'en' | 'es' } = {}) {
  return mountBase(HomePage, { ...options, stubs: STUBS });
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date(2026, 9, 22, 9, 30));
});

afterEach(() => {
  vi.useRealTimers();
  document.head.innerHTML = '';
  document.body.innerHTML = '';
});

describe('HomePage', () => {
  it("is headed by the business's name and today's date in the page's language", async () => {
    embed('Bar Pepe');
    const m = await home({ locale: 'es' });
    expect(m.wrapper.getComponent(AppPage).props('title')).toBe('Inicio');
    expect(m.wrapper.get('h1').text()).toBe('Bar Pepe');
    expect(m.wrapper.get('[data-testid="home-date"]').text()).toBe('Hoy, jueves, 22 de octubre');
  });

  it('greets by the hour while the business has no name', async () => {
    embed('');
    vi.setSystemTime(new Date(2026, 9, 22, 21, 0));
    const m = await home();
    expect(m.wrapper.get('h1').text()).toBe('Good evening');
    expect(m.wrapper.get('[data-testid="home-date"]').text()).toBe('Today, Thursday, October 22');
  });

  it('«Summary»: «My apps», then the checklist, then the board', async () => {
    embed('Bar');
    const m = await home();
    const order = m.wrapper.findAll('home-my-apps-stub, setup-checklist-stub, widget-board-stub').map((el) => el.element.tagName.toLowerCase());
    expect(order).toEqual(['home-my-apps-stub', 'setup-checklist-stub', 'widget-board-stub']);
    expect(m.wrapper.find('home-activity-stub').exists()).toBe(false);
  });

  it('has the two tabs, «Summary» first, with their icons', async () => {
    const m = await home({ locale: 'es' });
    expect(m.wrapper.getComponent(AppPage).props('tabs')).toEqual([
      { id: 'summary', label: 'Resumen', icon: 'ion:speedometer-outline' },
      { id: 'activity', label: 'Actividad', icon: 'ion:time-outline' },
    ]);
  });

  it('«Activity» puts #actividad in the address, and the address opens it', async () => {
    const m = await home();
    m.wrapper.getComponent(AppPage).vm.$emit('update:tab', 'activity');
    await flush();
    expect(m.router.currentRoute.value.fullPath).toBe('/#actividad');
    expect(m.wrapper.find('home-activity-stub').exists()).toBe(true);
    expect(m.wrapper.find('home-my-apps-stub').exists()).toBe(false);
    m.wrapper.unmount();

    const linked = await home({ path: '/#actividad' });
    expect(linked.wrapper.getComponent(AppPage).props('contentLayout')).toBe('fill');
    expect(linked.wrapper.find('home-activity-stub').exists()).toBe(true);
  });

  it('back to «Summary» clears the hash', async () => {
    const m = await home({ path: '/#actividad' });
    m.wrapper.getComponent(AppPage).vm.$emit('update:tab', 'summary');
    await flush();
    expect(m.router.currentRoute.value.fullPath).toBe('/');
    expect(m.wrapper.find('home-my-apps-stub').exists()).toBe(true);
  });
});
