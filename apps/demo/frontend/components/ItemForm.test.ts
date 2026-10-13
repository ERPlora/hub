// The item's form, shared by the «New item» and «Edit item» pages (DEMO-F01/F02): name, status and
// note in outlined md controls; a 422 paints each message under its field; any other failure goes
// to a banner with the server message; «Save» submits and is off while the command runs.
import { InlineFeedback } from '@erplora/ui/components';
import { ApiError } from '@erplora/ui/sdk';
import { IonInput, IonSelect, IonTextarea } from '@ionic/vue';
import { describe, expect, it } from 'vitest';

import { flush, mountDemo } from '../__tests__/mount-demo';
import ItemForm, { changedFields, type ItemFields } from './ItemForm.vue';

type Control = HTMLElement & { errorText?: string; value?: unknown; disabled?: boolean };

const FIELDS: ItemFields = { name: 'Table 4', status: 'open', note: 'By the window' };

async function mountForm(props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const model = { ...FIELDS };
  const m = await mountDemo(ItemForm, { props: { modelValue: model, error: null, pending: false, ...props }, locale });
  const field = (name: string) => m.wrapper.get(`[data-testid="demo-form-${name}"]`);
  return { ...m, model, field };
}

describe('ItemForm', () => {
  it('asks for name, status and note with outlined controls in md mode, filled from the model', async () => {
    const { wrapper } = await mountForm();
    for (const control of [IonInput, IonSelect, IonTextarea]) {
      const c = wrapper.findComponent(control);
      // `mode` is not a prop of Ionic Vue's proxies: it reaches the element as an attribute.
      expect([c.props('fill'), c.attributes('mode')]).toEqual(['outline', 'md']);
    }
    expect([wrapper.findComponent(IonInput).props('label'), wrapper.findComponent(IonInput).props('modelValue')]).toEqual(['Name', 'Table 4']);
    expect(wrapper.findComponent(IonInput).props('maxlength')).toBe(120);
    expect([wrapper.findComponent(IonSelect).props('label'), wrapper.findComponent(IonSelect).props('modelValue')]).toEqual(['Status', 'open']);
    // Ionic's elements take `value` as a DOM property.
    expect(wrapper.findAll('ion-select-option').map((o) => [(o.element as Control).value, o.text()])).toEqual([
      ['open', 'Open'],
      ['done', 'Done'],
    ]);
    expect([wrapper.findComponent(IonTextarea).props('label'), wrapper.findComponent(IonTextarea).props('modelValue')]).toEqual(['Note', 'By the window']);
    expect(wrapper.get('[data-testid="demo-form-save"]').text()).toBe('Save');
  });

  it('typing hands the parent a new model, field by field, and never mutates the one it got', async () => {
    // A parent's `v-model`: each new model comes back as the prop.
    const parent: { form?: Awaited<ReturnType<typeof mountForm>> } = {};
    const f = await mountForm({ 'onUpdate:modelValue': (value: ItemFields) => parent.form?.wrapper.setProps({ modelValue: value }) });
    parent.form = f;
    await f.wrapper.findComponent(IonInput).setValue('Bar');
    await f.wrapper.findComponent(IonSelect).setValue('done');
    await f.wrapper.findComponent(IonTextarea).setValue('');
    expect(f.wrapper.emitted('update:modelValue')).toEqual([
      [{ ...FIELDS, name: 'Bar' }],
      [{ ...FIELDS, name: 'Bar', status: 'done' }],
      [{ name: 'Bar', status: 'done', note: '' }],
    ]);
    expect(f.model).toEqual(FIELDS);
  });

  it('submitting emits «submit»; «Save» is off while the command runs', async () => {
    const f = await mountForm();
    await f.wrapper.get('[data-testid="demo-form"]').trigger('submit');
    expect(f.wrapper.emitted('submit')).toHaveLength(1);
    expect((f.field('save').element as Control).disabled).toBe(false);
    await f.wrapper.setProps({ pending: true });
    expect((f.field('save').element as Control).disabled).toBe(true);
  });

  it('on a 422 paints each message under its field and marks it invalid, with no banner', async () => {
    const error = new ApiError(422, 'invalid_payload', 'Invalid payload', { name: 'This field is required.' });
    const f = await mountForm({ error });
    const name = f.field('name');
    expect((name.element as Control).errorText).toBe('This field is required.');
    expect(name.classes()).toEqual(expect.arrayContaining(['ion-invalid', 'ion-touched']));
    expect(f.field('status').classes()).not.toContain('ion-invalid');
    expect(f.field('note').classes()).not.toContain('ion-invalid');
    expect(f.wrapper.findComponent(InlineFeedback).exists()).toBe(false);
  });

  it('shows any other failure in a danger banner with the server message; a new attempt clears it', async () => {
    const f = await mountForm({ error: new ApiError(403, 'permission_denied', 'You do not have permission.') });
    const banner = f.wrapper.findComponent(InlineFeedback);
    expect([banner.attributes('data-testid'), banner.props('tone'), banner.text()]).toEqual([
      'demo-form-failure',
      'danger',
      'You do not have permission.',
    ]);
    expect(f.field('name').classes()).not.toContain('ion-invalid');
    await f.wrapper.setProps({ error: null });
    await flush();
    expect(f.wrapper.findComponent(InlineFeedback).exists()).toBe(false);
  });

  it('speaks Spanish', async () => {
    const { wrapper } = await mountForm({}, 'es');
    expect(wrapper.findComponent(IonInput).props('label')).toBe('Nombre');
    expect(wrapper.findComponent(IonSelect).props('label')).toBe('Estado');
    expect(wrapper.findComponent(IonTextarea).props('label')).toBe('Nota');
    expect(wrapper.findAll('ion-select-option').map((o) => o.text())).toEqual(['Abierto', 'Hecho']);
    expect(wrapper.get('[data-testid="demo-form-save"]').text()).toBe('Guardar');
  });
});

describe('changedFields: what an edit sends (only what changed, DEMO-F02)', () => {
  it('keeps the fields whose value differs from where the form started', () => {
    expect(changedFields(FIELDS, { ...FIELDS, name: 'Bar', note: '' })).toEqual({ name: 'Bar', note: '' });
  });

  it('is empty when nothing changed', () => {
    expect(changedFields(FIELDS, { ...FIELDS })).toEqual({});
  });
});
