// «New group» and «Edit · {name}» (CUSTOMER-F27): Name (required), Description, Color and Order;
// editing adds «Active». Saved: «Group created» / «Group updated» and the dialog closes. A name taken
// by another active group is said under «Name».
import { toastSuccess } from '@erplora/ui/shell';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { defineComponent, h, ref } from 'vue';

import { flush, json, mountCustomer, refusal, sent } from '../__tests__/mount-customer';
import type { GroupRow } from '../operations';
import GroupFormModal from './GroupFormModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});
vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...((await importOriginal()) as object),
  toastSuccess: vi.fn(() => Promise.resolve()),
}));
beforeEach(() => vi.mocked(toastSuccess).mockClear());
afterEach(() => {
  document.body.innerHTML = '';
});

const VIP: GroupRow = { id: 'g1', name: 'VIP', description: 'Best', color: 'warning', sort_order: 2, is_active: true, customer_count: 3 };
const TAKEN = 'There is already a group with that name. Choose another name.';

async function setup(group: GroupRow | null = null, locale: 'en' | 'es' = 'en') {
  const open = ref(true);
  const Host = defineComponent({
    setup: () => () => h(GroupFormModal, { open: open.value, 'onUpdate:open': (v: boolean) => (open.value = v), group }),
  });
  const m = await mountCustomer(Host, { attachTo: document.body, locale });
  await flush();
  const el = <T = HTMLElement & { value?: unknown; disabled?: boolean; errorText?: string; checked?: boolean }>(id: string) =>
    document.querySelector(`[data-testid="${id}"]`) as T;
  async function type(id: string, value: string) {
    const input = el(id);
    input.value = value;
    input.dispatchEvent(new CustomEvent('ionInput', { detail: { value } }));
    await flush();
  }
  async function save() {
    el('customer-group-form-submit').dispatchEvent(new MouseEvent('click', { bubbles: true }));
    await flush();
  }
  return { ...m, open, el, type, save };
}

describe('GroupFormModal', () => {
  it('«New group»: name, description, color and order; no «Active»; «Save» waits for a name', async () => {
    const s = await setup();
    expect(document.querySelector('[data-testid="customer-group-form"]')?.getAttribute('aria-label')).toBe('New group');
    for (const id of ['name', 'description', 'color', 'order']) expect(s.el(`customer-group-form-${id}`), id).not.toBeNull();
    expect(s.el('customer-group-form-active')).toBeNull();
    expect(s.el('customer-group-form-color').value).toBe('primary');
    expect(s.el('customer-group-form-submit').disabled).toBe(true);
  });

  it('creates it, says «Group created» and closes', async () => {
    const s = await setup();
    s.net.onApi(() => json(VIP, 201));
    await s.type('customer-group-form-name', ' VIP ');
    await s.type('customer-group-form-order', '2');
    await s.save();
    expect(sent(s.net.api[0])).toMatchObject({
      path: '/api/customer/groups',
      body: { name: 'VIP', description: '', color: 'primary', sort_order: 2 },
    });
    expect(toastSuccess).toHaveBeenCalledWith('Group created');
    expect(s.open.value).toBe(false);
  });

  it('«Edit · {name}» starts from the group, adds «Active», and updates it', async () => {
    const s = await setup(VIP);
    expect(document.querySelector('[data-testid="customer-group-form"]')?.getAttribute('aria-label')).toBe('Edit · VIP');
    expect([s.el('customer-group-form-name').value, s.el('customer-group-form-color').value]).toEqual(['VIP', 'warning']);
    expect(s.el('customer-group-form-active').checked).toBe(true);
    s.net.onApi(() => json({ ...VIP, is_active: false }));
    s.el('customer-group-form-active').dispatchEvent(new CustomEvent('ionChange', { detail: { checked: false } }));
    await flush();
    await s.save();
    expect(sent(s.net.api[0])).toMatchObject({ path: '/api/customer/groups/update', body: { id: 'g1', is_active: false } });
    expect(toastSuccess).toHaveBeenCalledWith('Group updated');
  });

  it('a name already taken is said under «Name»; the dialog stays open', async () => {
    const s = await setup();
    s.net.onApi(() => refusal(409, 'customer.group_name_taken', TAKEN, { name: TAKEN }));
    await s.type('customer-group-form-name', 'VIP');
    await s.save();
    expect(s.el('customer-group-form-name').errorText).toBe(TAKEN);
    expect(s.el('customer-group-form-error')).toBeNull();
    expect(s.open.value).toBe(true);
  });

  it('speaks Spanish', async () => {
    await setup(VIP, 'es');
    expect(document.querySelector('[data-testid="customer-group-form"]')?.getAttribute('aria-label')).toBe('Editar · VIP');
  });
});
