// VeriFactu → Events (VERIFACTU-F31; the old `erp-verifactu-events`): «Audit events», the live `verifactu.event.list`
// — When, Severity, Type and Message (composed by the server in the reader's language) —, the newest first, search
// «Search type or message…» and the filters of type, severity and day. It follows itself.
import { DataTable, EmptyState } from '@erplora/ui/components';
import { describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

import { flush, type MountOptions, mountVerifactu } from '../__tests__/mount-verifactu';
import { plain } from '../lib/format';
import type { EventOut } from '../operations';
import EventsPage from './EventsPage.vue';
import { listFillProblems } from '../../../../frontend/testing/list-fill';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const OP = 'verifactu.event.list';
const EVENT: EventOut = {
  id: 'e1',
  created_at: '2026-10-14T10:00:00Z',
  kind: 'chain_broken',
  severity: 'critical',
  message: 'Fingerprint chain BROKEN at sequence 7 (B12345674).',
  record_id: null,
  invoice_number: '',
};

async function setup(options: MountOptions = {}) {
  const m = await mountVerifactu(EventsPage, { path: '/verifactu/events', ...options });
  await m.live();
  const table = () => m.wrapper.findComponent(DataTable as unknown as Component);
  async function emit(name: string, ...args: unknown[]) {
    table().vm.$emit(name, ...args);
    await flush();
  }
  const prop = <T = unknown>(name: string) => (table().props() as Record<string, unknown>)[name] as T;
  return { ...m, table, emit, prop };
}

describe('EventsPage', () => {
  it('follows the events, the newest first, and paints When, Severity, Type and Message', async () => {
    const s = await setup();
    expect(s.params(OP)).toEqual([{ sort: 'created_at', dir: 'desc', limit: 50, offset: 0 }]);
    await s.result(OP, { rows: [EVENT], total: 1, limit: 50, offset: 0 });
    expect(((s.table().props() as Record<string, unknown>).columns as Array<{ label: string }>).map((c) => c.label)).toEqual(['When', 'Severity', 'Type', 'Message']);
    const cells = s.wrapper.findAll('[data-testid="verifactu-events-row"]')[0].findAll('[role="cell"]').map((c) => plain(c.text().trim()));
    expect(cells.slice(1, 4)).toEqual(['Critical', 'Chain broken', EVENT.message]);
    expect((s.table().props() as Record<string, unknown>).searchPlaceholder).toBe('Search type or message…');
  });

  it('searches on the server', async () => {
    const s = await setup();
    await s.result(OP, { rows: [EVENT], total: 1, limit: 50, offset: 0 });
    await s.emit('update:search', 'rota');
    await s.reopen();
    expect(s.params(OP)).toEqual([{ search: 'rota', sort: 'created_at', dir: 'desc', limit: 50, offset: 0 }]);
  });

  it('says «No events.»', async () => {
    const s = await setup();
    await s.result(OP, { rows: [], total: 0, limit: 50, offset: 0 });
    expect(s.wrapper.findComponent(EmptyState).props('heading')).toBe('No events.');
  });
});

describe('EventsPage: the filters behind the table funnel (FIX-DATATABLE-HUB-FILTERS-2B)', () => {
  // flow: ninguno — FIX DataTable parte 2b-2 (PLAN-MIGRATIONS §13: filtros como en la vieja)
  type Filter = { type: string; key?: string; keys?: string[]; options?: Array<{ value: string; label: string }> };
  const PAGE = { rows: [EVENT], total: 1, limit: 50, offset: 0 };

  it('When (by day), Severity and Type filter on their columns', async () => {
    const s = await setup();
    await s.result(OP, PAGE);
    expect(s.prop('filterable')).toBe(true);
    const columns = s.prop<Array<{ key: string; label: string; filter?: Filter }>>('columns');
    expect(columns.filter((c) => c.filter).map((c) => [c.label, c.filter?.key ?? c.key, c.filter?.type, c.filter?.keys])).toEqual([
      ['When', 'created_at', 'daterange', ['date_from', 'date_to']],
      ['Severity', 'severity', 'select', undefined],
      ['Type', 'kind', 'select', undefined],
    ]);
    const options = (key: string) => columns.find((c) => c.key === key)?.filter?.options;
    expect(options('severity')).toEqual([
      { value: 'debug', label: 'Debug' },
      { value: 'info', label: 'Info' },
      { value: 'warning', label: 'Warning' },
      { value: 'error', label: 'Error' },
      { value: 'critical', label: 'Critical' },
    ]);
    expect(options('kind')?.find((o) => o.value === 'chain_broken')?.label).toBe('Chain broken');
    expect(s.prop('filterFields') ?? []).toEqual([]);
  });

  it('the funnel panel applies on «Apply»: every filter, and counts them', async () => {
    const s = await setup();
    await s.result(OP, PAGE);
    await s.find('verifactu-events-filters-toggle').trigger('click');
    await flush();
    const panel = s.find('verifactu-events-filters-panel');
    const set = (name: string, value: string) =>
      panel.get(`[data-testid="verifactu-events-filter-${name}"]`).element.dispatchEvent(new CustomEvent('ionChange', { detail: { value } }));
    set('date_from', '2026-10-01');
    set('date_to', '2026-10-14');
    set('severity', 'critical');
    set('kind', 'chain_broken');
    await flush();
    await s.reopen();
    expect(s.params(OP), 'the panel edits a draft: nothing is asked before «Apply»').toEqual([{ sort: 'created_at', dir: 'desc', limit: 50, offset: 0 }]);
    await panel.get('[data-testid="verifactu-events-filters-apply"]').trigger('click');
    await flush();
    await s.reopen();
    expect(s.params(OP)).toEqual([
      { date_from: '2026-10-01', date_to: '2026-10-14', severity: 'critical', kind: 'chain_broken', sort: 'created_at', dir: 'desc', limit: 50, offset: 0 },
    ]);
    expect(s.find('verifactu-events-filters-count').text()).toBe('3');
  });

  it('a day «until» before its «from» is said under it, in both languages, and does not filter', async () => {
    const s = await setup();
    await s.result(OP, PAGE);
    expect(s.prop('filterErrors')).toEqual({});
    await s.emit('update:filters', { date_from: '2026-10-14', date_to: '2026-10-13' });
    await s.reopen();
    expect(s.prop('filterErrors')).toEqual({ date_to: 'The end date cannot be before the start date.' });
    expect(s.params(OP)).toEqual([{ date_from: '2026-10-14', sort: 'created_at', dir: 'desc', limit: 50, offset: 0 }]);
    const es = await setup({ locale: 'es' });
    await es.result(OP, PAGE);
    await es.emit('update:filters', { date_from: '2026-10-14', date_to: '2026-10-13' });
    expect(es.prop('filterErrors')).toEqual({ date_to: 'La fecha final no puede ser anterior a la inicial.' });
  });

  it('a filter the server refuses (422) goes under its filter; the rows stay and no error replaces them', async () => {
    const s = await setup();
    await s.result(OP, PAGE);
    await s.emit('update:filters', { date_from: '0001-01-01' });
    await s.reopen();
    await s.result(OP, PAGE);
    const refused = { code: 'invalid_payload', message: 'Some fields are not valid.', fields: { date_from: 'Input should be a valid date.' } };
    s.net.lastStream().push(`event: error\ndata: ${JSON.stringify({ id: s.subId(OP), error: refused })}\n\n`);
    await flush();
    expect(s.prop('filterErrors')).toEqual({ date_from: 'Input should be a valid date.' });
    expect(s.prop('error')).toBeUndefined();
    expect(s.wrapper.findAll('[data-testid="verifactu-events-row"]')).toHaveLength(1);
  });
});

describe('EventsPage: the list fills the page (FIX-DATATABLE-HUB)', () => {
  it('AppPage `fill` and its DataTable `fill`, only stacks between them: from the topbar to the tabbar', async () => {
    const s = await setup();
    expect(listFillProblems(s.wrapper)).toEqual([]);
  });
});
