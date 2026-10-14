// «Delete» of a card (CUSTOMER-F07), from the list or the card: a dialog asks «Delete customer» —
// «Delete {name}? …» with Cancel and Delete; confirmed, the card is deleted (its data kept) and
// «Customer {name} deleted» is said. A refusal stays in the dialog.
import { toastSuccess } from '@erplora/ui/shell';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { defineComponent, h, ref } from 'vue';

import { flush, json, mountCustomer, refusal, sent } from '../__tests__/mount-customer';
import CustomerDeleteDialog from './CustomerDeleteDialog.vue';

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

async function setup(locale: 'en' | 'es' = 'en') {
  const target = ref<{ id: string; name: string } | null>({ id: 'c1', name: 'Ana García' });
  const deleted: string[] = [];
  const Host = defineComponent({
    setup: () => () =>
      h(CustomerDeleteDialog, {
        customer: target.value,
        'onUpdate:customer': (v: { id: string; name: string } | null) => (target.value = v),
        onDeleted: (id: string) => deleted.push(id),
      }),
  });
  const m = await mountCustomer(Host, { locale, attachTo: document.body });
  await flush();
  const el = (id: string) => document.querySelector<HTMLElement>(`[data-testid="${id}"]`);
  return { ...m, target, deleted, el };
}

describe('CustomerDeleteDialog', () => {
  it('asks «Delete customer» with what it means, Cancel and Delete', async () => {
    const s = await setup();
    const dialog = s.el('customer-delete-confirm')!;
    expect(dialog.getAttribute('aria-label')).toBe('Delete customer');
    expect(dialog.getAttribute('role')).toBe('alertdialog');
    expect(dialog.textContent).toContain(
      'Delete Ana García? They no longer show in the list, at the till or in the search by phone. Their sales are kept.',
    );
    expect(s.el('customer-delete-confirm-submit')!.textContent?.trim()).toBe('Delete');
  });

  it('Cancel deletes nothing', async () => {
    const s = await setup();
    s.el('customer-delete-confirm-cancel')!.click();
    await flush();
    expect(s.net.api).toHaveLength(0);
    expect(s.target.value).toBeNull();
  });

  it('Delete deletes the card, closes, says so and tells the parent', async () => {
    const s = await setup();
    s.net.onApi(() => json({ id: 'c1' }));
    s.el('customer-delete-confirm-submit')!.click();
    await flush();
    expect(sent(s.net.api[0])).toMatchObject({ path: '/api/customer/customers/delete', body: { id: 'c1' } });
    expect(s.target.value).toBeNull();
    expect(s.deleted).toEqual(['c1']);
    expect(toastSuccess).toHaveBeenCalledWith('Customer Ana García deleted');
  });

  it('a refusal stays in the dialog with its message', async () => {
    const s = await setup();
    s.net.onApi(() => refusal(404, 'customer.customer_unavailable', 'This customer is no longer available.'));
    s.el('customer-delete-confirm-submit')!.click();
    await flush();
    expect(s.el('customer-delete-confirm-error')?.textContent).toContain('This customer is no longer available.');
    expect(s.target.value).not.toBeNull();
  });

  it('speaks Spanish', async () => {
    const s = await setup('es');
    expect(s.el('customer-delete-confirm')!.getAttribute('aria-label')).toBe('Eliminar cliente');
    expect(s.el('customer-delete-confirm')!.textContent).toContain('¿Eliminar Ana García?');
  });
});
