// VeriFactu → Events (VERIFACTU-F31; the old `erp-verifactu-events`): «Audit events», the live `verifactu.event.list`
// — When, Severity, Type and Message (composed by the server in the reader's language) —, the newest first, search
// «Search type or message…» and the filters of type, severity and day. It follows itself.
import { DataTable, EmptyState } from '@erplora/ui/components';
import { describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

import { flush, mountVerifactu } from '../__tests__/mount-verifactu';
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

async function setup() {
  const m = await mountVerifactu(EventsPage, { path: '/verifactu/events' });
  await m.live();
  const table = () => m.wrapper.findComponent(DataTable as unknown as Component);
  async function emit(name: string, ...args: unknown[]) {
    table().vm.$emit(name, ...args);
    await flush();
  }
  return { ...m, table, emit };
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

describe('EventsPage: the list fills the page (FIX-DATATABLE-HUB)', () => {
  it('AppPage `fill` and its DataTable `fill`, only stacks between them: from the topbar to the tabbar', async () => {
    const s = await setup();
    expect(listFillProblems(s.wrapper)).toEqual([]);
  });
});
