// «Delete» of a group, a tag or a custom field (CUSTOMER-F27–F29): the dialog asks with the
// consequence («The customers who have it lose it.», «The values saved on the cards are deleted
// too.»); confirmed, it deletes and says «Group {name} deleted». A refusal stays in the dialog.
import { toastSuccess } from '@erplora/ui/shell';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { defineComponent, h, ref } from 'vue';

import { flush, json, mountCustomer, refusal, sent } from '../__tests__/mount-customer';
import EntityDeleteDialog from './EntityDeleteDialog.vue';

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

async function setup(kind: 'groups' | 'tags' | 'fields') {
  const target = ref<{ id: string; name: string } | null>({ id: 'x1', name: 'VIP' });
  const Host = defineComponent({
    setup: () => () =>
      h(EntityDeleteDialog, { kind, target: target.value, 'onUpdate:target': (v: { id: string; name: string } | null) => (target.value = v) }),
  });
  const m = await mountCustomer(Host, { attachTo: document.body });
  await flush();
  const el = (id: string) => document.querySelector<HTMLElement>(`[data-testid="${id}"]`);
  return { ...m, target, el };
}

describe('EntityDeleteDialog', () => {
  it('asks with the consequence; Delete deletes the group and says so', async () => {
    const s = await setup('groups');
    const dialog = s.el('customer-groups-delete')!;
    expect(dialog.getAttribute('aria-label')).toBe('Delete group');
    expect(dialog.textContent).toContain('Delete VIP? The customers who have it lose it.');
    s.net.onApi(() => json({ id: 'x1' }));
    s.el('customer-groups-delete-submit')!.click();
    await flush();
    expect(sent(s.net.api[0])).toMatchObject({ path: '/api/customer/groups/delete', body: { id: 'x1' } });
    expect(toastSuccess).toHaveBeenCalledWith('Group VIP deleted');
    expect(s.target.value).toBeNull();
  });

  it('the tag and the field have their own words and operation', async () => {
    const tag = await setup('tags');
    expect(tag.el('customer-tags-delete')!.getAttribute('aria-label')).toBe('Delete tag');
    tag.net.onApi(() => json({ id: 'x1' }));
    tag.el('customer-tags-delete-submit')!.click();
    await flush();
    expect(sent(tag.net.api[0]).path).toBe('/api/customer/tags/delete');
    document.body.innerHTML = '';
    const field = await setup('fields');
    expect(field.el('customer-fields-delete')!.textContent).toContain('Delete VIP? The values saved on the cards are deleted too.');
  });

  it('a refusal stays in the dialog', async () => {
    const s = await setup('groups');
    s.net.onApi(() => refusal(403, 'permission_denied', 'You do not have permission to do that.'));
    s.el('customer-groups-delete-submit')!.click();
    await flush();
    expect(s.el('customer-groups-delete-error')?.textContent).toContain('You do not have permission to do that.');
    expect(s.target.value).not.toBeNull();
  });
});
