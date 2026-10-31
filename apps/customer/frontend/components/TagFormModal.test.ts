// «New tag» and «Edit · {name}» (CUSTOMER-F28): Name and Color; editing adds «Active». A name taken
// by another active tag is said under «Name».
import { toastSuccess } from '@erplora/ui/shell';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { defineComponent, h, ref } from 'vue';

import { approvalDialog, approvalSettled, asksApproval } from '../__tests__/approval-dialog';
import { flush, json, mountCustomer, refusal, sent } from '../__tests__/mount-customer';
import type { TagRow } from '../operations';
import TagFormModal from './TagFormModal.vue';

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

const LOYAL: TagRow = { id: 't1', name: 'Loyal', color: 'success', is_active: true, customer_count: 2 };
const TAKEN = 'There is already a tag with that name. Choose another name.';

async function setup(tag: TagRow | null = null) {
  const open = ref(true);
  const Host = defineComponent({ setup: () => () => h(TagFormModal, { open: open.value, 'onUpdate:open': (v: boolean) => (open.value = v), tag }) });
  const m = await mountCustomer(Host, { attachTo: document.body });
  await flush();
  const el = (id: string) => document.querySelector(`[data-testid="${id}"]`) as HTMLElement & { value?: unknown; disabled?: boolean; errorText?: string; checked?: boolean };
  async function type(id: string, value: string) {
    el(id).value = value;
    el(id).dispatchEvent(new CustomEvent('ionInput', { detail: { value } }));
    await flush();
  }
  const save = async () => {
    el('customer-tag-form-submit').dispatchEvent(new MouseEvent('click', { bubbles: true }));
    await flush();
  };
  return { ...m, open, el, type, save };
}

describe('TagFormModal', () => {
  it('«New tag» asks name and color, then creates it', async () => {
    const s = await setup();
    expect(document.querySelector('[data-testid="customer-tag-form"]')?.getAttribute('aria-label')).toBe('New tag');
    expect(s.el('customer-tag-form-active')).toBeNull();
    s.net.onApi(() => json(LOYAL, 201));
    await s.type('customer-tag-form-name', 'Loyal');
    await s.save();
    expect(sent(s.net.api[0])).toMatchObject({ path: '/api/customer/tags', body: { name: 'Loyal', color: 'primary' } });
    expect(toastSuccess).toHaveBeenCalledWith('Tag created');
    expect(s.open.value).toBe(false);
  });

  it('«Edit · {name}» adds «Active» and updates it', async () => {
    const s = await setup(LOYAL);
    expect(document.querySelector('[data-testid="customer-tag-form"]')?.getAttribute('aria-label')).toBe('Edit · Loyal');
    s.net.onApi(() => json(LOYAL));
    await s.save();
    expect(sent(s.net.api[0])).toMatchObject({ path: '/api/customer/tags/update', body: { id: 't1', name: 'Loyal', color: 'success', is_active: true } });
    expect(toastSuccess).toHaveBeenCalledWith('Tag updated');
  });

  it('a name already taken is said under «Name»', async () => {
    const s = await setup();
    s.net.onApi(() => refusal(409, 'customer.tag_name_taken', TAKEN, { name: TAKEN }));
    await s.type('customer-tag-form-name', 'Loyal');
    await s.save();
    expect(s.el('customer-tag-form-name').errorText).toBe(TAKEN);
  });
});

describe('TagFormModal with a manager’s approval (BASE-F84)', () => {
  it('an employee’s change goes once more with the manager’s pass', async () => {
    const s = await setup(LOYAL);
    let calls = 0;
    s.net.onApi(() => (calls++ === 0 ? Response.json(asksApproval('customer.tag.update', 'Change a customer tag'), { status: 403 }) : json(LOYAL)));
    await s.type('customer-tag-form-name', 'Loyal');
    await s.save();
    await approvalSettled();
    expect(approvalDialog.questions.map((question) => question.label)).toEqual(['Change a customer tag']);
    expect(s.net.api.map((call) => sent(call).path)).toEqual(['/api/customer/tags/update', '/api/customer/tags/update']);
    expect(toastSuccess).toHaveBeenCalledWith('Tag updated');
  });
});
