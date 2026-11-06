// The blocking strip over every screen (hub#374; BASE-G22): while a ⛔ step is pending the invoice is refused,
// so it says the consequence and names what is missing, each with its way in. Not on the Home's «Summary»,
// whose checklist says strictly more a screenful below; on «Activity» it is back. On a screen as low as a phone on its
// side (hub#838) it is one line: the consequence and one «Set up», to the first step that can be set up from there.
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { SetupItem, SetupStatus } from '../operations';
import { flush, mountBase } from '../__tests__/mount-base';
import BlockingStrip from './BlockingStrip.vue';

function legal(fields: Partial<SetupItem> = {}): SetupItem {
  return {
    key: 'invoice.business_identity',
    app: 'invoice',
    state: 'pending',
    level: 'legal',
    required: true,
    actionable: true,
    title: 'Los datos de tu negocio',
    description: 'Razón social y NIF.',
    icon: 'ion:receipt-outline',
    route: '/invoice/settings',
    order: 20,
    ...fields,
  };
}

function status(items: SetupItem[]): SetupStatus {
  const blocking = items.filter((i) => i.state === 'pending' && i.level === 'legal').length;
  return { total: items.length, pending: items.length, unavailable: 0, blocking_pending: blocking, items };
}

async function setup(path: string, data: SetupStatus, routes: string[] = ['/demo/items', '/invoice/settings']) {
  const m = await mountBase(BlockingStrip, { path, routes, locale: 'es' });
  const call = await m.live();
  await m.result(call, 'base.setup.status', data);
  const strip = () => m.wrapper.find('[data-testid="blocking-strip"]');
  return { ...m, call, strip };
}

/** A screen 500 px high or less (`LOW_HEIGHT_QUERY`, a phone on its side) when `low`; every other query, false. */
function screenLow(low: boolean) {
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches: low && query === '(max-height: 500px)',
    addEventListener: () => {},
    removeEventListener: () => {},
  }));
}

/** VeriFactu's step, as a second ⛔ step pending beside the business data. */
function verifactu(fields: Partial<SetupItem> = {}): SetupItem {
  return legal({ key: 'verifactu.config', app: 'verifactu', title: 'VeriFactu', route: '/verifactu/settings', order: 30, ...fields });
}

const ROUTES = ['/demo/items', '/invoice/settings', '/verifactu/settings'];

afterEach(() => {
  document.body.innerHTML = '';
  vi.unstubAllGlobals();
});

describe('BlockingStrip', () => {
  it('on any other screen, says the invoice is refused and names what is missing, with «Set up»', async () => {
    const s = await setup('/demo/items', status([legal()]));
    expect(s.client.stream.subscriptions('base.setup.status').map((sub) => sub.params)).toEqual([{}]);
    expect(s.strip().attributes('role')).toBe('alert');
    expect(s.strip().text()).toContain('Todavía no puedes facturar');
    // «tique», the word Invoicing's own notice under it uses (FIX-HUB-BASE-BLOCKING-STRIP-SAYS-TICKET-WHERE-INVOICING-SAYS-TIQUE).
    expect(s.strip().text()).toContain('No se podrá emitir ningún tique ni factura hasta que configures esto:');
    expect(s.strip().get('[data-testid="blocking-item"]').text()).toContain('Los datos de tu negocio');
    await s.strip().get('[data-testid="blocking-configure-invoice.business_identity"]').trigger('click');
    await flush();
    expect(s.router.currentRoute.value.path).toBe('/invoice/settings');
  });

  it("stands down on the Home's «Summary» and comes back on «Activity»", async () => {
    const summary = await setup('/', status([legal()]));
    expect(summary.strip().exists()).toBe(false);
    summary.wrapper.unmount();
    const activity = await setup('/#actividad', status([legal()]));
    expect(activity.strip().exists()).toBe(true);
  });

  it('on the very screen that sets the step up, names it with no «Set up» to that same screen', async () => {
    const s = await setup('/invoice/settings', status([legal()]));
    expect(s.strip().get('[data-testid="blocking-item"]').text()).toContain('Los datos de tu negocio');
    expect(s.strip().find('[data-testid="blocking-configure-invoice.business_identity"]').exists()).toBe(false);
    expect(s.strip().text()).not.toContain('Esto lo tiene que configurar un administrador.');
  });

  it('a step only an administrator can do says so, with no button', async () => {
    const s = await setup('/demo/items', status([legal({ actionable: false })]));
    expect(s.strip().find('[data-testid="blocking-configure-invoice.business_identity"]').exists()).toBe(false);
    expect(s.strip().text()).toContain('Esto lo tiene que configurar un administrador.');
  });

  it('without a pending ⛔ step paints nothing', async () => {
    const s = await setup('/demo/items', status([legal({ state: 'done' }), legal({ key: 'a.f', level: 'functional' })]));
    expect(s.strip().exists()).toBe(false);
  });

  it('goes away as soon as the step is done anywhere in the business', async () => {
    const s = await setup('/demo/items', status([legal()]));
    await s.result(s.call, 'base.setup.status', status([legal({ state: 'done' })]), 2);
    expect(s.strip().exists()).toBe(false);
  });

  it('on a screen of normal height, names every step pending, each with its own «Set up»', async () => {
    screenLow(false);
    const s = await setup('/demo/items', status([legal(), verifactu()]), ROUTES);
    expect(s.strip().get('.blocking-strip-text').text()).toBe('No se podrá emitir ningún tique ni factura hasta que configures esto:');
    expect(s.strip().findAll('[data-testid="blocking-item"]').map((item) => item.find('strong').text())).toEqual([
      'Los datos de tu negocio',
      'VeriFactu',
    ]);
    expect(s.strip().findAll('ion-button')).toHaveLength(2);
  });

  it('on a low screen (a phone on its side) is one line: the consequence and «Set up», with no sentence and no step named', async () => {
    screenLow(true);
    const s = await setup('/demo/items', status([legal()]));
    expect(s.strip().attributes('role')).toBe('alert');
    expect(s.strip().get('.blocking-strip-title').text()).toBe('Todavía no puedes facturar');
    expect(s.strip().find('.blocking-strip-text').exists()).toBe(false);
    expect(s.strip().find('[data-testid="blocking-item"]').exists()).toBe(false);
    expect(s.strip().text()).not.toContain('Los datos de tu negocio');
    expect(s.strip().findAll('ion-button')).toHaveLength(1);
    await s.strip().get('[data-testid="blocking-configure-invoice.business_identity"]').trigger('click');
    await flush();
    expect(s.router.currentRoute.value.path).toBe('/invoice/settings');
  });

  it('on a low screen with two steps pending, one «Set up» leads to the first that can be set up from there', async () => {
    screenLow(true);
    // The first is an administrator's: «Set up» skips it for the next one.
    const delegated = await setup('/demo/items', status([legal({ actionable: false }), verifactu()]), ROUTES);
    expect(delegated.strip().findAll('ion-button')).toHaveLength(1);
    expect(delegated.strip().text()).not.toContain('VeriFactu');
    expect(delegated.strip().text()).not.toContain('Esto lo tiene que configurar un administrador.');
    await delegated.strip().get('[data-testid="blocking-configure-verifactu.config"]').trigger('click');
    await flush();
    expect(delegated.router.currentRoute.value.path).toBe('/verifactu/settings');
    delegated.wrapper.unmount();
    // On the very screen of the first one, «Set up» leads to the next one.
    const here = await setup('/invoice/settings', status([legal(), verifactu()]), ROUTES);
    expect(here.strip().findAll('ion-button')).toHaveLength(1);
    expect(here.strip().find('[data-testid="blocking-configure-verifactu.config"]').exists()).toBe(true);
  });

  it('on a low screen with no step that can be set up from there, says the consequence alone', async () => {
    screenLow(true);
    const s = await setup('/invoice/settings', status([legal(), verifactu({ actionable: false })]), ROUTES);
    expect(s.strip().get('.blocking-strip-title').text()).toBe('Todavía no puedes facturar');
    expect(s.strip().find('ion-button').exists()).toBe(false);
    expect(s.strip().find('.blocking-strip-note').exists()).toBe(false);
  });
});
