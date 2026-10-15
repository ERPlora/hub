// «Open cash session» (CASH_REGISTER-F03): «Drawer» (only when the business has drawers; the only one is
// chosen alone), «Opening float» as it is read («150,50»; empty is 0), «Notes», «Open session» / «Cancel».
// An amount that cannot be read is said under the field and nothing is sent; the server's refusal (one
// already open, a float required) is read in the window, at its field; success says «Session opened».
import { toastSuccess } from '@erplora/ui/shell';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { click, ionValue, mountCash } from '../__tests__/mount-cash-register';
import OpenSessionModal from './OpenSessionModal.vue';

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
const REGISTERS = 'cash_register.register.list';
const page = (rows: unknown[]) => ({ rows, total: rows.length, limit: 100, offset: 0 });

async function setup(options: { locale?: 'en' | 'es'; unassignedCash?: number } = {}) {
  const m = await mountCash(OpenSessionModal, {
    props: { open: true, unassignedCash: options.unassignedCash ?? 0 },
    locale: options.locale,
  });
  await m.live();
  const submit = () => click(m.inDoc('cash-register-open-submit'));
  return { ...m, submit };
}

describe('OpenSessionModal', () => {
  it('asks the active drawers and, with only one, chooses it alone', async () => {
    const s = await setup();
    expect(s.inDoc('cash-register-open')?.getAttribute('aria-label')).toBe('Open cash session');
    expect(s.params(REGISTERS)).toEqual([{ is_active: true, limit: 100 }]);
    expect(s.inDoc('cash-register-open-register')).toBeNull();
    await s.result(REGISTERS, page([{ id: 'r1', name: 'Bar', is_active: true }]));
    expect(prop(s.inDoc('cash-register-open-register'), 'value')).toBe('r1');
    expect(prop(s.inDoc('cash-register-open-balance'), 'label')).toBe('Opening float');
    expect([s.inDoc('cash-register-open-submit')?.textContent?.trim(), s.inDoc('cash-register-open-cancel')?.textContent?.trim()]).toEqual([
      'Open session',
      'Cancel',
    ]);
  });

  it('opens with the float in cents, the drawer and the notes, says «Session opened» and closes', async () => {
    const s = await setup();
    await s.result(REGISTERS, page([{ id: 'r1', name: 'Bar', is_active: true }, { id: 'r2', name: 'Terrace', is_active: true }]));
    expect(prop(s.inDoc('cash-register-open-register'), 'value')).toBe('');
    await ionValue(s.inDoc('cash-register-open-register'), 'r2');
    await ionValue(s.inDoc('cash-register-open-balance'), '150,50', 'ionInput');
    await ionValue(s.inDoc('cash-register-open-notes'), '  Morning ', 'ionInput');
    s.answer(201, { id: 's1', number: 'S-261014-0001', status: 'open' });
    await s.submit();
    expect(s.sent()).toEqual([
      {
        method: 'POST',
        path: '/api/cash_register/sessions/open',
        query: {},
        body: { register_id: 'r2', opening_balance: 15050, opening_notes: 'Morning' },
      },
    ]);
    expect(toastSuccess).toHaveBeenCalledWith('Session opened');
    expect(s.wrapper.emitted('update:open')).toEqual([[false]]);
  });

  it('an empty float opens at 0 without a drawer', async () => {
    const s = await setup();
    await s.result(REGISTERS, page([]));
    s.answer(201, { id: 's1' });
    await s.submit();
    expect(s.sent()[0].body).toEqual({ opening_notes: '' });
  });

  it('an amount that cannot be read is said under the field and nothing is sent', async () => {
    const s = await setup();
    await ionValue(s.inDoc('cash-register-open-balance'), 'abc', 'ionInput');
    await s.submit();
    expect(s.sent()).toEqual([]);
    expect(prop(s.inDoc('cash-register-open-balance'), 'errorText')).toBe('This is not an amount. Type a figure, for example 12.50.');
  });

  it('the server’s refusal is read in the window and at its field', async () => {
    const s = await setup();
    s.answer(409, {
      error: {
        code: 'cash_register.opening_balance_required',
        message: 'This business requires an opening float: give the cash the drawer starts with.',
        fields: { opening_balance: 'This business requires an opening float: give the cash the drawer starts with.' },
      },
    });
    await s.submit();
    expect(s.inDoc('cash-register-open-error')?.textContent).toContain('This business requires an opening float');
    expect(prop(s.inDoc('cash-register-open-balance'), 'errorText')).toContain('This business requires an opening float');
    expect(s.wrapper.emitted('update:open')).toBeUndefined();
  });

  it('reminds the cash charged with the drawer closed, to count it in the float', async () => {
    const s = await setup({ unassignedCash: 300 });
    expect(s.inDoc('cash-register-open-unassigned')?.textContent?.replace(/\s/g, ' ')).toContain('€3.00 were charged in cash with the drawer closed');
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    expect(s.inDoc('cash-register-open')?.getAttribute('aria-label')).toBe('Abrir sesión de caja');
    expect(prop(s.inDoc('cash-register-open-balance'), 'label')).toBe('Fondo de apertura');
    expect(s.inDoc('cash-register-open-submit')?.textContent?.trim()).toBe('Abrir sesión');
  });
});
