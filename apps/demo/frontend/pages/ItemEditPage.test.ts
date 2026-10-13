// «Edit item» as its own page (DEMO-F02): loads the item live, fills the form once (later results
// never overwrite what is being edited), Save sends only what changed and goes back to the detail;
// a 422 stays with each message under its field; a deleted item says so.
import { InlineFeedback } from '@erplora/ui/components';
import { AppPage } from '@erplora/ui/shell';
import { IonInput, IonTextarea } from '@ionic/vue';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { EMPLOYEE, errorFrame, flush, type MountOptions, mountDemo, subId } from '../__tests__/mount-demo';
import ItemForm from '../components/ItemForm.vue';
import ItemEditPage from './ItemEditPage.vue';

type Control = HTMLElement & { errorText?: string };

const ITEM = {
  id: 'i1',
  name: 'Table 4',
  status: 'open' as const,
  note: 'By the window',
  line_count: 0,
  updated_at: '2026-10-13T10:00:00Z',
  lines: [],
};

async function setup(options: MountOptions = {}) {
  const m = await mountDemo(ItemEditPage, { props: { id: 'i1' }, path: '/demo/items/i1/edit', ...options });
  const call = await m.live();
  const show = (item: unknown, rev = 1) => m.result(call, 'demo.item.detail', item, rev);
  const testid = (id: string) => m.wrapper.find(`[data-testid="${id}"]`);
  const form = () => m.wrapper.findComponent(ItemForm);
  async function save() {
    await m.wrapper.get('[data-testid="demo-form"]').trigger('submit');
    await flush();
  }
  const body = () => JSON.parse(m.net.api.at(-1)!.init.body as string);
  return { ...m, call, show, testid, form, save, body };
}

afterEach(() => {
  window.history.replaceState(null, '');
});

describe('ItemEditPage', () => {
  it('follows demo.item.detail of its id, with a spinner and no form until the first result', async () => {
    const s = await setup();
    expect(s.client.stream.subscriptions('demo.item.detail')).toEqual([{ id: expect.any(String), params: { id: 'i1' } }]);
    expect(s.testid('demo-edit-loading').exists()).toBe(true);
    expect(s.form().exists()).toBe(false);
    await s.show(ITEM);
    expect(s.testid('demo-edit-loading').exists()).toBe(false);
    const page = s.wrapper.findComponent(AppPage);
    expect([page.props('title'), page.props('backHref')]).toEqual(['Edit item', '/demo/items/i1']);
    expect(s.form().props('modelValue')).toEqual({ name: 'Table 4', status: 'open', note: 'By the window' });
  });

  it('a later result never overwrites what is being edited', async () => {
    const s = await setup();
    await s.show(ITEM);
    await s.wrapper.findComponent(IonInput).setValue('Mine');
    await s.show({ ...ITEM, name: 'Theirs', note: 'Theirs too' }, 2);
    expect(s.form().props('modelValue')).toEqual({ name: 'Mine', status: 'open', note: 'By the window' });
  });

  it('sends only what changed, then goes back to the detail', async () => {
    const s = await setup();
    await s.show(ITEM);
    window.history.replaceState({ back: '/demo/items/i1' }, '');
    const back = vi.spyOn(s.router, 'back');
    s.net.onApi(() => Response.json({ ...ITEM, note: '' }));
    await s.wrapper.findComponent(IonTextarea).setValue('');
    await s.save();
    expect([s.net.api[0].url, s.net.api[0].init.method]).toEqual(['/api/demo/items/update', 'POST']);
    expect(s.body()).toEqual({ id: 'i1', note: '' });
    expect(back).toHaveBeenCalledOnce();
  });

  it('opened by a direct link, after saving goes to the detail', async () => {
    const s = await setup();
    await s.show(ITEM);
    s.net.onApi(() => Response.json({ ...ITEM, name: 'Bar' }));
    await s.wrapper.findComponent(IonInput).setValue('Bar');
    await s.save();
    expect(s.body()).toEqual({ id: 'i1', name: 'Bar' });
    expect(s.router.currentRoute.value.path).toBe('/demo/items/i1');
  });

  it('on a 422 stays on the page with the message under its field', async () => {
    const s = await setup();
    await s.show(ITEM);
    s.net.onApi(() =>
      Response.json(
        { error: { code: 'invalid_payload', message: 'Invalid payload', fields: { name: 'This field is required.' } } },
        { status: 422 },
      ),
    );
    await s.wrapper.findComponent(IonInput).setValue(' ');
    await s.save();
    const name = s.wrapper.get('[data-testid="demo-form-name"]');
    expect((name.element as Control).errorText).toBe('This field is required.');
    expect(s.router.currentRoute.value.path).toBe('/demo/items/i1/edit');
  });

  it('when the item no longer exists says so with the server message, and shows no form', async () => {
    const s = await setup();
    s.call.push(errorFrame(subId(s.client, 'demo.item.detail'), 'not_found'));
    await flush();
    const banner = s.wrapper.findComponent(InlineFeedback);
    expect([banner.attributes('data-testid'), banner.props('tone'), banner.props('heading')]).toEqual([
      'demo-edit-error',
      'warning',
      'The item could not be loaded',
    ]);
    expect(banner.text()).toContain('msg not_found');
    expect(s.form().exists()).toBe(false);
    expect(s.testid('demo-edit-loading').exists()).toBe(false);
  });

  it('whoever cannot manage gets «No permission» instead of the form (DEMO-F06)', async () => {
    const s = await setup({ session: EMPLOYEE });
    await s.show(ITEM);
    expect(s.form().exists()).toBe(false);
    expect(s.wrapper.findComponent(InlineFeedback).attributes('data-testid')).toBe('demo-form-forbidden');
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    expect(s.wrapper.findComponent(AppPage).props('title')).toBe('Editar elemento');
  });
});
