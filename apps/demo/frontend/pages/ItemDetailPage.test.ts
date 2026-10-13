// The detail of a demo item (DEMO-F02–F06): live `demo.item.detail`, a note that is never
// overwritten while it is being written, «Add line» shown at once and undone on a 409, «Mark done»
// / «Reopen», «Edit» (its own page) and «Delete» behind a confirmation.
import { InlineFeedback } from '@erplora/ui/components';
import { AppPage, toastError } from '@erplora/ui/shell';
import { IonInput, IonTextarea } from '@ionic/vue';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { AlertStub, EMPLOYEE, errorFrame, flush, type MountOptions, mountDemo, subId } from '../__tests__/mount-demo';
import ItemLines, { type ShownLine } from '../components/ItemLines.vue';
import ItemDetailPage from './ItemDetailPage.vue';
import source from './ItemDetailPage.vue?raw';

vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...((await importOriginal()) as object),
  toastError: vi.fn(() => Promise.resolve()),
}));

const LINE = { id: 'l1', text: 'Water', qty: '2.000', position: 1, client_line_id: 'c0' };
const ITEM = {
  id: 'i1',
  name: 'Table 4',
  status: 'open' as const,
  note: 'By the window',
  line_count: 1,
  updated_at: '2026-10-13T10:00:00Z',
  lines: [LINE],
};
const LIST = { rows: [{ ...ITEM, lines: undefined }, { ...ITEM, id: 'i2', name: 'Bar', line_count: 0 }], total: 2, limit: 50, offset: 0 };

type Control = HTMLElement & { errorText?: string; disabled?: boolean };

function deferred() {
  let resolve!: (res: Response) => void;
  const promise = new Promise<Response>((r) => (resolve = r));
  return { promise, resolve };
}

async function setup(options: MountOptions & { withList?: boolean } = {}) {
  const m = await mountDemo(ItemDetailPage, { props: { id: 'i1' }, path: '/demo/items/i1', ...options });
  // Another screen of the tab following the list, as the list page left in Ionic's stack would.
  const listSub = options.withList ? m.client.stream.subscribe('demo.item.list', { limit: 50, offset: 0 }, () => {}) : undefined;
  const call = await m.live();
  const show = (item: unknown, rev = 1) => m.result(call, 'demo.item.detail', item, rev);
  if (listSub) await m.result(call, 'demo.item.list', LIST);
  const testid = (id: string) => m.wrapper.find(`[data-testid="${id}"]`);
  const note = () => m.wrapper.findAllComponents(IonTextarea).find((c) => c.attributes('data-testid') === 'demo-note')!;
  const input = (id: string) => m.wrapper.findAllComponents(IonInput).find((c) => c.attributes('data-testid') === id)!;
  const lines = () => m.wrapper.findComponent(ItemLines).props('lines') as ShownLine[];
  const banner = (id: string) => m.wrapper.findAllComponents(InlineFeedback).find((c) => c.attributes('data-testid') === id)!;
  const body = (i = -1) => JSON.parse(m.net.api.at(i)!.init.body as string);
  // Ionic's elements take `disabled` as a DOM property.
  const disabled = (id: string) => (m.wrapper.get(`[data-testid="${id}"]`).element as Control).disabled;
  const click = async (id: string) => {
    await m.wrapper.get(`[data-testid="${id}"]`).trigger('click');
    await flush();
  };
  return { ...m, call, show, listSub, testid, note, input, lines, banner, body, disabled, click };
}

beforeEach(() => vi.mocked(toastError).mockClear());

describe('ItemDetailPage: the item, live', () => {
  it('follows demo.item.detail of its id, with a spinner until the first result', async () => {
    const s = await setup();
    expect(s.client.stream.subscriptions('demo.item.detail')).toEqual([{ id: expect.any(String), params: { id: 'i1' } }]);
    expect(s.testid('demo-detail-loading').exists()).toBe(true);
    await s.show(ITEM);
    expect(s.testid('demo-detail-loading').exists()).toBe(false);
    const page = s.wrapper.findComponent(AppPage);
    expect([page.props('title'), page.props('backHref')]).toEqual(['Table 4', '/demo/items']);
    expect(s.testid('demo-detail-status').text()).toBe('Open');
    expect(s.note().props('modelValue')).toBe('By the window');
    expect(s.lines()).toEqual([LINE]);
  });

  it('shows a failure of the query (e.g. deleted elsewhere) with the server message', async () => {
    const s = await setup();
    s.call.push(errorFrame(subId(s.client, 'demo.item.detail'), 'not_found'));
    await flush();
    const banner = s.banner('demo-detail-error');
    expect([banner.props('tone'), banner.props('heading')]).toEqual(['warning', 'The item could not be loaded']);
    expect(banner.text()).toContain('msg not_found');
  });

  it('says when the app is not active in this business', async () => {
    const s = await setup();
    s.call.push(errorFrame(subId(s.client, 'demo.item.detail'), 'app_inactive'));
    await flush();
    expect(s.banner('demo-detail-error').props('heading')).toBe('This app is not active in this business');
  });

  it('has no OutfitKit tag left in any state (PLAN §16.11)', () => {
    expect(source).not.toMatch(/<ok[-]/);
  });

  it('gives whoever cannot manage a read-only view: no actions, no line form, a read-only note (DEMO-F06)', async () => {
    const s = await setup({ session: EMPLOYEE });
    await s.show(ITEM);
    for (const id of ['demo-detail-edit', 'demo-detail-toggle', 'demo-detail-delete', 'demo-note-save', 'demo-line-form']) {
      expect(s.testid(id).exists(), id).toBe(false);
    }
    expect(s.note().props('readonly')).toBe(true);
  });
});

describe('ItemDetailPage: the note is never overwritten while it is being written', () => {
  it('a clean note follows every new result', async () => {
    const s = await setup();
    await s.show(ITEM);
    await s.show({ ...ITEM, note: 'Theirs' }, 2);
    expect(s.note().props('modelValue')).toBe('Theirs');
    expect(s.testid('demo-note-stale').exists()).toBe(false);
  });

  it('a new result keeps the text being written and warns «Updated elsewhere»; Reload takes the server text', async () => {
    const s = await setup();
    await s.show(ITEM);
    await s.note().setValue('Mine');
    await s.show({ ...ITEM, note: 'Theirs' }, 2);
    expect(s.note().props('modelValue')).toBe('Mine');
    const banner = s.banner('demo-note-stale');
    expect([banner.props('tone'), banner.props('heading')]).toEqual(['info', 'Updated elsewhere']);
    expect(banner.text()).toContain('Someone changed this note while you were writing it.');
    await s.click('demo-note-reload');
    expect(s.note().props('modelValue')).toBe('Theirs');
    expect(s.testid('demo-note-stale').exists()).toBe(false);
  });

  it('does not warn for results that leave the note alone, nor for the server catching up with the same text', async () => {
    const s = await setup();
    await s.show(ITEM);
    await s.note().setValue('Mine');
    await s.show({ ...ITEM, line_count: 2, lines: [LINE, { ...LINE, id: 'l2' }] }, 2);
    await s.show({ ...ITEM, note: 'Mine' }, 3);
    expect(s.note().props('modelValue')).toBe('Mine');
    expect(s.testid('demo-note-stale').exists()).toBe(false);
  });

  it('«Save note» is off while nothing changed and sends only the note', async () => {
    const s = await setup();
    await s.show(ITEM);
    expect(s.disabled('demo-note-save')).toBe(true);
    await s.note().setValue('Mine');
    expect(s.disabled('demo-note-save')).toBe(false);
    s.net.onApi(() => Response.json({ ...ITEM, note: 'Mine' }));
    await s.click('demo-note-save');
    expect(s.net.api[0].url).toBe('/api/demo/items/update');
    expect(s.body()).toEqual({ id: 'i1', note: 'Mine' });
    expect(s.disabled('demo-note-save')).toBe(true);
  });
});

describe('ItemDetailPage: «Add line» at once, undone on a 409', () => {
  async function typeLine(s: Awaited<ReturnType<typeof setup>>, text: string, qty: string) {
    await s.input('demo-line-input-text').setValue(text);
    await s.input('demo-line-input-qty').setValue(qty);
    await s.wrapper.get('[data-testid="demo-line-form"]').trigger('submit');
    await flush();
  }

  it('paints the line provisional before the server answers, counts it in the list, then takes the server line', async () => {
    const s = await setup({ withList: true });
    await s.show(ITEM);
    const reply = deferred();
    s.net.onApi(() => reply.promise);
    await typeLine(s, 'Bread', '0.5');
    const sent = s.body();
    expect(s.net.api[0].url).toBe('/api/demo/items/add_line');
    expect(sent).toEqual({ id: 'i1', text: 'Bread', qty: '0.5', client_line_id: expect.stringMatching(/^[0-9a-f-]{36}$/) });
    expect(s.lines()).toEqual([
      LINE,
      { id: sent.client_line_id, text: 'Bread', qty: '0.5', position: 2, client_line_id: sent.client_line_id, pending: true },
    ]);
    expect(s.input('demo-line-input-text').props('modelValue')).toBe('');
    const list = s.client.optimistic.view(s.listSub!.id, LIST);
    expect(list.rows.map((r) => r.line_count)).toEqual([2, 0]);
    // The server answers, and its newer result (with the saved line) replaces the provisional one.
    const saved = { id: 'l2', text: 'Bread', qty: '0.500', position: 2, client_line_id: sent.client_line_id };
    reply.resolve(Response.json({ ...ITEM, line_count: 2, lines: [LINE, saved] }));
    await flush();
    await s.show({ ...ITEM, line_count: 2, lines: [LINE, saved] }, 2);
    expect(s.lines()).toEqual([LINE, saved]);
    expect(toastError).not.toHaveBeenCalled();
  });

  it('never shows the line twice when the stream brings the saved line before the HTTP answer', async () => {
    const s = await setup();
    await s.show(ITEM);
    const reply = deferred();
    s.net.onApi(() => reply.promise);
    await typeLine(s, 'Bread', '1');
    const id = s.body().client_line_id;
    const saved = { id: 'l2', text: 'Bread', qty: '1.000', position: 2, client_line_id: id };
    await s.show({ ...ITEM, line_count: 2, lines: [LINE, saved] }, 2);
    expect(s.lines()).toEqual([LINE, saved]);
  });

  it('on a 409 (the item is done) the line goes away, a toast says why and the text comes back to retry', async () => {
    const s = await setup({ withList: true });
    await s.show(ITEM);
    const reply = deferred();
    s.net.onApi(() => reply.promise);
    await typeLine(s, 'Bread', '1');
    expect(s.lines()).toHaveLength(2);
    reply.resolve(
      Response.json({ error: { code: 'demo.item_done', message: 'This item is closed: open it to add lines.' } }, { status: 409 }),
    );
    await flush();
    expect(s.lines()).toEqual([LINE]);
    expect(s.client.optimistic.view(s.listSub!.id, LIST)).toEqual(LIST);
    expect(toastError).toHaveBeenCalledExactlyOnceWith('This item is closed: open it to add lines.');
    expect(s.input('demo-line-input-text').props('modelValue')).toBe('Bread');
  });

  it('on a 422 the message goes under its field, with no toast', async () => {
    const s = await setup();
    await s.show(ITEM);
    s.net.onApi(() =>
      Response.json(
        { error: { code: 'invalid_payload', message: 'Invalid payload', fields: { qty: 'Ensure this value is greater than 0.' } } },
        { status: 422 },
      ),
    );
    await typeLine(s, 'Bread', '0');
    const qty = s.wrapper.get('[data-testid="demo-line-input-qty"]');
    expect((qty.element as Control).errorText).toBe('Ensure this value is greater than 0.');
    expect(qty.classes()).toEqual(expect.arrayContaining(['ion-invalid', 'ion-touched']));
    expect(s.lines()).toEqual([LINE]);
    expect(toastError).not.toHaveBeenCalled();
  });

  it('cannot add a line without text', async () => {
    const s = await setup();
    await s.show(ITEM);
    expect(s.disabled('demo-line-add')).toBe(true);
    await s.input('demo-line-input-text').setValue('Bread');
    expect(s.disabled('demo-line-add')).toBe(false);
  });
});

describe('ItemDetailPage: edit, status and delete', () => {
  it('«Edit» opens the edit page of this item', async () => {
    const s = await setup();
    await s.show(ITEM);
    expect(s.testid('demo-detail-edit').text()).toBe('Edit');
    await s.click('demo-detail-edit');
    expect(s.router.currentRoute.value.path).toBe('/demo/items/i1/edit');
  });

  it('«Mark done» closes an open item and «Reopen» opens a done one', async () => {
    const s = await setup();
    await s.show(ITEM);
    s.net.onApi(() => Response.json(ITEM));
    expect(s.testid('demo-detail-toggle').text()).toBe('Mark done');
    await s.click('demo-detail-toggle');
    expect([s.net.api[0].url, s.body()]).toEqual(['/api/demo/items/update', { id: 'i1', status: 'done' }]);
    await s.show({ ...ITEM, status: 'done' }, 2);
    expect(s.testid('demo-detail-toggle').text()).toBe('Reopen');
    expect(s.testid('demo-detail-status').text()).toBe('Done');
    await s.click('demo-detail-toggle');
    expect(s.body()).toEqual({ id: 'i1', status: 'open' });
  });

  it('a failed command says why in a toast', async () => {
    const s = await setup();
    await s.show(ITEM);
    s.net.onApi(() => Response.json({ error: { code: 'permission_denied', message: 'You do not have permission.' } }, { status: 403 }));
    await s.click('demo-detail-toggle');
    expect(toastError).toHaveBeenCalledExactlyOnceWith('You do not have permission.');
  });

  it('«Delete» asks first; cancelling deletes nothing', async () => {
    const s = await setup();
    await s.show(ITEM);
    const alert = s.wrapper.findComponent(AlertStub);
    expect(alert.props('isOpen')).toBe(false);
    await s.click('demo-detail-delete');
    expect(alert.props('isOpen')).toBe(true);
    expect(alert.props('header')).toBe('Delete this item and its lines?');
    expect((alert.props('buttons') as Array<{ text: string; role: string }>).map((b) => [b.text, b.role])).toEqual([
      ['Cancel', 'cancel'],
      ['Delete', 'destructive'],
    ]);
    alert.vm.$emit('didDismiss', new CustomEvent('didDismiss', { detail: { role: 'cancel' } }));
    await flush();
    expect(alert.props('isOpen')).toBe(false);
    expect(s.net.api).toHaveLength(0);
  });

  it('confirming deletes the item and goes back to the list', async () => {
    const s = await setup();
    await s.show(ITEM);
    s.net.onApi(() => Response.json({ id: 'i1' }));
    await s.click('demo-detail-delete');
    s.wrapper.findComponent(AlertStub).vm.$emit('didDismiss', new CustomEvent('didDismiss', { detail: { role: 'destructive' } }));
    await flush();
    expect([s.net.api[0].url, s.body()]).toEqual(['/api/demo/items/delete', { id: 'i1' }]);
    expect(s.router.currentRoute.value.path).toBe('/demo/items');
  });
});
