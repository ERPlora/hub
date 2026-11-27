import { toastSuccess } from '@erplora/ui/shell';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { click, errorFrame, flush, ionValue, mountBase, subId } from '../__tests__/mount-base';
import type { HubRoleRow, PersonDetail } from '../operations/people';
import PersonRoleCard from './PersonRoleCard.vue';

const CASHIER = '0199aaaa-0000-7000-8000-000000000001';
const LEAD = '0199aaaa-0000-7000-8000-000000000002';

const row = (key: string, label: string, origin: 'basic' | 'own' = 'own'): HubRoleRow => ({
  key,
  label,
  description: '',
  origin,
  members: 0,
  to_review: false,
  mine: false,
  permissions: 10,
});
const ROLES = [row('hub_employee', 'Empleado', 'basic'), row(CASHIER, 'Cajero'), row(LEAD, 'Jefe de turno')];

function eva(fields: Partial<PersonDetail> = {}): PersonDetail {
  return {
    id: 'saas:3',
    name: 'Eva Gil',
    initials: 'EG',
    email: 'eva@example.com',
    role: 'hub_employee',
    ways: { account: true, pin: false, badge: false },
    entered: true,
    me: false,
    pin_set_at: null,
    badge_set_at: null,
    business_role: CASHIER,
    role_refusal: null,
    may: { remove_pin: true, set_badge: true, give_role: true },
    ...fields,
  };
}

async function open(person = eva(), roles: HubRoleRow[] | null = ROLES, locale: 'en' | 'es' = 'es') {
  const m = await mountBase(PersonRoleCard, { locale, props: { person }, routes: ['/employees'] });
  const call = await m.live();
  if (roles) await m.result(call, 'base.role.list', { roles });
  return { ...m, call };
}

type Mounted = Awaited<ReturnType<typeof open>>;
const select = (m: Mounted) => m.inDoc('person-role-select');
const options = (m: Mounted) => [...(select(m)?.querySelectorAll('ion-select-option') ?? [])].map((o) => o.textContent?.trim());
const chosen = (m: Mounted) => (select(m) as unknown as { value: string } | null)?.value;
const given = (person: string, role: string, label: string) => [200, { person, name: 'Eva Gil', role, label }] as [number, unknown];

afterEach(() => {
  vi.mocked(toastSuccess).mockClear();
  document.body.innerHTML = '';
});

describe('PersonRoleCard', () => {
  it('follows the roles of the business live', async () => {
    const m = await open();
    expect(m.client.stream.subscriptions('base.role.list')).toHaveLength(1);
  });

  it('offers the role of their invitation and the business’s own, with the one that rules chosen', async () => {
    const m = await open();
    expect(m.inDoc('person-role')?.querySelector('h2')?.textContent).toContain('Rol en este negocio');
    expect(options(m)).toEqual(['El de la invitación (Empleado)', 'Cajero', 'Jefe de turno']);
    expect(chosen(m)).toBe(CASHIER);
    const field = select(m) as unknown as { mode?: string; fill?: string };
    expect([field.mode ?? select(m)?.getAttribute('mode'), field.fill ?? select(m)?.getAttribute('fill')]).toEqual([
      'md',
      'outline',
    ]);
  });

  it('without a role of the business, the one of their invitation is chosen', async () => {
    const m = await open(eva({ business_role: null }));
    expect(chosen(m)).toBe('hub_employee');
  });

  it('choosing another gives it at once and says who has which role now', async () => {
    const m = await open();
    m.answerBy({ '/api/roles/assign': given('saas:3', LEAD, 'Jefe de turno') });
    await ionValue(select(m), LEAD);
    await flush();
    expect(m.sent().map((call) => [call.method, call.path, call.body])).toEqual([
      ['POST', '/api/roles/assign', { person: 'saas:3', role: LEAD }],
    ]);
    expect(toastSuccess).toHaveBeenCalledWith('Eva Gil tiene ahora el rol Jefe de turno.');
  });

  it('the role of their invitation returns them to it', async () => {
    const m = await open();
    m.answerBy({ '/api/roles/assign': given('saas:3', 'hub_employee', 'Empleado') });
    await ionValue(select(m), 'hub_employee');
    await flush();
    expect(m.sent().map((call) => call.body)).toEqual([{ person: 'saas:3', role: 'hub_employee' }]);
  });

  it('choosing the one they have sends nothing', async () => {
    const m = await open();
    await ionValue(select(m), CASHIER);
    await flush();
    expect(m.sent()).toEqual([]);
  });

  it('a refusal is said under the choice, which goes back to the role they have', async () => {
    const m = await open();
    const message = 'Un rol no puede permitir más de lo que puedes hacer tú.';
    m.answerBy({ '/api/roles/assign': [403, { error: { code: 'base.role_beyond_editor', message, fields: { role: message } } }] });
    await ionValue(select(m), LEAD);
    await flush();
    expect(m.inDoc('person-role-error')?.textContent).toContain(message);
    expect(chosen(m)).toBe(CASHIER);
    expect(toastSuccess).not.toHaveBeenCalled();
  });

  it.each([
    ['base.role_of_owner', 'El propietario siempre es el propietario: nadie le da otro rol.'],
    ['base.role_of_accountant', 'La gestoría solo lee y no ocupa plaza del plan: se queda con el rol de su invitación.'],
    ['base.role_own', 'Nadie se cambia su propio rol: pídeselo a alguien por encima de ti.'],
    ['base.role_above', 'Solo puedes dar un rol a quien está por debajo de ti en el negocio.'],
  ] as const)('%s: the role is said with why, and there is nothing to choose', async (code, why) => {
    const m = await open(eva({ business_role: null, role_refusal: code, may: { remove_pin: true, set_badge: true, give_role: false } }));
    expect(select(m)).toBeNull();
    expect(m.inDoc('person-role-current')?.textContent).toContain('El de la invitación (Empleado)');
    expect(m.inDoc('person-role-refused')?.textContent).toContain(why);
  });

  it('who does not manage the roles only reads it, without a reason', async () => {
    const m = await open(eva({ may: { remove_pin: true, set_badge: true, give_role: false } }));
    expect(select(m)).toBeNull();
    expect(m.inDoc('person-role-current')?.textContent).toContain('Cajero');
    expect(m.inDoc('person-role-refused')).toBeNull();
  });

  it('without roles of its own, it says where they are made', async () => {
    const m = await open(eva({ business_role: null }), [row('hub_employee', 'Empleado', 'basic')]);
    expect(select(m)).toBeNull();
    expect(m.inDoc('person-role-none')?.textContent).toContain('Este negocio aún no tiene roles propios');
    await click(m.inDoc('person-role-make'));
    await flush();
    expect(m.router.currentRoute.value.fullPath).toBe('/employees#roles');
  });

  it('says it is loading the roles, and when they cannot be read, offers to retry', async () => {
    const m = await open(eva(), null);
    expect(m.inDoc('person-role-loading')?.textContent).toContain('Cargando los roles…');
    expect(select(m)).toBeNull();

    m.call.push(errorFrame(subId(m.client, 'base.role.list'), 'server_error'));
    await flush();
    expect(m.inDoc('person-role-load-error')?.textContent).toContain('No se pudieron cargar los roles.');
    const reconnect = vi.spyOn(m.client.stream, 'reconnect');
    await click(m.inDoc('person-role-load-error')?.querySelector('ion-button') ?? null);
    expect(reconnect).toHaveBeenCalledTimes(1);
  });

  it('in English too', async () => {
    const m = await open(eva(), ROLES, 'en');
    expect(m.inDoc('person-role')?.querySelector('h2')?.textContent).toContain('Role in this business');
    expect(options(m)?.[0]).toBe('From the invitation (Employee)');
  });
});
