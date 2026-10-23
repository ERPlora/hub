// «Who is serving this check» / «Whose line is this» (SALE-F16): «Me (whoever is signed in)» — or, for a
// line, «The check's professional» — and the active team of Staff, searched on the server. The choice
// in use is marked. A team that cannot be loaded says the sale stays with whoever is signed in. For the
// check it asks Staff whose record the session is (`staff.member.current`): without one, it warns that a
// sale left on «Me» counts for nobody.
import { describe, expect, it, vi } from 'vitest';
import { h, ref } from 'vue';

import { click, errorFrame, ionValue, mountSale, settle } from '../../__tests__/mount-sale';
import { page } from './__tests__/fixtures';
import StaffPicker from './StaffPicker.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const OP = 'staff.member.list';
const member = (id: string, full_name: string) => ({
  id,
  first_name: full_name.split(' ')[0],
  last_name: full_name.split(' ')[1] ?? '',
  full_name,
  email: '',
  phone: '',
  employee_number: '',
  role_id: null,
  role_name: null,
  user_id: null,
  status: 'active',
  is_bookable: true,
  hire_date: null,
  color: '',
});

async function setup(
  props: Record<string, unknown> = {},
  locale: 'en' | 'es' = 'en',
  answer?: { status: number; body: unknown },
) {
  const open = ref(true);
  const m = await mountSale(
    { setup: () => () => h(StaffPicker, { open: open.value, 'onUpdate:open': (v: boolean) => (open.value = v), mode: 'check', current: null, ...props }) },
    { locale, answer },
  );
  await settle();
  await m.live();
  return { ...m, open, picker: () => m.wrapper.findComponent(StaffPicker) };
}

describe('StaffPicker', () => {
  it('for the check: its title and hint, «Me» first, and the active team asked on the server', async () => {
    const m = await setup({}, 'es');
    expect(m.find('pos-staff-title').text()).toBe('Quién atiende esta cuenta');
    expect(m.find('pos-staff-hint').text()).toContain('Si lo dejas en «Yo», el TPV usa a quien tenga la sesión.');
    expect(m.find('pos-staff-me').text()).toBe('Yo (quien tenga la sesión)');
    expect(m.find('pos-staff-me').attributes('aria-pressed')).toBe('true');
    expect(m.params(OP)).toEqual([{ status: 'active', search: '', sort: 'name', limit: 20, offset: 0 }]);
    expect(m.find('pos-staff-loading').text()).toBe('Cargando el equipo…');
  });

  it('lists the team; a tap chooses the person (with the name, for the chip)', async () => {
    const m = await setup({ current: 's2' });
    await m.result(OP, page([member('s1', 'Marta Ruiz'), member('s2', 'Luis Gil')]));
    expect(m.find('pos-staff-s2').attributes('aria-pressed')).toBe('true');
    expect(m.find('pos-staff-me').attributes('aria-pressed')).toBe('false');
    await click(m.find('pos-staff-s1').element);
    expect(m.picker().emitted('choose')).toEqual([[{ id: 's1', name: 'Marta Ruiz' }]]);
  });

  it('«Me» clears the choice', async () => {
    const m = await setup({ current: 's1' });
    await click(m.find('pos-staff-me').element);
    expect(m.picker().emitted('choose')).toEqual([[{ id: null, name: null }]]);
  });

  it('searches on the server', async () => {
    const m = await setup();
    await ionValue(m.wrapper.find('ion-searchbar').element, 'mar', 'ionInput');
    await m.reopen();
    expect(m.params(OP)[0].search).toBe('mar');
    await m.result(OP, page([]));
    expect(m.find('pos-staff-empty').text()).toBe('Nobody in the team matches your search.');
  });

  it('nobody else to serve, and a team that cannot be loaded, are said', async () => {
    const m = await setup();
    await m.result(OP, page([]));
    expect(m.find('pos-staff-empty').text()).toBe('This hub has nobody else to serve. Add staff from Settings.');
    m.net.lastStream().push(errorFrame(m.subId(OP), 'app_inactive'));
    await m.reopen();
    expect(m.find('pos-staff-error').text()).toBe('The team could not be loaded. The sale is still attributed to whoever is signed in.');
    expect(m.find('pos-staff-me').exists()).toBe(true);
  });

  it('for a line: «Whose line is this» and «The check’s professional»', async () => {
    const m = await setup({ mode: 'line' }, 'es');
    expect(m.find('pos-staff-title').text()).toBe('De quién es esta línea');
    expect(m.find('pos-staff-hint').text()).toContain('Solo se mueve esta línea.');
    expect(m.find('pos-staff-me').text()).toBe('El profesional de la cuenta');
  });

  // flow: SALE-F16 (atribuir a quien tiene la sesión con «Atiende yo»)
  const CURRENT = '/api/staff/members/current';
  const asked = (m: Awaited<ReturnType<typeof setup>>) => m.sent().filter((call) => call.path === CURRENT);

  it('for the check, without a record of the session in Staff, warns that a sale left on «Me» counts for nobody', async () => {
    const m = await setup({}, 'es', { status: 200, body: { member: null } });
    expect(asked(m)).toHaveLength(1);
    expect(m.find('pos-staff-unlinked').text()).toBe(
      'Tu cuenta no tiene ficha en Personal: si lo dejas en «Yo», esta venta no contará para nadie.',
    );
    expect(m.find('pos-staff-unlinked').attributes('role')).toBe('status');
    expect(m.find('pos-staff-me').exists()).toBe(true);
  });

  it('with a record of the session, or when Staff cannot answer, it does not warn', async () => {
    const linked = await setup({}, 'en', { status: 200, body: { member: { id: 's1', full_name: 'Marta Ruiz' } } });
    expect(asked(linked)).toHaveLength(1);
    expect(linked.find('pos-staff-unlinked').exists()).toBe(false);
    // Staff off: the list says the team could not be loaded; whose record it is, nobody knows.
    const off = await setup({}, 'en', { status: 404, body: { error: { code: 'app_inactive', message: 'Off.' } } });
    expect(off.find('pos-staff-unlinked').exists()).toBe(false);
  });

  it('for a line it does not ask: the line goes with the check or with the person chosen', async () => {
    const m = await setup({ mode: 'line' }, 'en', { status: 200, body: { member: null } });
    expect(asked(m)).toEqual([]);
    expect(m.find('pos-staff-unlinked').exists()).toBe(false);
  });

  it('«Cancel» closes it without choosing', async () => {
    const m = await setup();
    await click(m.find('pos-staff-cancel').element);
    expect(m.open.value).toBe(false);
    expect(m.picker().emitted('choose')).toBeUndefined();
  });
});
