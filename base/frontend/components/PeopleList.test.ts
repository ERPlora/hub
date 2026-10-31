// Employees › Personal (BASE-G11, G138, G142; the old hub's EmployeesPage): the people of the business, live, with
// how each one gets in, their role and whether they entered yet; the plan's places and, when every one is taken, why;
// inviting and changing roles on erplora.com («Members» of the business). A list that cannot be read says so.
import { applySurface } from '@erplora/ui/shell';
import { afterEach, describe, expect, it } from 'vitest';

import { EMPLOYEE, errorFrame, flush, installedApp, leaveInstalledApp, mountBase, subId, tap } from '../__tests__/mount-base';
import type { Person, Seats } from '../operations';
import PeopleList from './PeopleList.vue';

const MEMBERS_URL = 'http://localhost:8001/businesses/0199a1b2-0000-7000-8000-000000000001/members';
const PLAN_URL = 'http://localhost:8001/store/plans?business=0199a1b2-0000-7000-8000-000000000001';

function person(fields: Partial<Person> = {}): Person {
  return {
    id: 'saas:1',
    name: 'Olga Ruiz',
    initials: 'OR',
    email: 'olga@example.com',
    role: 'hub_owner',
    ways: { account: true, pin: false, badge: false },
    entered: true,
    me: false,
    ...fields,
  };
}

const PEOPLE: Person[] = [
  person({ me: true }),
  person({ id: 'saas:3', name: 'Eva Gil', initials: 'EG', email: 'eva@example.com', role: 'hub_employee', ways: { account: true, pin: true, badge: true } }),
  person({ id: 'saas:5', name: 'Nuria', initials: 'N', email: 'nuria@example.com', role: 'hub_manager', entered: false }),
];
const SEATS: Seats = { known: true, used: 3, limit: 5, full: false };

function embed(block: object | null) {
  document.head.innerHTML = block ? `<script id="hub-home" type="application/json">${JSON.stringify(block)}</script>` : '';
}

async function open(options: Parameters<typeof mountBase>[1] = {}) {
  const m = await mountBase(PeopleList, { path: '/employees', routes: ['/employees', '/employees/:person'], ...options });
  const call = await m.live();
  return { ...m, call };
}

afterEach(() => {
  applySurface('web');
  leaveInstalledApp();
  document.head.innerHTML = '';
  document.body.innerHTML = '';
});

describe('PeopleList', () => {
  it('follows the people of the business live, and says it is loading meanwhile', async () => {
    const m = await open();
    expect(m.client.stream.subscriptions('base.person.list').map((sub) => sub.params)).toEqual([{}]);
    expect(m.wrapper.find('[data-testid="people-loading"]').exists() || m.wrapper.text().includes('Loading')).toBe(true);
  });

  it('a row per person: name (with «You»), email, role, how they get in and whether they entered', async () => {
    const m = await open({ locale: 'es' });
    await m.result(m.call, 'base.person.list', { people: PEOPLE, seats: SEATS });
    const rows = m.wrapper.findAll('[data-testid="people-row"]');
    expect(rows).toHaveLength(3);
    expect(rows[0].text()).toContain('Olga Ruiz');
    expect(rows[0].text()).toContain('Tú');
    expect(rows[0].text()).toContain('Propietario');
    expect(rows[1].find('[data-testid="people-access"]').text()).toBe('Cuenta + PIN + Placa');
    expect(rows[0].find('[data-testid="people-access"]').text()).toBe('Cuenta');
    expect(rows[1].find('[data-testid="people-status"]').text()).toBe('Activo');
    expect(rows[2].find('[data-testid="people-status"]').text()).toBe('Aún no ha entrado');
    expect(rows[2].text()).toContain('Encargado');
  });

  it('the places taken against the plan’s limit', async () => {
    const m = await open();
    await m.result(m.call, 'base.person.list', { people: PEOPLE, seats: SEATS });
    expect(m.wrapper.find('[data-testid="people-seats"]').text()).toBe('3 of 5 places taken');
    expect(m.wrapper.find('[data-testid="people-full"]').exists()).toBe(false);
  });

  it('no limit, or a plan it does not know yet, never says a place is missing', async () => {
    const m = await open();
    await m.result(m.call, 'base.person.list', { people: PEOPLE, seats: { known: true, used: 3, limit: null, full: false } });
    expect(m.wrapper.find('[data-testid="people-seats"]').text()).toBe('3 people · no limit');
    await m.result(m.call, 'base.person.list', { people: PEOPLE, seats: { known: false, used: 3, limit: null, full: false } }, 2);
    expect(m.wrapper.find('[data-testid="people-seats"]').text()).toBe('3 people');
  });

  it('one person, or a plan of one place, is said in the singular', async () => {
    const m = await open({ locale: 'es' });
    const one = PEOPLE.slice(0, 1);
    await m.result(m.call, 'base.person.list', { people: one, seats: { known: false, used: 1, limit: null, full: false } });
    expect(m.wrapper.find('[data-testid="people-seats"]').text()).toBe('1 persona');
    await m.result(m.call, 'base.person.list', { people: one, seats: { known: true, used: 1, limit: null, full: false } }, 2);
    expect(m.wrapper.find('[data-testid="people-seats"]').text()).toBe('1 persona · sin límite');
    await m.result(m.call, 'base.person.list', { people: one, seats: { known: true, used: 1, limit: 1, full: true } }, 3);
    expect(m.wrapper.find('[data-testid="people-seats"]').text()).toBe('1 de 1 plaza ocupada');
    const en = await open();
    await en.result(en.call, 'base.person.list', { people: one, seats: { known: false, used: 1, limit: null, full: false } });
    expect(en.wrapper.find('[data-testid="people-seats"]').text()).toBe('1 person');
  });

  it('every place taken (BASE-G138): why, and «Upgrade plan» on the web', async () => {
    embed({ name: 'Bar', plan_url: PLAN_URL, members_url: MEMBERS_URL });
    const m = await open({ locale: 'es' });
    await m.result(m.call, 'base.person.list', { people: PEOPLE, seats: { known: true, used: 3, limit: 3, full: true } });
    const full = m.wrapper.get('[data-testid="people-full"]');
    expect(full.text()).toContain('Tu plan tiene todas las plazas ocupadas');
    expect(full.text()).toContain('Quita en erplora.com a alguien que ya no trabaje aquí, o pasa a un plan con más plazas.');
    expect(full.get('a[data-testid="people-upgrade"]').attributes('href')).toBe(PLAN_URL);
  });

  it('«Upgrade plan» sells: never on the app surfaces', async () => {
    embed({ name: 'Bar', plan_url: PLAN_URL, members_url: MEMBERS_URL });
    applySurface('mobile');
    const m = await open();
    await m.result(m.call, 'base.person.list', { people: PEOPLE, seats: { known: true, used: 3, limit: 3, full: true } });
    expect(m.wrapper.find('[data-testid="people-full"]').exists()).toBe(true);
    expect(m.wrapper.find('[data-testid="people-upgrade"]').exists()).toBe(false);
  });

  it('inviting is on erplora.com: who runs the business opens its «Members» in a new tab', async () => {
    embed({ name: 'Bar', plan_url: PLAN_URL, members_url: MEMBERS_URL });
    const m = await open({ locale: 'es' });
    await m.result(m.call, 'base.person.list', { people: PEOPLE, seats: SEATS });
    const invite = m.wrapper.get('a[data-testid="people-invite"]');
    expect(invite.text()).toContain('Invitar en erplora.com');
    expect([invite.attributes('href'), invite.attributes('target'), invite.attributes('rel')]).toEqual([MEMBERS_URL, '_blank', 'noopener']);
    expect(m.wrapper.text()).toContain('Las personas se invitan, se les cambia el rol y se quitan en erplora.com');
  });

  // gh:hub#439: on the tablet's app «Invite on erplora.com» did nothing (its webview opens no `_blank`).
  it('in the installed app, inviting opens «Members» in the system browser, and in a browser the link opens its tab', async () => {
    embed({ name: 'Bar', plan_url: PLAN_URL, members_url: MEMBERS_URL });
    const browser = await open();
    await browser.result(browser.call, 'base.person.list', { people: PEOPLE, seats: SEATS });
    expect(tap(browser.wrapper.get('[data-testid="people-invite"]').element).defaultPrevented).toBe(false);
    browser.wrapper.unmount();

    const invoke = installedApp('direct');
    const m = await open();
    await m.result(m.call, 'base.person.list', { people: PEOPLE, seats: SEATS });
    await flush();
    const click = tap(m.wrapper.get('[data-testid="people-invite"]').element);
    await flush();
    expect(click.defaultPrevented).toBe(true);
    expect(invoke).toHaveBeenCalledWith('open_external_url', { url: MEMBERS_URL });
  });

  it('the Google Play copy has no way to erplora.com’s panel (gh:hub#1897): only where it is done', async () => {
    embed({ name: 'Bar', plan_url: PLAN_URL, members_url: MEMBERS_URL });
    installedApp('play');
    const m = await open();
    await m.result(m.call, 'base.person.list', { people: PEOPLE, seats: SEATS });
    await flush();
    expect(m.wrapper.find('[data-testid="people-invite"]').exists()).toBe(false);
    expect(m.wrapper.text()).toContain('People are invited, given a role and removed on erplora.com');
  });

  it('without erplora.com’s address (a session opened with a PIN) there is no link, only where it is done', async () => {
    embed({ name: 'Bar', plan_url: '', members_url: '' });
    const m = await open();
    await m.result(m.call, 'base.person.list', { people: PEOPLE, seats: SEATS });
    expect(m.wrapper.find('[data-testid="people-invite"]').exists()).toBe(false);
    expect(m.wrapper.text()).toContain('People are invited, given a role and removed on erplora.com');
  });

  it('who runs the business opens a person’s page from their row', async () => {
    const m = await open();
    await m.result(m.call, 'base.person.list', { people: PEOPLE, seats: SEATS });
    await m.wrapper.findAll('[data-testid="people-row"]')[1].trigger('click');
    await flush();
    expect(m.router.currentRoute.value.path).toBe('/employees/saas:3');
  });

  it('anyone else sees the list, without opening a person nor inviting', async () => {
    embed({ name: 'Bar', plan_url: PLAN_URL, members_url: MEMBERS_URL });
    const m = await open({ session: EMPLOYEE });
    await m.result(m.call, 'base.person.list', { people: PEOPLE.map((p) => ({ ...p, email: '' })), seats: SEATS });
    await m.wrapper.findAll('[data-testid="people-row"]')[1].trigger('click');
    await flush();
    expect(m.router.currentRoute.value.path).toBe('/employees');
    expect(m.wrapper.find('[data-testid="people-invite"]').exists()).toBe(false);
  });

  it('a list that cannot be read says so with «Retry», never «nobody»', async () => {
    const m = await open();
    m.call.push(errorFrame(subId(m.client, 'base.person.list'), 'server_error'));
    await flush();
    expect(m.wrapper.text()).toContain('The people of this business could not be loaded.');
    expect(m.wrapper.find('[data-testid="people-row"]').exists()).toBe(false);
  });
});
