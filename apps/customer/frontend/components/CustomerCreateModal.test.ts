// «Add» on the customer list (CUSTOMER-F01): the card's form in a dialog (the product's side panel
// of the table). Only the name is required: «Save» waits for it. Saved, the dialog closes and the
// live list paints the card by itself; refused, the dialog stays open with what was typed and the
// reason under its field (a phone that is not one of its country: F11).
import { toastSuccess } from '@erplora/ui/shell';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { defineComponent, h, ref } from 'vue';

import { flush, json, mountCustomer, refusal, sent } from '../__tests__/mount-customer';
import CustomerCreateModal from './CustomerCreateModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});
vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...((await importOriginal()) as object),
  toastSuccess: vi.fn(() => Promise.resolve()),
}));

const PHONE_INVALID =
  'Not a valid phone of its country: check the digits or write it with its international prefix (+44…).';

async function setup(locale: 'en' | 'es' = 'en') {
  const open = ref(true);
  const created: unknown[] = [];
  const Host = defineComponent({
    setup: () => () =>
      h(CustomerCreateModal, {
        open: open.value,
        'onUpdate:open': (v: boolean) => (open.value = v),
        onCreated: (c: unknown) => created.push(c),
      }),
  });
  const m = await mountCustomer(Host, { locale, attachTo: document.body });
  await flush();
  const el = (id: string) => document.querySelector<HTMLElement & { value?: string; disabled?: boolean }>(`[data-testid="${id}"]`);
  async function type(id: string, value: string) {
    const input = el(id)!;
    input.value = value;
    input.dispatchEvent(new CustomEvent('ionInput', { detail: { value } }));
    await flush();
  }
  async function save() {
    el('customer-create-submit')!.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    await flush();
  }
  return { ...m, open, created, el, type, save };
}

beforeEach(() => vi.mocked(toastSuccess).mockClear());
afterEach(() => {
  document.body.innerHTML = '';
});

describe('CustomerCreateModal', () => {
  it('opens «New customer» with the card form; «Save» waits for a name', async () => {
    const s = await setup();
    expect(document.querySelector('[data-testid="customer-create"]')?.getAttribute('aria-label')).toBe('New customer');
    expect(s.el('customer-form-name')).not.toBeNull();
    expect(s.el('customer-form-more')).not.toBeNull();
    expect(s.el('customer-create-submit')!.disabled).toBe(true);
    await s.type('customer-form-name', 'Ana');
    expect(s.el('customer-create-submit')!.disabled).toBe(false);
    await s.type('customer-form-name', '   ');
    expect(s.el('customer-create-submit')!.disabled).toBe(true);
  });

  it('saves the whole card in one call; then closes, says so and hands the card up', async () => {
    const s = await setup();
    s.net.onApi(() => json({ id: 'c9', name: 'Ana' }, 201));
    await s.type('customer-form-name', 'Ana');
    await s.type('customer-form-phone', '600 111 222');
    await s.save();
    expect(s.net.api).toHaveLength(1);
    const call = sent(s.net.api[0]);
    expect([s.net.api[0].init.method, call.path]).toEqual(['POST', '/api/customer/customers']);
    expect(call.body).toMatchObject({ name: 'Ana', phone: '600 111 222', source: 'walk_in', lifecycle_stage: 'lead', birthday: null });
    expect(s.open.value).toBe(false);
    expect(s.created).toEqual([{ id: 'c9', name: 'Ana' }]);
    expect(toastSuccess).toHaveBeenCalledWith('Customer Ana created');
  });

  it('a phone that is not one of its country stays under «Phone», with what was typed, and the dialog open', async () => {
    const s = await setup();
    s.net.onApi(() => refusal(422, 'customer.phone_invalid', PHONE_INVALID, { phone: PHONE_INVALID }));
    await s.type('customer-form-name', 'Ana');
    await s.type('customer-form-phone', '600111');
    await s.save();
    expect(s.open.value).toBe(true);
    const phone = s.el('customer-form-phone') as HTMLElement & { errorText?: string; value?: string };
    expect(phone.errorText).toBe(PHONE_INVALID);
    expect(phone.classList.contains('ion-invalid')).toBe(true);
    expect(phone.value).toBe('600111');
    expect(s.el('customer-create-error')).toBeNull();
    expect(s.created).toEqual([]);
  });

  it('a refusal that names no field shown is told on top of the form', async () => {
    const s = await setup();
    s.net.onApi(() => refusal(403, 'permission_denied', 'You do not have permission to do that.'));
    await s.type('customer-form-name', 'Ana');
    await s.save();
    expect(s.el('customer-create-error')?.textContent).toContain('You do not have permission to do that.');
    expect(s.open.value).toBe(true);
  });

  it('starts empty again the next time it opens', async () => {
    const s = await setup();
    s.net.onApi(() => json({ id: 'c9', name: 'Ana' }, 201));
    await s.type('customer-form-name', 'Ana');
    await s.save();
    s.open.value = true;
    await flush();
    expect(s.el('customer-form-name')!.value).toBe('');
  });

  it('speaks Spanish', async () => {
    await setup('es');
    expect(document.querySelector('[data-testid="customer-create"]')?.getAttribute('aria-label')).toBe('Nuevo cliente');
    expect(document.querySelector('[data-testid="customer-create-submit"]')?.textContent?.trim()).toBe('Guardar');
  });
});
