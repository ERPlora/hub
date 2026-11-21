// Turning an app on or off with its switch (BASE-F18, F19, F23, F24): what is asked, sent and said, and the switch
// going back to the real state when nothing changed.
import { applySurface, toastError, toastSuccess } from '@erplora/ui/shell';
import { describe, expect, it, vi } from 'vitest';

import { sessionChanged } from '../lib/access';

import { app } from '../__tests__/app-row';
import {
  appActionLabel,
  flip,
  flipNow,
  freshEachTest,
  type Mounted,
  noteOf,
  open,
  PLANS,
  pressAppAction,
  rowOf,
  STOCK,
  STORE,
  switchState,
} from '../__tests__/apps-page';
import { confirmSpy } from '../__tests__/apps-page-spies';
import { EMPLOYEE, flush, followPass, passRefused, placedUpgrade, SIGNED } from '../__tests__/mount-base';
import type { AppList } from '../operations/apps';

vi.mock('@erplora/ui/components', async (importOriginal) => (await import('../__tests__/apps-page-spies')).componentsWithConfirmSpy(importOriginal));
vi.mock('../lib/access', async (importOriginal) => (await import('../__tests__/apps-page-spies')).accessWithSessionSpy(importOriginal));

freshEachTest();

// sale came with customer; task was chosen; flow is off and needs nothing; booking (off) needs schedule (off).
const SALE = app('sale', { name: 'Sales', requires: ['customer'] });
const CUSTOMER = app('customer', { name: 'Customers', chosen: false, required_by: ['sale'] });
const TASK = app('task', { name: 'Tasks' });
const FLOW = app('flow', { name: 'Flows', state: 'off', chosen: false, path: null });
const SCHEDULE = app('schedule', { name: 'Schedules', state: 'off', chosen: false, path: null });
const BOOKING = app('booking', { name: 'Bookings', state: 'off', chosen: false, path: null, requires: ['schedule'] });
const APPS: AppList = {
  apps: [SALE, CUSTOMER, TASK, FLOW, SCHEDULE, BOOKING, STOCK],
  country_name: 'Spain',
  store_url: STORE,
  plan_url: PLANS,
  max_apps: 20,
  enabled: 2,
};
const posted = (m: Mounted) => m.net.api.map((c) => [c.url, JSON.parse(String(c.init.body ?? '{}')) as Record<string, unknown>]);
const refusal = (status: number, error: Record<string, unknown>) => () => Response.json({ error }, { status });
/** The refusal's notice: it stays on screen until it is closed or the next change. */
const refused = (m: Mounted) => m.wrapper.find('[data-testid="apps-refused"]');

describe('the switch of an app', () => {
  it('is on for an app on, off for one off, and named with the app and its state', async () => {
    const m = await open('/apps#all');
    await m.result(m.call, 'base.app.list', APPS);
    expect(switchState(m, 'sale')).toEqual({ checked: true, disabled: false, label: 'Sales: on' });
    expect(switchState(m, 'flow')).toEqual({ checked: false, disabled: false, label: 'Flows: off' });
    expect(rowOf(m, 'sale').text()).not.toContain('Turn off');
  });

  it('in Spanish', async () => {
    const m = await open('/apps#all', { locale: 'es' });
    await m.result(m.call, 'base.app.list', APPS);
    expect([switchState(m, 'sale').label, switchState(m, 'flow').label]).toEqual(['Sales: activada', 'Flows: sin activar']);
  });

  it('turned off, it asks with the app and what goes with it, turns it off and reads the menu again', async () => {
    confirmSpy.mockResolvedValue(true);
    const m = await open('/apps', {
      onApi: () => Response.json({ app: 'sale', state: 'off', chosen: false, along: [{ id: 'customer', name: 'Customers' }] }),
    });
    await m.result(m.call, 'base.app.list', APPS);
    await flip(m, 'sale', false);

    const asked = confirmSpy.mock.calls[0][0];
    expect([asked.title, asked.tone]).toEqual(['Turn off Sales?', 'danger']);
    expect(asked.message).toContain('Customers');
    expect(asked.message).toContain('Nothing is deleted');
    expect(posted(m)).toEqual([['/api/apps/disable', { app: 'sale' }]]);
    expect(vi.mocked(toastSuccess).mock.calls[0][0]).toBe('Sales is off. Also turned off: Customers.');
    expect(sessionChanged).toHaveBeenCalledTimes(1);
  });

  it('cancelled, nothing is sent and the switch is on again', async () => {
    confirmSpy.mockResolvedValue(false);
    const m = await open();
    await m.result(m.call, 'base.app.list', APPS);
    await flip(m, 'task', false);
    expect(m.net.api).toEqual([]);
    expect(sessionChanged).not.toHaveBeenCalled();
    expect(switchState(m, 'task').checked).toBe(true);
  });

  it('one another app on needs says which to turn off first, without asking or sending, and stays on', async () => {
    const m = await open();
    await m.result(m.call, 'base.app.list', APPS);
    await flip(m, 'customer', false);
    expect(confirmSpy).not.toHaveBeenCalled();
    expect(m.net.api).toEqual([]);
    expect(refused(m).text()).toContain('Nothing was changed');
    expect(refused(m).text()).toContain('Turn off Sales first.');
    expect(switchState(m, 'customer').checked).toBe(true);
  });

  it('a 409 from the server says the same, with the apps it names', async () => {
    confirmSpy.mockResolvedValue(true);
    const m = await open('/apps', {
      locale: 'es',
      onApi: refusal(409, { code: 'base.app_required', message: 'server words', required_by: ['sale'] }),
    });
    await m.result(m.call, 'base.app.list', APPS);
    await flip(m, 'task', false);
    expect(refused(m).text()).toContain('No se ha cambiado nada');
    expect(refused(m).text()).toContain('Desactiva antes Sales.');
    expect(toastError).not.toHaveBeenCalled();
    expect(switchState(m, 'task').checked).toBe(true);
  });

  it('an app that refuses to go off says its reason', async () => {
    confirmSpy.mockResolvedValue(true);
    const m = await open('/apps', {
      onApi: refusal(409, { code: 'base.app_vetoed', message: 'VeriFactu has records the AEAT has not accepted yet.', app: 'task' }),
    });
    await m.result(m.call, 'base.app.list', APPS);
    await flip(m, 'task', false);
    expect(refused(m).text()).toContain('VeriFactu has records the AEAT has not accepted yet.');
  });

  it('a refusal stays until it is closed, and the next change clears it', async () => {
    confirmSpy.mockResolvedValue(true);
    let answer = refusal(409, { code: 'base.app_vetoed', message: 'Send the pending records first.', app: 'task' });
    const m = await open('/apps', { onApi: () => answer() });
    await m.result(m.call, 'base.app.list', APPS);
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval'] });
    try {
      flipNow(m, 'task', false);
      await vi.advanceTimersByTimeAsync(60_000);
    } finally {
      vi.useRealTimers();
    }
    await flush();
    expect(refused(m).text()).toContain('Send the pending records first.');
    await refused(m).find('button.close').trigger('click');
    await flush();
    expect(refused(m).exists()).toBe(false);

    await flip(m, 'task', false);
    expect(refused(m).exists()).toBe(true);
    answer = () => Response.json({ app: 'task', state: 'off', chosen: false, along: [] });
    await flip(m, 'task', false);
    expect(refused(m).exists()).toBe(false);
  });

  it('turned on, an app that needs nothing goes on at once and reads the menu again', async () => {
    const m = await open('/apps#all', { onApi: () => Response.json({ app: 'flow', state: 'on', chosen: true, along: [] }) });
    await m.result(m.call, 'base.app.list', APPS);
    await flip(m, 'flow', true);
    expect(confirmSpy).not.toHaveBeenCalled();
    expect(posted(m)).toEqual([['/api/apps/enable', { app: 'flow' }]]);
    expect(vi.mocked(toastSuccess).mock.calls[0][0]).toBe('Flows is on.');
    expect(sessionChanged).toHaveBeenCalledTimes(1);
  });

  it('turned on, an app that needs others off asks first, naming them', async () => {
    confirmSpy.mockResolvedValue(true);
    const m = await open('/apps#all', {
      onApi: () => Response.json({ app: 'booking', state: 'on', chosen: true, along: [{ id: 'schedule', name: 'Schedules' }] }),
    });
    await m.result(m.call, 'base.app.list', APPS);
    await flip(m, 'booking', true);
    const asked = confirmSpy.mock.calls[0][0];
    expect([asked.title, asked.message]).toEqual(['Turn on Bookings?', 'Bookings needs Schedules: it turns on with it.']);
    expect(posted(m)).toEqual([['/api/apps/enable', { app: 'booking' }]]);
    expect(vi.mocked(toastSuccess).mock.calls[0][0]).toBe('Bookings is on. Also turned on: Schedules.');
  });

  it('while one change is sent its switch waits with a spinner and no other can start; a failure says so and puts it back', async () => {
    let answer: (response: Response) => void = () => undefined;
    const m = await open('/apps#all', { onApi: () => new Promise<Response>((resolve) => (answer = resolve)) });
    await m.result(m.call, 'base.app.list', APPS);
    await flip(m, 'flow', true);
    expect(switchState(m, 'flow')).toMatchObject({ checked: true, disabled: true });
    expect(rowOf(m, 'flow').find('ion-spinner').exists()).toBe(true);
    expect(switchState(m, 'task').disabled).toBe(true);
    answer(Response.json({ error: { code: 'internal_error', message: 'Boom.' } }, { status: 500 }));
    await flush();
    expect(refused(m).text()).toContain('Flows could not be changed: Boom.');
    expect(toastError).not.toHaveBeenCalled();
    expect(switchState(m, 'flow')).toMatchObject({ checked: false, disabled: false });
    expect(switchState(m, 'task').disabled).toBe(false);
  });

  it('who does not run the business has no switch', async () => {
    const m = await open('/apps#all', { session: EMPLOYEE });
    await m.result(m.call, 'base.app.list', APPS);
    expect(m.wrapper.find('ion-toggle').exists()).toBe(false);
  });
});

describe('the plan’s limit', () => {
  const LIMIT = refusal(402, { code: 'base.app_limit_reached', message: 'server words', max_apps: 20, enabled: 20 });

  it('says so, with «Upgrade plan» for whoever runs the business on the web, and the switch goes back off', async () => {
    const m = await open('/apps#all', { onApi: LIMIT });
    await m.result(m.call, 'base.app.list', { ...APPS, enabled: 20 });
    await flip(m, 'flow', true);
    const notice = m.wrapper.find('[data-testid="apps-limit"]');
    expect(notice.text()).toContain('You have reached the 20-app limit of your plan. Upgrade your plan or turn one off.');
    const upgrade = notice.find('[data-testid="apps-limit-upgrade"]');
    expect(upgrade.attributes()).toMatchObject({ href: PLANS, target: '_blank', rel: 'noopener' });
    expect(upgrade.text()).toBe('Upgrade plan');
    expect(sessionChanged).not.toHaveBeenCalled();
    expect(refused(m).exists()).toBe(false);
    expect(switchState(m, 'flow').checked).toBe(false);
  });

  /** The Apps store at the plan's limit, its notice out, with `pass` as what signing the pass answers. */
  async function atTheLimit(pass: () => Response) {
    const m = await open('/apps#all', { onApi: (call) => (call.url.includes('/saas-pass') ? pass() : LIMIT()) });
    await m.result(m.call, 'base.app.list', { ...APPS, enabled: 20 });
    await flip(m, 'flow', true);
    return m;
  }

  it('its «Upgrade plan» goes with the pass, already signed in on erplora.com', async () => {
    const m = await atTheLimit(() => Response.json({ url: SIGNED }));
    expect(await followPass(m, m.wrapper.get('[data-testid="apps-limit-upgrade"]').element)).toEqual({ next: 'plan', to: SIGNED });
  });

  it('its «Upgrade plan» is the platform’s PlanUpgradeLink to the business’s plans', async () => {
    const m = await atTheLimit(passRefused);
    expect(placedUpgrade(m.wrapper.get('[data-testid="apps-limit"]'))).toEqual({ url: PLANS, testid: 'apps-limit-upgrade', says: 'Upgrade plan' });
  });

  it('when the pass cannot be signed, its «Upgrade plan» opens the plans as usual', async () => {
    const error = vi.spyOn(console, 'error').mockImplementation(() => {});
    const m = await atTheLimit(passRefused);
    expect(await followPass(m, m.wrapper.get('[data-testid="apps-limit-upgrade"]').element)).toEqual({ next: 'plan', to: PLANS });
    error.mockRestore();
  });

  it('in Spanish, and inside the installed app without the link', async () => {
    applySurface('mobile');
    const m = await open('/apps#all', {
      locale: 'es',
      onApi: refusal(402, { code: 'base.app_limit_reached', message: 'server words', max_apps: 20, enabled: 21 }),
    });
    await m.result(m.call, 'base.app.list', { ...APPS, enabled: 21 });
    await flip(m, 'flow', true);
    const notice = m.wrapper.find('[data-testid="apps-limit"]');
    expect(notice.text()).toContain('Has llegado al límite de 20 apps de tu plan. Mejora el plan o desactiva una.');
    expect(notice.find('[data-testid="apps-limit-upgrade"]').exists()).toBe(false);
  });
});

describe('a paid app without its right', () => {
  it('cannot be switched on: «Upgrade plan» opens erplora.com’s Store in a new tab for whoever runs the business on the web', async () => {
    const clicked: string[][] = [];
    const opened = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      clicked.push([this.href, this.target, this.rel]);
    });
    const m = await open('/apps#all');
    await m.result(m.call, 'base.app.list', APPS);
    expect(switchState(m, 'stock')).toMatchObject({ checked: false, disabled: true });
    expect(await appActionLabel(m, 'stock', 'plans')).toBe('Upgrade plan: Stock');
    expect(rowOf(m, 'stock').find('[data-testid="apps-row-stock-plans"]').text()).toBe('Upgrade plan');
    await pressAppAction(m, 'stock', 'plans');
    // Clicked as its link would be, so the installed app hands it to the system browser (`openExternalLink`).
    expect(clicked).toEqual([[STORE, '_blank', 'noopener']]);
    expect(noteOf(m, 'stock').exists()).toBe(false);
    opened.mockRestore();
  });

  it('inside the installed app it sells nothing: it says where it is bought', async () => {
    applySurface('mobile');
    const m = await open('/apps#all');
    await m.result(m.call, 'base.app.list', APPS);
    expect(await appActionLabel(m, 'stock', 'plans')).toBeUndefined();
    expect(noteOf(m, 'stock').text()).toBe('Subscribed to on erplora.com, from your ERPlora account.');
  });
});
