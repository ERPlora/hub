// «Upgrade plan» and erplora.com's Store have one rule wherever they are offered (BASE-F11): only the owner buys for the
// business, as on erplora.com, and only on the web (it sells, and the stores refuse an app that sells). The plan's
// address is this hub's plan page, which `base/spa.py` embeds in `hub-home`; never a button that does nothing when the
// address is not there.
import { applySurface, createShellSession, type SessionMe, SESSION_KEY } from '@erplora/ui/shell';
import { mount } from '@vue/test-utils';
import { defineComponent, h, ref } from 'vue';
import { afterEach, describe, expect, it } from 'vitest';

import { embedHubHome as embed, forgetHubHome } from '../__tests__/hub-home';
import { ADMIN, EMPLOYEE, OWNER } from '../__tests__/mount-base';
import { useMayBuy, usePlanLink } from './plan-link';

const PLAN_URL = 'http://localhost:8001/store/plans?business=0199a1b2-0000-7000-8000-000000000001';

/** Runs `use` in a component's setup with `me`'s session, as a screen does, and gives what it returned. */
function inSetup<T>(use: () => T, me: SessionMe = OWNER): T {
  let used: T | undefined;
  mount(
    defineComponent({
      setup() {
        used = use();
        return () => h('div');
      },
    }),
    { global: { provide: { [SESSION_KEY as symbol]: createShellSession(ref(me), ref('live')) } } },
  );
  return used as T;
}

afterEach(() => {
  applySurface('web');
  forgetHubHome();
});

describe('useMayBuy', () => {
  it('the owner, on the web', () => {
    expect(inSetup(useMayBuy, OWNER).value).toBe(true);
  });

  it('never an administrator nor an employee: on erplora.com only the owner buys', () => {
    expect(inSetup(useMayBuy, ADMIN).value).toBe(false);
    expect(inSetup(useMayBuy, EMPLOYEE).value).toBe(false);
  });

  it('never in the installed app, and follows the surface', () => {
    const mayBuy = inSetup(useMayBuy, OWNER);
    applySurface('mobile');
    expect(mayBuy.value).toBe(false);
    applySurface('web');
    expect(mayBuy.value).toBe(true);
  });
});

describe('usePlanLink', () => {
  it('on the web with the address embedded, offers it to the owner', () => {
    embed({ name: 'Bar', plan_url: PLAN_URL });
    const link = inSetup(usePlanLink);
    expect([link.planUrl, link.offered.value]).toEqual([PLAN_URL, true]);
  });

  it('does not offer it to an administrator', () => {
    embed({ name: 'Bar', plan_url: PLAN_URL });
    expect(inSetup(usePlanLink, ADMIN).offered.value).toBe(false);
  });

  it('does not offer it where the address does not come', () => {
    embed(null);
    expect(inSetup(usePlanLink).offered.value).toBe(false);
    embed({ name: 'Bar', plan_url: '' });
    expect(inSetup(usePlanLink).offered.value).toBe(false);
  });

  it('does not offer it in the installed app, and follows the surface', () => {
    embed({ name: 'Bar', plan_url: PLAN_URL });
    const link = inSetup(usePlanLink);
    applySurface('mobile');
    expect(link.offered.value).toBe(false);
    applySurface('web');
    expect(link.offered.value).toBe(true);
  });
});
