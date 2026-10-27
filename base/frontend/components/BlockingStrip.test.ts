// The blocking strip over every screen (hub#374; BASE-G22): while a ⛔ step is pending the invoice is refused,
// so it says the consequence and names what is missing, each with its way in. Not on the Home's «Summary»,
// whose checklist says strictly more a screenful below; on «Activity» it is back.
import { afterEach, describe, expect, it } from 'vitest';

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

afterEach(() => {
  document.body.innerHTML = '';
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
});
