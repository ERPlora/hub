import type { ActionNotice, ActionNoticeSource } from '@erplora/ui/shell';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { defineComponent, h } from 'vue';

import type { SetupItem, SetupStatus } from '../operations/home';
import type { BellCounter } from '../operations-bell';
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

/** A counter as the server sends it: with the words of one that declares none of its own unless `fields` says. */
function counter(key: string, count: number, fields: Partial<BellCounter> = {}): BellCounter {
  const label = fields.label ?? `Counter ${key}`;
  return {
    key,
    app: key.split('.')[0],
    count,
    route: '/demo/items',
    label,
    icon: 'ion:warning-outline',
    severity: 'warning',
    title: `${label} (${count})`,
    body: null,
    action_label: 'Abrir',
    due: null,
    ...fields,
  };
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

  it('each counter is a notice with the words the server says: its gravity, heading, sentence, deadline and button', async () => {
    const s = await setup();
    await s.setupStatus(status([]));
    await s.counters([
      counter('appointment.to_confirm', 3, {
        route: '/appointment/agenda',
        icon: 'ion:calendar-outline',
        severity: 'danger',
        title: '3 citas por confirmar',
        body: 'Tus clientes esperan a que les confirmes las citas antes de que empiecen.',
        action_label: 'Confirmar las citas',
        due: '2026-12-01T10:30:00+01:00',
      }),
    ]);
    expect(notices()).toEqual([
      {
        id: 'appointment.to_confirm',
        severity: 'danger',
        icon: 'ion:calendar-outline',
        label: '3 citas por confirmar',
        title: '3 citas por confirmar',
        body: 'Tus clientes esperan a que les confirmes las citas antes de que empiecen.',
        count: 3,
        due: { at: '2026-12-01T10:30:00+01:00' },
        action: { label: 'Confirmar las citas', to: '/appointment/agenda' },
      },
    ]);
  });

  it('a counter with no sentence nor deadline is told without them', async () => {
    const s = await setup();
    await s.setupStatus(status([]));
    await s.counters([counter('demo.open_items', 2)]);
    expect(notice('demo.open_items')).toEqual({
      id: 'demo.open_items',
      severity: 'warning',
      icon: 'ion:warning-outline',
      label: 'Counter demo.open_items (2)',
      title: 'Counter demo.open_items (2)',
      count: 2,
      action: { label: 'Abrir', to: '/demo/items' },
    });
  });

  it('adds no words of its own: every counter, known or not, says exactly what the server sent', async () => {
    const s = await setup();
    await s.setupStatus(status([]));
    await s.counters([
      counter('base.failed_events', 2, { route: '/system#events', severity: 'info', title: 'Two', action_label: 'Look' }),
      counter('flow.waiting_runs', 1, { route: '/flow/runs', severity: 'danger', title: 'One', action_label: 'Go' }),
    ]);
    expect(notices().map((n) => [n.id, n.severity, n.title, n.action?.label])).toEqual([
      ['base.failed_events', 'info', 'Two', 'Look'],
      ['flow.waiting_runs', 'danger', 'One', 'Go'],
    ]);
  });

  it('a counter whose screen this hub lacks is told with no button', async () => {
    const s = await setup();
    await s.setupStatus(status([]));
    await s.counters([counter('demo.open_items', 1, { route: '/nowhere' }), counter('demo.other', 1, { route: '' })]);
    expect(notices().map((n) => n.action)).toEqual([undefined, undefined]);
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
    await s.counters([]);
    await s.setupStatus(status([legal({ title: 'Your business details', actionable: false })]));
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
