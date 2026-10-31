// «New custom field» and «Edit · {name}» (CUSTOMER-F29): Name, Type (Text, Number, Date, Yes/No,
// Select, Long text), the Options of a select (comma-separated), Order and Required; editing adds
// «Active». The server's refusals go under their field: a name taken, a select without options, a
// type that cannot change once cards have values.
import { toastSuccess } from '@erplora/ui/shell';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { defineComponent, h, ref } from 'vue';

import { approvalDialog, approvalSettled, asksApproval } from '../__tests__/approval-dialog';
import { flush, json, mountCustomer, refusal, sent } from '../__tests__/mount-customer';
import type { FieldRow } from '../operations';
import FieldFormModal from './FieldFormModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  const { modalControllerStub } = await import('../__tests__/approval-dialog');
  const ionic = await importOriginal<typeof import('@ionic/vue')>();
  return { ...ionic, IonModal: IonModalStub, modalController: modalControllerStub(ionic.modalController) };
});
vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...((await importOriginal()) as object),
  toastSuccess: vi.fn(() => Promise.resolve()),
}));
beforeEach(() => {
  vi.mocked(toastSuccess).mockClear();
  approvalDialog.reset();
});
afterEach(() => {
  document.body.innerHTML = '';
});

const DYE: FieldRow = { id: 'f1', name: 'Dye', field_type: 'select', options: ['Blonde', 'Brown'], is_required: true, sort_order: 3, is_active: true };

async function setup(field: FieldRow | null = null) {
  const open = ref(true);
  const Host = defineComponent({ setup: () => () => h(FieldFormModal, { open: open.value, 'onUpdate:open': (v: boolean) => (open.value = v), field }) });
  const m = await mountCustomer(Host, { attachTo: document.body });
  await flush();
  const el = (id: string) =>
    document.querySelector(`[data-testid="${id}"]`) as HTMLElement & { value?: unknown; disabled?: boolean; errorText?: string; checked?: boolean };
  async function type(id: string, value: string) {
    el(id).value = value;
    el(id).dispatchEvent(new CustomEvent('ionInput', { detail: { value } }));
    await flush();
  }
  /** As Ionic does: the select takes the value, then says so. */
  async function choose(id: string, value: string) {
    el(id).value = value;
    el(id).dispatchEvent(new CustomEvent('ionChange', { detail: { value } }));
    await flush();
  }
  const save = async () => {
    el('customer-field-form-submit').dispatchEvent(new MouseEvent('click', { bubbles: true }));
    await flush();
  };
  return { ...m, open, el, type, choose, save };
}

describe('FieldFormModal', () => {
  it('«New custom field»: name, type (Text first) and order; the options only for a select', async () => {
    const s = await setup();
    expect(document.querySelector('[data-testid="customer-field-form"]')?.getAttribute('aria-label')).toBe('New custom field');
    expect([...s.el('customer-field-form-type').querySelectorAll('ion-select-option')].map((o) => o.textContent?.trim())).toEqual([
      'Text',
      'Number',
      'Date',
      'Yes/No',
      'Select',
      'Long text',
    ]);
    expect(s.el('customer-field-form-options')).toBeNull();
    await s.choose('customer-field-form-type', 'select');
    expect(s.el('customer-field-form-options')).not.toBeNull();
    expect(s.el('customer-field-form-active')).toBeNull();
  });

  it('creates a select with its options and «Required», says «Field created»', async () => {
    const s = await setup();
    s.net.onApi(() => json(DYE, 201));
    await s.type('customer-field-form-name', 'Dye');
    await s.choose('customer-field-form-type', 'select');
    await s.type('customer-field-form-options', 'Blonde, Brown , ,Red');
    s.el('customer-field-form-required').dispatchEvent(new CustomEvent('ionChange', { detail: { checked: true } }));
    await flush();
    await s.save();
    expect(sent(s.net.api[0])).toMatchObject({
      path: '/api/customer/fields',
      body: { name: 'Dye', field_type: 'select', options: ['Blonde', 'Brown', 'Red'], is_required: true, sort_order: 0 },
    });
    expect(toastSuccess).toHaveBeenCalledWith('Field created');
  });

  it('«Edit · {name}» starts from the field (options as a list), adds «Active» and updates it', async () => {
    const s = await setup(DYE);
    expect(document.querySelector('[data-testid="customer-field-form"]')?.getAttribute('aria-label')).toBe('Edit · Dye');
    expect(s.el('customer-field-form-options').value).toBe('Blonde, Brown');
    expect([s.el('customer-field-form-required').checked, s.el('customer-field-form-active').checked]).toEqual([true, true]);
    s.net.onApi(() => json(DYE));
    await s.save();
    expect(sent(s.net.api[0])).toMatchObject({ path: '/api/customer/fields/update', body: { id: 'f1', field_type: 'select', is_active: true } });
    expect(toastSuccess).toHaveBeenCalledWith('Field updated');
  });

  it('the server\'s refusals go under their field', async () => {
    const s = await setup(DYE);
    const HAS_VALUES = 'This field already has values on some cards: its type cannot change.';
    s.net.onApi(() => refusal(409, 'customer.field_has_values', HAS_VALUES, { field_type: HAS_VALUES }));
    await s.choose('customer-field-form-type', 'text');
    await s.save();
    expect(s.el('customer-field-form-type').errorText).toBe(HAS_VALUES);
    expect(s.open.value).toBe(true);
  });
});

describe('FieldFormModal with a manager’s approval (BASE-F84)', () => {
  it('an employee’s field goes once more with the manager’s pass, and is created', async () => {
    const s = await setup();
    let calls = 0;
    s.net.onApi(() => (calls++ === 0 ? Response.json(asksApproval('customer.field.create', 'Create a custom field'), { status: 403 }) : json(DYE, 201)));
    await s.type('customer-field-form-name', 'Dye');
    await s.save();
    await approvalSettled();
    expect(approvalDialog.questions.map((question) => question.label)).toEqual(['Create a custom field']);
    expect(s.net.api.map((call) => sent(call).path)).toEqual(['/api/customer/fields', '/api/customer/fields']);
    expect(toastSuccess).toHaveBeenCalledWith('Field created');
  });
});
