// Sales & POS → Quick notes (SALE-F36; WORKBOOK «Pantallas · Notas rápidas»): the old intro, then the live
// `sale.quick_note.list` in a server-side DataTable — Note and Position —, «Search a note…», 50 a page
// sorted by position. Whoever may change the till settings gets «+», «Edit» (also a tap on the row) and
// «Delete» (confirmed with the old «Delete quick note» text); anyone else sees the list read-only. Every
// state of the screen: loading, empty, no results, error with Retry, reconnecting, app inactive.
import { DataTable, EmptyState } from '@erplora/ui/components';
import { AppPage } from '@erplora/ui/shell';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

import { BYE, EMPLOYEE, errorFrame, flush, type MountOptions, mountSale } from '../__tests__/mount-sale';
import QuickNoteFormModal from '../components/backoffice/QuickNoteFormModal.vue';
import type { QuickNoteOut } from '../operations';
import QuickNotesPage from './QuickNotesPage.vue';

const mocks = vi.hoisted(() => ({ confirm: vi.fn() }));
vi.mock('@erplora/ui/components', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/components')>()),
  useConfirm: () => ({ confirm: mocks.confirm }),
}));
vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});
beforeEach(() => mocks.confirm.mockReset());

const OP = 'sale.quick_note.list';
const note = (id: string, text: string, sort_order: number): QuickNoteOut => ({ id, text, sort_order });
const PAGE = { rows: [note('n1', 'no salt', 0), note('n2', 'medium rare', 1), note('n3', 'no ice', 2)], total: 3, limit: 50, offset: 0 };
const EMPTY = { rows: [], total: 0, limit: 50, offset: 0 };
const GONE = 'That quick note is no longer in this business. Reload the list and try again.';

async function setup(options: MountOptions = {}) {
  const m = await mountSale(QuickNotesPage, { path: '/sale/quick-notes', ...options });
  await m.live();
  const table = () => m.wrapper.findComponent(DataTable as unknown as Component);
  const prop = <T = unknown>(name: string) => (table().props() as Record<string, unknown>)[name] as T;
  const rows = () => m.wrapper.findAll('[data-testid="sale-quick-notes-row"]');
  const show = (page: unknown) => m.result(OP, page);
  async function emit(event: string, ...args: unknown[]) {
    table().vm.$emit(event, ...args);
    await flush();
    await m.reopen();
  }
  const form = () => m.wrapper.findComponent(QuickNoteFormModal);
  return { ...m, table, prop, rows, show, emit, form };
}

describe('QuickNotesPage: the live list', () => {
  it('sits under «Sales & POS» with the tabbar of its sections, the old intro on top', async () => {
    const s = await setup();
    const page = s.wrapper.findComponent(AppPage);
    expect([page.props('title'), page.props('tabsLabel')]).toEqual(['Sales & POS', 'Sales & POS sections']);
    expect((page.props('tabs') as Array<{ to: string }>).map((tab) => tab.to)).toContain('/sale/quick-notes');
    expect(s.find('sale-quick-notes-intro').text()).toBe(
      'The notes the till offers with one tap on the line-note sheet. The waiter can still type anything by hand.',
    );
  });

  it('follows sale.quick_note.list, 50 sorted by position, «Loading quick notes…» until the first result', async () => {
    const s = await setup();
    expect(s.params(OP)).toEqual([{ sort: 'sort_order', dir: 'asc', limit: 50, offset: 0 }]);
    expect(s.find('sale-quick-notes-loading').text()).toContain('Loading quick notes…');
    await s.show(PAGE);
    expect(s.find('sale-quick-notes-loading').exists()).toBe(false);
    expect(s.table().props()).toMatchObject({ serverSide: true, searchable: true, testid: 'sale-quick-notes', pageSize: 50, total: 3, page: 0, views: ['table', 'cards'] });
    expect([s.prop('searchPlaceholder'), s.prop('entityLabel')]).toEqual(['Search a note…', { one: 'quick note', many: 'quick notes' }]);
  });

  it('paints Note and Position, one row per note; the card is titled by its text', async () => {
    const s = await setup();
    await s.show(PAGE);
    expect(s.prop<Array<{ key: string; label: string; sortable?: boolean; align?: string }>>('columns').map((c) => [c.key, c.label, !!c.sortable, c.align ?? 'left'])).toEqual([
      ['text', 'Note', true, 'left'],
      ['sort_order', 'Position', true, 'right'],
    ]);
    expect(s.rows().map((r) => r.attributes('data-id'))).toEqual(['n1', 'n2', 'n3']);
    // The third cell holds the row actions.
    expect(s.rows()[1].findAll('[role="cell"]').map((c) => c.text().trim()).slice(0, 2)).toEqual(['medium rare', '1']);
    expect(s.prop<(row: QuickNoteOut) => string>('cardTitle')(PAGE.rows[0])).toBe('no salt');
  });

  it('sorts and searches on the server, from the first page', async () => {
    const s = await setup();
    await s.show(PAGE);
    await s.emit('sortChange', { sort: 'text', dir: 'desc' });
    expect(s.params(OP)).toEqual([{ sort: 'text', dir: 'desc', limit: 50, offset: 0 }]);
    await s.emit('update:search', '  sal ');
    expect(s.params(OP)).toEqual([{ search: 'sal', sort: 'text', dir: 'desc', limit: 50, offset: 0 }]);
  });

  it('«Load more» on a phone never asks more than 100 at once: a second window of its own', async () => {
    const s = await setup();
    await s.show({ ...PAGE, total: 230 });
    await s.emit('loadMore');
    await s.emit('loadMore');
    expect(s.params(OP).map((p) => [p.limit, p.offset])).toEqual([
      [100, 0],
      [50, 100],
    ]);
  });

  it('with no note at all, the old empty text; a search with no match says «No results»', async () => {
    const s = await setup();
    await s.show(EMPTY);
    const empty = () => s.wrapper.findComponent(EmptyState);
    expect([empty().attributes('data-testid'), empty().props('heading')]).toEqual([
      'sale-quick-notes-empty',
      'No quick notes yet. Add the ones your kitchen hears every day — “no salt”, “medium rare”, “no ice”.',
    ]);
    await s.emit('update:search', 'zzz');
    await s.show(EMPTY);
    expect([empty().props('heading'), empty().props('message')]).toEqual(['No results', 'No quick note matches your search.']);
  });

  it('a failed read is the table’s error with «Retry»', async () => {
    const s = await setup();
    s.net.lastStream().push(errorFrame(s.subId(OP), 'server_error'));
    await flush();
    expect(s.prop('error')).toBe('msg server_error');
    expect(s.prop<Record<string, string>>('labels')).toMatchObject({ loadError: 'The quick notes could not be loaded.', retry: 'Retry' });
  });

  it('the app off in this business replaces the list with «This app is not active in this business.»', async () => {
    const s = await setup();
    s.net.lastStream().push(errorFrame(s.subId(OP), 'app_inactive'));
    await flush();
    expect(s.find('sale-quick-notes-inactive').text()).toContain('This app is not active in this business.');
    expect(s.table().exists()).toBe(false);
  });

  it('while the stream recovers, «Reconnecting…» and the rows stay', async () => {
    const s = await setup();
    await s.show(PAGE);
    s.net.lastStream().push(BYE);
    await flush();
    expect(s.find('sale-quick-notes-reconnecting').text()).toBe('Reconnecting…');
    expect(s.rows()).toHaveLength(3);
  });
});

describe('QuickNotesPage: whoever may change the till settings', () => {
  it('«+» opens «New quick note»', async () => {
    const s = await setup();
    await s.show(PAGE);
    expect([s.prop('addable'), s.prop<Record<string, string>>('labels').add]).toEqual([true, 'Add']);
    await s.emit('add');
    expect([s.form().props('open'), s.form().props('note')]).toEqual([true, null]);
  });

  it('each row offers «Edit» and «Delete»; «Edit» and a tap on the row open it in the form', async () => {
    const s = await setup();
    await s.show(PAGE);
    expect(s.prop<Array<{ id: string; label: string; icon: string; color?: string }>>('actions').map((a) => [a.id, a.label, a.icon, a.color])).toEqual([
      ['edit', 'Edit', 'ion:create-outline', undefined],
      ['delete', 'Delete', 'ion:trash-outline', 'danger'],
    ]);
    expect(s.prop('rowClickable')).toBe(true);
    await s.emit('action', { actionId: 'edit', row: PAGE.rows[1] });
    expect([s.form().props('open'), s.form().props('note')]).toEqual([true, PAGE.rows[1]]);
    s.form().vm.$emit('update:open', false);
    await flush();
    await s.emit('rowClick', PAGE.rows[2]);
    expect(s.form().props('note')).toEqual(PAGE.rows[2]);
  });

  it('«Delete» asks with the old words and, confirmed, deletes it by its id', async () => {
    const s = await setup();
    await s.show(PAGE);
    mocks.confirm.mockResolvedValue(true);
    s.answer(200, PAGE.rows[0]);
    await s.emit('action', { actionId: 'delete', row: PAGE.rows[0] });
    expect(mocks.confirm).toHaveBeenCalledWith({
      title: 'Delete quick note',
      message: 'no salt — It stops being offered at the till. The notes already typed on checks and sales keep their text.',
      confirmLabel: 'Delete',
      cancelLabel: 'Cancel',
      confirmIcon: 'ion:trash-outline',
      tone: 'danger',
    });
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/sale/quick_notes/delete', query: {}, body: { id: 'n1' } }]);
  });

  it('«Delete» cancelled sends nothing', async () => {
    const s = await setup();
    await s.show(PAGE);
    mocks.confirm.mockResolvedValue(false);
    await s.emit('action', { actionId: 'delete', row: PAGE.rows[0] });
    expect(s.sent()).toEqual([]);
  });

  it('a refused delete is said on the page: «The quick note could not be deleted.» and the server’s words', async () => {
    const s = await setup();
    await s.show(PAGE);
    mocks.confirm.mockResolvedValue(true);
    s.answer(404, { error: { code: 'sale.quick_note_not_found', message: GONE } });
    await s.emit('action', { actionId: 'delete', row: PAGE.rows[0] });
    const notice = s.find('sale-quick-notes-error').text();
    expect(notice).toContain('The quick note could not be deleted.');
    expect(notice).toContain(GONE);
  });
});

describe('QuickNotesPage: anyone else', () => {
  it('sees the list without «+», row actions, row taps or form', async () => {
    const s = await setup({ session: EMPLOYEE });
    await s.show(PAGE);
    expect([s.prop('addable'), s.prop('actions'), s.prop('rowClickable')]).toEqual([false, [], false]);
    expect(s.form().exists()).toBe(false);
    expect(s.rows()).toHaveLength(3);
  });
});

describe('QuickNotesPage: Spanish', () => {
  it('speaks the old screen’s words', async () => {
    const s = await setup({ locale: 'es' });
    expect(s.find('sale-quick-notes-intro').text()).toBe(
      'Las notas que el TPV ofrece de un toque en la hoja de nota de la línea. Escribir a mano sigue funcionando.',
    );
    expect(s.find('sale-quick-notes-loading').text()).toContain('Cargando notas rápidas…');
    await s.show(EMPTY);
    expect(s.prop('searchPlaceholder')).toBe('Buscar una nota…');
    expect(s.prop<Array<{ label: string }>>('columns').map((c) => c.label)).toEqual(['Nota', 'Posición']);
    expect(s.wrapper.findComponent(EmptyState).props('heading')).toBe(
      'Todavía no hay notas rápidas. Añade las que tu cocina oye a diario: «sin sal», «poco hecho», «sin hielo».',
    );
  });
});
