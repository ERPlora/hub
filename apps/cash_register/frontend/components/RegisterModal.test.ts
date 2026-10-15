// «New drawer» / «Rename drawer» (CASH_REGISTER-F02): its «Name», required; «Save» creates it or renames
// it and says so; a name another drawer has is said at the field.
import { toastSuccess } from '@erplora/ui/shell';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { click, ionValue, mountCash } from '../__tests__/mount-cash-register';
import RegisterModal from './RegisterModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});
vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...((await importOriginal()) as object),
  toastSuccess: vi.fn(() => Promise.resolve()),
}));
beforeEach(() => vi.mocked(toastSuccess).mockClear());

const prop = (el: Element | null, name: string): unknown => (el as unknown as Record<string, unknown>)[name];

async function setup(register: { id: string; name: string } | null = null) {
  const m = await mountCash(RegisterModal, { props: { open: true, register } });
  const name = () => m.inDoc('cash-register-register-name');
  const submit = () => click(m.inDoc('cash-register-register-submit'));
  return { ...m, name, submit };
}

describe('RegisterModal', () => {
  it('creates a drawer by its name', async () => {
    const s = await setup();
    expect(s.inDoc('cash-register-register')?.getAttribute('aria-label')).toBe('New drawer');
    await ionValue(s.name(), '  Bar ', 'ionInput');
    s.answer(201, { id: 'r1', name: 'Bar', is_active: true });
    await s.submit();
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/cash_register/registers', query: {}, body: { name: 'Bar' } }]);
    expect(toastSuccess).toHaveBeenCalledWith('Drawer created');
    expect(s.wrapper.emitted('update:open')).toEqual([[false]]);
  });

  it('renames one, starting from its name', async () => {
    const s = await setup({ id: 'r1', name: 'Bar' });
    expect(s.inDoc('cash-register-register')?.getAttribute('aria-label')).toBe('Rename drawer');
    expect(prop(s.name(), 'value')).toBe('Bar');
    await ionValue(s.name(), 'Terrace', 'ionInput');
    s.answer(200, { id: 'r1', name: 'Terrace', is_active: true });
    await s.submit();
    expect(s.sent()[0]).toMatchObject({ path: '/api/cash_register/registers/update', body: { register_id: 'r1', name: 'Terrace' } });
    expect(toastSuccess).toHaveBeenCalledWith('Drawer renamed');
  });

  it('a name is required and a taken one is said at the field', async () => {
    const s = await setup();
    await s.submit();
    expect(prop(s.name(), 'errorText')).toBe("Type the drawer's name.");
    expect(s.sent()).toEqual([]);
    await ionValue(s.name(), 'bar', 'ionInput');
    s.answer(409, { error: { code: 'cash_register.register_exists', message: 'There is already a drawer with that name.', fields: { name: 'There is already a drawer with that name.' } } });
    await s.submit();
    expect(prop(s.name(), 'errorText')).toBe('There is already a drawer with that name.');
  });
});
