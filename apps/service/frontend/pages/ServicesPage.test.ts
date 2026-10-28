// Services → Services (WORKBOOK «Pantallas · Servicios»; SERVICE-F01 to F05): the live
// `service.service.list` in a server-side DataTable — Name, Category, Pricing, Price, Duration (min) and
// Status (Active, Not configured with its reason, Archived) —, «Search service…», column filters (the
// Status filter on Archived is the archived view), list or cards, 50 a page. «New service» and a row
// open the form; a row offers Edit and Archive (with its confirmation), and Restore in the archived view.
import { ConfirmDialog, DataTable, EmptyState, InlineFeedback } from '@erplora/ui/components';
import { AppPage } from '@erplora/ui/shell';
import { describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

import type { ServiceOut } from '../operations';
import { business, EMPLOYEE, flush, JAPANESE, MANAGER, type MountOptions, mountService, OWNER, page, POLISH } from '../__tests__/mount-service';
import ServiceFormModal from '../components/ServiceFormModal.vue';
import ServicesPage from './ServicesPage.vue';
import { listFillProblems } from '../../../../frontend/testing/list-fill';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const OP = 'service.service.list';
const service = (id: string, over: Partial<ServiceOut> = {}): ServiceOut => ({
  id,
  name: 'Haircut',
  description: '',
  short_description: '',
  category_id: 'c1',
  category_name: 'Hair',
  pricing_type: 'fixed',
  price: 2250,
  min_price: null,
  max_price: null,
  cost: 0,
  duration_minutes: 30,
  buffer_before: 0,
  buffer_after: 0,
  max_capacity: 1,
  is_bookable: true,
  requires_confirmation: false,
  allow_online_booking: true,
  sort_order: 0,
  is_featured: false,
  sku: '',
  barcode: '',
  notes: '',
  tax_category_id: 't1',
  tax_category_key: 'service.generic',
  tax_category_name: 'Service — generic',
  needs_tax_setup: false,
  status: 'active',
  is_active: true,
  archived_at: null,
  created_at: '2026-10-01T10:00:00Z',
  updated_at: '2026-10-01T10:00:00Z',
  ...over,
});
const ROWS = [
  service('s1'),
  service('s2', { name: 'Beard', category_id: null, category_name: null, pricing_type: 'from', tax_category_key: null, needs_tax_setup: true, status: 'unconfigured' }),
];

async function setup(options: MountOptions = {}) {
  const m = await mountService(ServicesPage, { path: '/service/services', ...options });
  await m.live();
  const table = () => m.wrapper.findComponent(DataTable as unknown as Component);
  const prop = <T = unknown>(name: string) => (table().props() as Record<string, unknown>)[name] as T;
  const rows = () => m.wrapper.findAll('[data-testid="service-services-row"]');
  const cells = (i: number) => rows()[i].findAll('[role="cell"]').map((c) => c.text().trim());
  const actions = (row: ServiceOut) =>
    prop<Array<{ id: string; hidden?: (r: ServiceOut) => boolean }>>('actions')
      .filter((a) => !a.hidden?.(row))
      .map((a) => a.id);
  return { ...m, table, prop, rows, cells, actions, list: () => m.params(OP), show: (data: unknown) => m.result(OP, data) };
}

describe('ServicesPage', () => {
  it('follows the offered services sorted by name, 50 from the first', async () => {
    const s = await setup();
    expect(s.list()).toEqual([{ sort: 'name', limit: 50, offset: 0 }]);
    await s.show(page(ROWS));
    expect(s.table().props()).toMatchObject({ serverSide: true, searchable: true, testid: 'service-services', total: 2, views: ['table', 'cards'] });
    // The column filters live behind «Filters» (the old screen's funnel), not in a row that pushes the list down.
    expect(s.prop('filterable')).toBe(true);
    expect(s.prop('searchPlaceholder')).toBe('Search service…');
    expect(s.prop<{ add: string }>('labels').add).toBe('New service');
    expect(s.wrapper.findComponent(AppPage).props('title')).toBe('Services');
  });

  it('paints Name, Category, Pricing, Price, Duration and Status, with the reason of «Not configured»', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    expect(s.prop<Array<{ key: string; label: string }>>('columns').map((c) => [c.key, c.label])).toEqual([
      ['name', 'Name'],
      ['category_name', 'Category'],
      ['pricing_type', 'Pricing'],
      ['price', 'Price'],
      ['duration_minutes', 'Duration (min)'],
      ['status', 'Status'],
    ]);
    expect(s.cells(0).slice(0, 6)).toEqual(['Haircut', 'Hair', 'Fixed price', '€22.50', '30', 'Active']);
    expect(s.cells(1).slice(1, 3)).toEqual(['—', 'From']);
    expect(s.cells(1)[5]).toContain('Not configured');
    expect(s.cells(1)[5]).toContain('No tax category: it cannot be charged');
  });

  it('filters by column: the price in euros as cents, the status, and Archived is the archived view', async () => {
    const s = await setup();
    s.table().vm.$emit('filtersChange', { name: 'cut', pricing_type: 'from', price_from: '10', price_to: '25,50', duration_minutes_to: '60' });
    await flush();
    expect(s.list()).toEqual([
      { name: 'cut', pricing_type: 'from', price_min: 1000, price_max: 2550, duration_max: 60, sort: 'name', limit: 50, offset: 0 },
    ]);
    s.table().vm.$emit('filtersChange', { status: 'archived' });
    await flush();
    expect(s.list()).toEqual([{ status: 'archived', sort: 'name', limit: 50, offset: 0 }]);
    await s.show(page([service('s3', { status: 'archived', is_active: false })]));
    expect(s.actions(service('s3', { status: 'archived', is_active: false }))).toEqual(['restore']);
    expect(s.prop('rowClickable')).toBe(false);
  });

  it("wears the old module's icons: the briefcase on its cards and its empty list, «Archive» its archive box", async () => {
    const s = await setup();
    await s.show(page(ROWS));
    expect(s.prop<Array<{ id: string; icon?: string }>>('actions').map((a) => [a.id, a.icon])).toEqual([
      ['edit', 'create-outline'],
      ['archive', 'archive-outline'],
    ]);
    expect(s.prop<() => string>('cardIcon')()).toBe('briefcase-outline');
    await s.show(page([]));
    expect(s.wrapper.findComponent(EmptyState).props('icon')).toBe('briefcase-outline');
  });

  it('sorts and searches on the server; no service at all says «No services.»', async () => {
    const s = await setup();
    await s.show(page([]));
    expect(s.wrapper.findComponent(EmptyState).props('heading')).toBe('No services.');
    s.table().vm.$emit('sortChange', { sort: 'price', dir: 'desc' });
    s.table().vm.$emit('update:search', 'cut');
    await flush();
    expect(s.list()).toEqual([{ search: 'cut', sort: '-price', limit: 50, offset: 0 }]);
  });

  it('«New service» and a row open the form', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    const modal = () => s.wrapper.findComponent(ServiceFormModal);
    s.table().vm.$emit('add');
    await flush();
    expect([modal().props('open'), modal().props('service')]).toEqual([true, null]);
    modal().vm.$emit('update:open', false);
    s.table().vm.$emit('rowClick', ROWS[0]);
    await flush();
    expect([modal().props('open'), modal().props('service'), modal().props('canChange')]).toEqual([true, ROWS[0], true]);
    expect(s.actions(ROWS[0])).toEqual(['edit', 'archive']);
  });

  it('archives after its confirmation, naming the service', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    s.table().vm.$emit('action', { actionId: 'archive', row: ROWS[0] });
    await flush();
    const dialog = s.wrapper.findComponent(ConfirmDialog);
    expect([dialog.props('open'), dialog.props('title'), dialog.props('message'), dialog.props('confirmLabel')]).toEqual([
      true,
      'Archive service',
      'Haircut — it will no longer be offered or bookable. Its history and the appointments already booked are kept.',
      'Archive',
    ]);
    s.answer(200, { ...ROWS[0], status: 'archived' });
    dialog.vm.$emit('confirm');
    await flush();
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/service/services/archive', query: {}, body: { id: 's1' } }]);
  });

  // SERVICE-F04: with Appointments on (its permission only exists then), the confirmation warns of the upcoming
  // appointments that keep using the service; the warning is advice and never stops the archive.
  describe('the upcoming appointments of the service being archived', () => {
    const COUNT = '/api/appointment/appointments/count_for_service';
    const WITH_AGENDA = { ...OWNER, permissions: [...OWNER.permissions, 'appointment.view_own_appointment'] };
    const LINE = '2 upcoming appointment(s) still use this service. They keep their booking, price and length; only new bookings stop.';

    async function archiving(session = WITH_AGENDA, answers: Record<string, [number, unknown]> = {}) {
      const s = await setup({ session });
      await s.show(page(ROWS));
      s.answerBy({ '/api/service/services/archive': [200, { ...ROWS[0], status: 'archived' }], ...answers });
      s.table().vm.$emit('action', { actionId: 'archive', row: ROWS[0] });
      await flush();
      await flush();
      return { ...s, dialog: () => s.wrapper.findComponent(ConfirmDialog) };
    }

    it('says how many upcoming appointments still use it', async () => {
      const s = await archiving(WITH_AGENDA, { [COUNT]: [200, { count: 2, earliest: '2026-10-22T10:00:00+02:00' }] });
      expect(s.sent()[0]).toEqual({ method: 'GET', path: COUNT, query: { service_id: 's1' }, body: undefined });
      expect(s.dialog().props('consequences')).toEqual([LINE]);
    });

    it('in Spanish', async () => {
      const s = await setup({ session: WITH_AGENDA, locale: 'es' });
      await s.show(page(ROWS));
      s.answerBy({ [COUNT]: [200, { count: 1, earliest: null }] });
      s.table().vm.$emit('action', { actionId: 'archive', row: ROWS[0] });
      await flush();
      await flush();
      expect(s.wrapper.findComponent(ConfirmDialog).props('consequences')).toEqual([
        '1 cita(s) próxima(s) siguen usando este servicio. Conservan su reserva, precio y duración; solo dejan de admitirse reservas nuevas.',
      ]);
    });

    it('says nothing when none uses it', async () => {
      const s = await archiving(WITH_AGENDA, { [COUNT]: [200, { count: 0, earliest: null }] });
      expect(s.dialog().props('consequences')).toEqual([]);
    });

    it('does not ask without Appointments, and a failed answer leaves the line out but the archive works', async () => {
      const off = await archiving(OWNER);
      expect(off.sent()).toEqual([]);
      expect(off.dialog().props('consequences')).toEqual([]);
      const s = await archiving(WITH_AGENDA, { [COUNT]: [404, { error: { code: 'app_inactive', message: 'Not active' } }] });
      expect(s.dialog().props('consequences')).toEqual([]);
      s.dialog().vm.$emit('confirm');
      await flush();
      expect(s.sent().map((c) => c.path)).toEqual([COUNT, '/api/service/services/archive']);
    });

    it('a late answer for another service never lands on this one', async () => {
      const s = await setup({ session: WITH_AGENDA });
      await s.show(page(ROWS));
      let late: (r: Response) => void = () => undefined;
      s.net.onApi(({ url }) =>
        url.includes('service_id=s1')
          ? new Promise<Response>((resolve) => (late = resolve))
          : Response.json({ count: 0, earliest: null }),
      );
      s.table().vm.$emit('action', { actionId: 'archive', row: ROWS[0] });
      await flush();
      s.wrapper.findComponent(ConfirmDialog).vm.$emit('cancel');
      s.table().vm.$emit('action', { actionId: 'archive', row: ROWS[1] });
      await flush();
      late(Response.json({ count: 2, earliest: null }));
      await flush();
      await flush();
      expect(s.wrapper.findComponent(ConfirmDialog).props('message')).toContain('Beard');
      expect(s.wrapper.findComponent(ConfirmDialog).props('consequences')).toEqual([]);
    });
  });

  it('restores from the archived view and says a refusal above the table', async () => {
    const s = await setup();
    s.table().vm.$emit('filtersChange', { status: 'archived' });
    await flush();
    s.answer(404, { error: { code: 'service.service_not_found', message: 'That service does not exist in this business.' } });
    s.table().vm.$emit('action', { actionId: 'restore', row: ROWS[0] });
    await flush();
    await flush();
    expect(s.sent().map((c) => [c.path, c.body])).toEqual([['/api/service/services/restore', { id: 's1' }]]);
    const banner = s.wrapper.findAllComponents(InlineFeedback).find((b) => b.attributes('data-testid') === 'service-services-row-error');
    expect([banner?.props('heading'), banner?.text()]).toEqual(['Could not restore the service', expect.stringContaining('does not exist')]);
  });

  it('a manager edits but does not archive; an employee adds but neither edits nor archives', async () => {
    const manager = await setup({ session: MANAGER });
    await manager.show(page(ROWS));
    expect(manager.actions(ROWS[0])).toEqual(['edit']);
    const employee = await setup({ session: EMPLOYEE });
    await employee.show(page(ROWS));
    expect([employee.prop('addable'), employee.prop('rowClickable'), employee.actions(ROWS[0])]).toEqual([true, false, []]);
  });

  // flow service-business-currency: the price is the business's (its country's), never a euro fixed in the app.
  describe('in the business currency (service-business-currency)', () => {
    it('paints the price in złoty for a business in Poland, never in euros', async () => {
      const s = await setup({ business: business(POLISH) });
      await s.show(page(ROWS));
      expect(s.cells(0)[3].replace(/\s/g, ' ')).toBe('zł 22.50');
      expect(s.wrapper.text()).not.toContain('€');
    });

    it('paints a price of 1500 yen as ¥1,500 for a business in Japan: the yen has no minor units', async () => {
      const s = await setup({ business: business(JAPANESE) });
      await s.show(page([service('s1', { price: 1500 })]));
      expect(s.cells(0)[3]).toBe('¥1,500');
    });

    it('paints a figure without a symbol until the business answers', async () => {
      const s = await setup({ business: null });
      await s.show(page(ROWS));
      expect(s.cells(0)[3]).toBe('22.50');
    });

    it('reads the price filter in the business currency’s minor units: «1500» is 1500 yen', async () => {
      const s = await setup({ business: business(JAPANESE) });
      s.table().vm.$emit('filtersChange', { price_from: '1500', price_to: '¥2,000' });
      await flush();
      expect(s.list()).toEqual([{ price_min: 1500, price_max: 2000, sort: 'name', limit: 50, offset: 0 }]);
    });

    it('a price filter typed before the business answers is read again in its currency, from the first page', async () => {
      const s = await setup({ business: null });
      s.table().vm.$emit('filtersChange', { price_from: '1500' });
      await flush();
      s.table().vm.$emit('pageChange', 2);
      await flush();
      expect(s.list()).toEqual([{ price_min: 150000, sort: 'name', limit: 50, offset: 100 }]);
      await s.result('base.business.get', business(JAPANESE));
      expect(s.list()).toEqual([{ price_min: 1500, sort: 'name', limit: 50, offset: 0 }]);
    });
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    await s.show(page(ROWS));
    expect(s.prop('searchPlaceholder')).toBe('Buscar servicio…');
    expect(s.cells(0)[2]).toBe('Precio fijo');
    expect(s.cells(0)[3]).toMatch(/^22,50\s€$/);
    expect(s.cells(1)[5]).toContain('Sin configurar');
  });
});

describe('ServicesPage: the list fills the page (FIX-DATATABLE-HUB)', () => {
  it('AppPage `fill` and its DataTable `fill`, only stacks between them: from the topbar to the tabbar', async () => {
    const s = await setup();
    expect(listFillProblems(s.wrapper)).toEqual([]);
  });
});
