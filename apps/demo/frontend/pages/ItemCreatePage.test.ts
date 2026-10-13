// «New item» as its own page (DEMO-F01): the item's form inside AppPage with Back to the list; Save
// creates the item and goes back where the person came from (the live list paints the new row by
// itself); a 422 stays on the page with each message under its field.
import { InlineFeedback } from '@erplora/ui/components';
import { AppPage } from '@erplora/ui/shell';
import { IonInput, IonSelect, IonTextarea } from '@ionic/vue';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { EMPLOYEE, flush, type MountOptions, mountDemo } from '../__tests__/mount-demo';
import ItemForm from '../components/ItemForm.vue';
import ItemCreatePage from './ItemCreatePage.vue';

type Control = HTMLElement & { errorText?: string };

async function setup(options: MountOptions = {}) {
  const m = await mountDemo(ItemCreatePage, { path: '/demo/items/new', ...options });
  const field = (name: string) => m.wrapper.get(`[data-testid="demo-form-${name}"]`);
  async function fill(values: { name?: string; status?: string; note?: string }) {
    if (values.name !== undefined) await m.wrapper.findComponent(IonInput).setValue(values.name);
    if (values.status !== undefined) await m.wrapper.findComponent(IonSelect).setValue(values.status);
    if (values.note !== undefined) await m.wrapper.findComponent(IonTextarea).setValue(values.note);
  }
  async function save() {
    await m.wrapper.get('[data-testid="demo-form"]').trigger('submit');
    await flush();
  }
  const body = () => JSON.parse(m.net.api.at(-1)!.init.body as string);
  return { ...m, field, fill, save, body };
}

afterEach(() => {
  window.history.replaceState(null, '');
});

describe('ItemCreatePage', () => {
  it('is a page titled «New item» with Back to the list, and an empty form (status open)', async () => {
    const s = await setup();
    const page = s.wrapper.findComponent(AppPage);
    expect([page.props('title'), page.props('backHref')]).toEqual(['New item', '/demo/items']);
    expect(s.wrapper.findComponent(ItemForm).props('modelValue')).toEqual({ name: '', status: 'open', note: '' });
    expect(s.net.api).toHaveLength(0);
  });

  it('creates the item with what was typed', async () => {
    const s = await setup();
    s.net.onApi(() => Response.json({ id: 'i9' }, { status: 201 }));
    await s.fill({ name: 'Table 4', status: 'done', note: 'By the window' });
    await s.save();
    expect(s.net.api).toHaveLength(1);
    expect([s.net.api[0].url, s.net.api[0].init.method]).toEqual(['/api/demo/items', 'POST']);
    expect(s.body()).toEqual({ name: 'Table 4', status: 'done', note: 'By the window' });
  });

  it('after saving goes back where the person came from, with a clean form', async () => {
    const s = await setup();
    // vue-router's web history keeps the previous screen in `history.state.back`.
    window.history.replaceState({ back: '/demo/items' }, '');
    const back = vi.spyOn(s.router, 'back');
    s.net.onApi(() => Response.json({ id: 'i9' }, { status: 201 }));
    await s.fill({ name: 'Table 4' });
    await s.save();
    expect(back).toHaveBeenCalledOnce();
    expect(s.wrapper.findComponent(ItemForm).props('modelValue')).toEqual({ name: '', status: 'open', note: '' });
  });

  it('opened by a direct link, after saving goes to the list', async () => {
    const s = await setup();
    s.net.onApi(() => Response.json({ id: 'i9' }, { status: 201 }));
    await s.fill({ name: 'Table 4' });
    await s.save();
    expect(s.router.currentRoute.value.path).toBe('/demo/items');
  });

  it('on a 422 stays on the page with the message under its field', async () => {
    const s = await setup();
    s.net.onApi(() =>
      Response.json(
        { error: { code: 'invalid_payload', message: 'Invalid payload', fields: { name: 'This field is required.' } } },
        { status: 422 },
      ),
    );
    await s.save();
    expect((s.field('name').element as Control).errorText).toBe('This field is required.');
    expect(s.field('name').classes()).toEqual(expect.arrayContaining(['ion-invalid', 'ion-touched']));
    expect(s.router.currentRoute.value.path).toBe('/demo/items/new');
  });

  it('any other failure shows its message and stays', async () => {
    const s = await setup();
    s.net.onApi(() => Response.json({ error: { code: 'permission_denied', message: 'You do not have permission.' } }, { status: 403 }));
    await s.fill({ name: 'Table 4' });
    await s.save();
    expect(s.wrapper.findComponent(InlineFeedback).text()).toBe('You do not have permission.');
    expect(s.router.currentRoute.value.path).toBe('/demo/items/new');
  });

  it('whoever cannot manage gets «No permission» instead of the form (DEMO-F06)', async () => {
    const s = await setup({ session: EMPLOYEE });
    expect(s.wrapper.findComponent(ItemForm).exists()).toBe(false);
    const banner = s.wrapper.findComponent(InlineFeedback);
    expect([banner.attributes('data-testid'), banner.props('tone'), banner.text()]).toEqual([
      'demo-form-forbidden',
      'warning',
      'You do not have permission',
    ]);
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    expect(s.wrapper.findComponent(AppPage).props('title')).toBe('Nuevo elemento');
  });
});
