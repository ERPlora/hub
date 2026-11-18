import type { ActionNotice, ActionNoticeSource } from '@erplora/ui/shell';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { defineComponent, h } from 'vue';

import type { BellCounter, SetupItem, SetupStatus } from '../operations';
import { errorFrame, flush, mountBase, subId } from '../__tests__/mount-base';
import { useHubActionNotices } from './action-notices';

let source: ActionNoticeSource;
const Host = defineComponent({
  setup() {
    source = useHubActionNotices();
    return () => h('div');
  },
});

const ROUTES = ['/appointment/agenda', '/whatsapp_inbox/inbox', '/printing/printers', '/demo/items', '/system', '/flow/runs', '/invoice/issuer', '/verifactu/settings'];

function counter(key: string, count: number, fields: Partial<BellCounter> & Record<string, unknown> = {}): BellCounter {
  return { key, app: key.split('.')[0], count, route: '/demo/items', label: `Counter ${key}`, icon: 'ion:warning-outline', ...fields };
}

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
    route: '/invoice/issuer',
    order: 40,
    ...fields,
  };
}

const VERIFACTU = { key: 'verifactu.sending_route', app: 'verifactu', title: 'Configura VeriFactu', route: '/verifactu/settings', order: 60 };

function status(items: SetupItem[]): SetupStatus {
  const blocking = items.filter((item) => item.state === 'pending' && item.level === 'legal').length;
  return { total: items.length, pending: blocking, unavailable: 0, blocking_pending: blocking, items };
}

async function setup(options: { locale?: 'en' | 'es'; path?: string } = {}) {
  const m = await mountBase(Host, { routes: ROUTES, locale: options.locale ?? 'es', path: options.path });
  const call = await m.live();
  const counters = (list: BellCounter[], rev = 1) => m.result(call, 'base.bell.counters', { counters: list, refresh_every: null }, rev);
  const setupStatus = (value: SetupStatus, rev = 1) => m.result(call, 'base.setup.status', value, rev);
  return { ...m, call, counters, setupStatus };
}

const notices = (): readonly ActionNotice[] => source.notices.value ?? [];
const notice = (id: string): ActionNotice | undefined => notices().find((n) => n.id === id);

afterEach(() => {
  document.body.innerHTML = '';
});

describe('useHubActionNotices: the counters of the bell', () => {
  it('gives nothing until both the counters and the setup gave their first result', async () => {
    const s = await setup();
    expect(s.client.stream.subscriptions('base.bell.counters').map((sub) => sub.params)).toEqual([{}]);
    expect(s.client.stream.subscriptions('base.setup.status').map((sub) => sub.params)).toEqual([{}]);
    expect(source.notices.value).toBeUndefined();
    await s.counters([]);
    expect(source.notices.value).toBeUndefined();
    await s.setupStatus(status([]));
    expect(source.notices.value).toEqual([]);
    expect(source.failed.value).toBe(false);
  });

  it('each counter is a notice: its key, icon and count, its words with the number, and the way to its screen', async () => {
    const s = await setup();
    await s.setupStatus(status([]));
    await s.counters([counter('appointment.to_confirm', 3, { route: '/appointment/agenda', icon: 'ion:calendar-outline' })]);
    expect(notices()).toEqual([
      {
        id: 'appointment.to_confirm',
        severity: 'warning',
        icon: 'ion:calendar-outline',
        label: '3 citas por confirmar',
        title: '3 citas por confirmar',
        count: 3,
        action: { label: 'Confirmar las citas', to: '/appointment/agenda' },
      },
    ]);
    await s.counters([counter('appointment.to_confirm', 1, { route: '/appointment/agenda' })], 2);
    expect(notice('appointment.to_confirm')?.title).toBe('1 cita por confirmar');
  });

  it('the counters known today carry their gravity and their action; any other, a warning with «Abrir»', async () => {
    const s = await setup();
    await s.setupStatus(status([]));
    await s.counters([
      counter('base.failed_events', 2, { route: '/system#events', label: 'Eventos caídos' }),
      counter('base.plan_limits', 1, { route: '/system#usage', label: 'Límites del plan' }),
      counter('whatsapp_inbox.awaiting_reply', 4, { route: '/whatsapp_inbox/inbox' }),
      counter('printing.stalled_kitchen', 2, { route: '/printing/printers', label: 'Nadie está imprimiendo «Cocina»' }),
      counter('demo.open_items', 5),
      counter('flow.waiting_runs', 2, { route: '/flow/runs', label: 'Automatizaciones esperando' }),
    ]);
    const said = notices().map((n) => [n.id, n.severity, n.title, n.action?.label]);
    expect(said).toEqual([
      ['base.failed_events', 'danger', '2 eventos caídos', 'Revisar los eventos'],
      ['base.plan_limits', 'warning', '1 límite del plan por revisar', 'Ver el uso del plan'],
      ['whatsapp_inbox.awaiting_reply', 'warning', '4 clientes de WhatsApp esperando respuesta', 'Contestar a los clientes'],
      ['printing.stalled_kitchen', 'warning', 'Nadie está imprimiendo «Cocina»: 2 trabajos esperando', 'Ver las impresoras'],
      ['demo.open_items', 'info', '5 elementos de demo abiertos', 'Ver los elementos'],
      ['flow.waiting_runs', 'warning', 'Automatizaciones esperando (2)', 'Abrir'],
    ]);
    expect(notice('flow.waiting_runs')?.label).toBe('Automatizaciones esperando (2)');
  });

  it('what the server says of a counter wins: its gravity, title, sentence, action and deadline', async () => {
    const s = await setup();
    await s.setupStatus(status([]));
    const due = { at: '2026-12-01T00:00:00Z', from: '2026-11-24T00:00:00Z' };
    await s.counters([
      counter('appointment.to_confirm', 3, {
        route: '/appointment/agenda',
        severity: 'danger',
        title: 'Tres citas de hoy sin confirmar',
        body: 'Las clientas no saben si las esperas.',
        action_label: 'Confirmarlas ahora',
        due,
      }),
    ]);
    expect(notice('appointment.to_confirm')).toMatchObject({
      severity: 'danger',
      label: 'Tres citas de hoy sin confirmar',
      title: 'Tres citas de hoy sin confirmar',
      body: 'Las clientas no saben si las esperas.',
      due,
      action: { label: 'Confirmarlas ahora', to: '/appointment/agenda' },
    });
  });

  it('a counter whose screen this hub lacks is told with no button', async () => {
    const s = await setup();
    await s.setupStatus(status([]));
    await s.counters([counter('demo.open_items', 1, { route: '/nowhere' }), counter('demo.other', 1, { route: '' })]);
    expect(notices().map((n) => n.action)).toEqual([undefined, undefined]);
  });

  it('a counter with no icon of its own takes the bell’s', async () => {
    const s = await setup();
    await s.setupStatus(status([]));
    await s.counters([counter('demo.open_items', 1, { icon: '' })]);
    expect(notice('demo.open_items')?.icon).toBe('ion:notifications-outline');
  });
});

describe('useHubActionNotices: «You cannot issue invoices yet»', () => {
  it('while a step blocks invoicing: one urgent notice that says what is missing, with «Configurar» to each step', async () => {
    const s = await setup();
    await s.counters([]);
    await s.setupStatus(status([legal(), legal(VERIFACTU)]));
    expect(notices()).toEqual([
      {
        id: 'base.blocking',
        severity: 'danger',
        icon: 'ion:alert-circle-outline',
        label: 'Todavía no puedes facturar',
        title: 'Todavía no puedes facturar',
        body: 'No se podrá emitir ningún tique ni factura hasta que configures esto: Los datos de tu negocio y Configura VeriFactu.',
        action: { label: 'Configurar los datos del negocio', to: '/invoice/issuer' },
        secondary: { label: 'Configurar VeriFactu', to: '/verifactu/settings' },
      },
    ]);
  });

  it('a step it knows no words for is named in its «Configurar»', async () => {
    const s = await setup();
    await s.counters([]);
    await s.setupStatus(status([legal({ key: 'tax.registry', app: 'tax', title: 'Tu registro fiscal', route: '/system' })]));
    expect(notice('base.blocking')?.action).toEqual({ label: 'Configurar: Tu registro fiscal', to: '/system' });
  });

  it('to whoever cannot set it up: the same notice with no buttons, saying an administrator has to', async () => {
    const s = await setup();
    await s.counters([]);
    await s.setupStatus(status([legal({ actionable: false })]));
    const blocking = notice('base.blocking');
    expect(blocking?.body).toBe(
      'No se podrá emitir ningún tique ni factura hasta que configures esto: Los datos de tu negocio. Esto lo tiene que configurar un administrador.',
    );
    expect([blocking?.action, blocking?.secondary]).toEqual([undefined, undefined]);
  });

  it('only the steps that can be set up from a screen of this hub carry a button', async () => {
    const s = await setup();
    await s.counters([]);
    await s.setupStatus(status([legal({ route: '/nowhere' }), legal(VERIFACTU)]));
    const blocking = notice('base.blocking');
    expect([blocking?.action, blocking?.secondary]).toEqual([{ label: 'Configurar VeriFactu', to: '/verifactu/settings' }, undefined]);
  });

  it('a step that is done, unavailable or not legal blocks nothing; it goes as soon as the last one is done', async () => {
    const s = await setup();
    await s.counters([]);
    await s.setupStatus(status([legal()]));
    expect(notice('base.blocking')).toBeDefined();
    await s.setupStatus({ ...status([legal({ state: 'done' })]), blocking_pending: 0 }, 2);
    expect(notices()).toEqual([]);
    await s.setupStatus(status([legal({ level: 'functional' }), legal({ state: 'unavailable' })]), 3);
    expect(notices()).toEqual([]);
  });

  it('stays on every screen, the Home’s «Summary» too, beside the counters', async () => {
    const s = await setup({ path: '/' });
    await s.counters([counter('demo.open_items', 2)]);
    await s.setupStatus(status([legal()]));
    expect(notices().map((n) => n.id).sort()).toEqual(['base.blocking', 'demo.open_items']);
  });

  it('in English', async () => {
    const s = await setup({ locale: 'en' });
    await s.counters([counter('appointment.to_confirm', 2, { route: '/appointment/agenda' })]);
    await s.setupStatus(status([legal({ title: 'Your business details', actionable: false })]));
    expect(notice('appointment.to_confirm')).toMatchObject({ title: '2 appointments to confirm', action: { label: 'Confirm the appointments' } });
    expect(notice('base.blocking')).toMatchObject({
      title: 'You cannot issue invoices yet',
      body: 'No ticket or invoice can be issued until this is set up: Your business details. An administrator has to set this up.',
    });
  });
});

describe('useHubActionNotices: when a read fails', () => {
  it('a failed read of either says so and keeps what it gave; retrying reopens the stream', async () => {
    const s = await setup();
    await s.counters([counter('demo.open_items', 2)]);
    await s.setupStatus(status([legal()]));
    s.call.push(errorFrame(subId(s.client, 'base.setup.status'), 'internal'));
    await flush();
    expect(source.failed.value).toBe(true);
    expect(notices().map((n) => n.id).sort()).toEqual(['base.blocking', 'demo.open_items']);
    await s.setupStatus(status([legal()]), 2);
    expect(source.failed.value).toBe(false);

    s.call.push(errorFrame(subId(s.client, 'base.bell.counters'), 'internal'));
    await flush();
    expect(source.failed.value).toBe(true);
    const reconnect = vi.spyOn(s.client.stream, 'reconnect');
    source.retry?.();
    expect(reconnect).toHaveBeenCalled();
  });

  it('a query that failed before its first result does not keep the other one waiting', async () => {
    const s = await setup();
    s.call.push(errorFrame(subId(s.client, 'base.setup.status'), 'internal'));
    await flush();
    await s.counters([counter('demo.open_items', 2)]);
    expect(source.failed.value).toBe(true);
    expect(notices().map((n) => n.id)).toEqual(['demo.open_items']);
  });
});
