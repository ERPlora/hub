// A person's page (BASE-G10, G139, G140; the old hub's EmployeeFormPage, «Edit user»): for who runs the business, what
// the hub keeps of a person's way in, live — their details (changed on erplora.com), their PIN (since when; «Remove the
// PIN», asked first) and their badge (a reader's burst fills the field; «Save badge», «Remove the badge»). What this
// administrator may not change (the owner's, one's own badge) is said instead of offered; a refusal by its code.
import { afterEach, describe, expect, it, vi } from 'vitest';

import { errorFrame, flush, mountBase, subId } from '../__tests__/mount-base';
import type { PersonDetail } from '../operations';
import PersonPage from './PersonPage.vue';

vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/shell')>()),
  toastSuccess: vi.fn(() => Promise.resolve()),
  toastError: vi.fn(() => Promise.resolve()),
}));
vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const MEMBERS_URL = 'http://localhost:8001/businesses/0199a1b2-0000-7000-8000-000000000001/members';

function detail(fields: Partial<PersonDetail> = {}): PersonDetail {
  return {
    id: 'saas:3',
    name: 'Eva Gil',
    initials: 'EG',
    email: 'eva@example.com',
    role: 'hub_employee',
    ways: { account: true, pin: true, badge: false },
    entered: true,
    me: false,
    pin_set_at: '2026-10-20T09:00:00Z',
    badge_set_at: null,
    may: { remove_pin: true, set_badge: true },
    ...fields,
  };
}

/** What the page posted: [path, body]. */
function posted(m: { net: { api: { url: string; init: RequestInit }[] } }) {
  return m.net.api.map((call) => [new URL(call.url, 'http://a.localhost').pathname, JSON.parse(String(call.init.body))]);
}

async function open(options: Parameters<typeof mountBase>[1] = {}) {
  document.head.innerHTML = `<script id="hub-home" type="application/json">${JSON.stringify({ name: 'Bar', plan_url: '', members_url: MEMBERS_URL })}</script>`;
  const m = await mountBase(PersonPage, { path: '/employees/saas:3', routes: ['/employees', '/employees/:person'], ...options });
  const call = await m.live();
  return { ...m, call };
}

function badgeBurst(card: string) {
  let at = 1_000_000;
  const now = Date.now;
  Date.now = () => at;
  for (const key of [...card, 'Enter']) {
    at += 5;
    document.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true }));
  }
  Date.now = now;
}

/** Types into an `ion-input` as Ionic tells it: its `ionInput` event. */
function type(field: { element: Element }, value: string) {
  field.element.dispatchEvent(new CustomEvent('ionInput', { detail: { value } }));
}

/** What an `ion-input` holds: its property, or the attribute Vue leaves on an element it does not know. */
function valueOf(field: { element: Element }) {
  return (field.element as HTMLInputElement).value ?? field.element.getAttribute('value');
}

afterEach(() => {
  document.head.innerHTML = '';
  document.body.innerHTML = '';
});

describe('PersonPage', () => {
  it('follows the person of the address live', async () => {
    const m = await open();
    expect(m.client.stream.subscriptions('base.person.detail').map((sub) => sub.params)).toEqual([{ person: 'saas:3' }]);
  });

  it('their details, changed on erplora.com, and since when they have a PIN', async () => {
    const m = await open({ locale: 'es' });
    await m.result(m.call, 'base.person.detail', detail());
    expect(m.wrapper.text()).toContain('Eva Gil');
    expect(m.wrapper.text()).toContain('eva@example.com');
    expect(m.wrapper.text()).toContain('Empleado');
    expect(m.wrapper.get('a[data-testid="person-open-saas"]').attributes('href')).toBe(MEMBERS_URL);
    expect(m.wrapper.get('[data-testid="person-pin"]').text()).toContain('Tiene PIN desde el');
    expect(m.wrapper.get('[data-testid="person-badge"]').text()).toContain('Sin placa.');
  });

  it('«Remove the PIN» asks first, then the PIN goes (BASE-G139)', async () => {
    const m = await open({ onApi: () => Response.json(detail({ ways: { account: true, pin: false, badge: false }, pin_set_at: null })), locale: 'es' });
    await m.result(m.call, 'base.person.detail', detail());
    await m.wrapper.get('[data-testid="person-pin-remove"]').trigger('click');
    await flush();
    expect(document.body.textContent).toContain('Eva Gil dejará de entrar en las cajas con su PIN.');
    expect(posted(m)).toEqual([]);
    (document.querySelector('[data-testid="person-pin-confirm-submit"]') as HTMLElement).click();
    await flush();
    expect(posted(m)).toEqual([['/api/people/pin/remove', { person: 'saas:3' }]]);
  });

  it('without a PIN there is nothing to remove, and where it is chosen is said', async () => {
    const m = await open();
    await m.result(m.call, 'base.person.detail', detail({ ways: { account: true, pin: false, badge: false }, pin_set_at: null }));
    expect(m.wrapper.find('[data-testid="person-pin-remove"]').exists()).toBe(false);
    expect(m.wrapper.get('[data-testid="person-pin"]').text()).toContain('the person chooses it in “My profile”');
  });

  it('a reader’s burst fills the badge, and «Save badge» gives it (BASE-G140)', async () => {
    const m = await open({
      onApi: () => Response.json(detail({ ways: { account: true, pin: true, badge: true }, badge_set_at: '2026-10-24T09:00:00Z' })),
    });
    await m.result(m.call, 'base.person.detail', detail());
    badgeBurst('CARD0003');
    await flush();
    expect(valueOf(m.wrapper.get('[data-testid="person-badge-input"]'))).toBe('CARD0003');
    await m.wrapper.get('[data-testid="person-badge-save"]').trigger('click');
    await flush();
    expect(posted(m)).toEqual([['/api/people/badge', { person: 'saas:3', badge: 'CARD0003' }]]);
  });

  it('what is no badge is said under the field and never sent', async () => {
    const m = await open({ onApi: () => Response.json(detail()) });
    await m.result(m.call, 'base.person.detail', detail());
    type(m.wrapper.get('[data-testid="person-badge-input"]'), 'ab');
    await m.wrapper.get('[data-testid="person-badge-save"]').trigger('click');
    await flush();
    expect(m.wrapper.get('[data-testid="person-badge-error"]').text()).toBe(
      'A badge has 4 to 64 characters: letters, digits, “-” and “_”.',
    );
    expect(posted(m)).toEqual([]);
  });

  it('a card somebody else carries, or too many tried, is told from its code', async () => {
    const m = await open({
      onApi: () => Response.json({ error: { code: 'base.badge_taken', message: 'Taken (server words)' } }, { status: 409 }),
    });
    await m.result(m.call, 'base.person.detail', detail());
    type(m.wrapper.get('[data-testid="person-badge-input"]'), 'CARD-0004');
    await m.wrapper.get('[data-testid="person-badge-save"]').trigger('click');
    await flush();
    expect(m.wrapper.get('[data-testid="person-badge-error"]').text()).toContain('Somebody else already carries that badge.');
  });

  it('a badge kept can be taken away', async () => {
    const m = await open({ onApi: () => Response.json(detail()) });
    await m.result(m.call, 'base.person.detail', detail({ ways: { account: true, pin: true, badge: true }, badge_set_at: '2026-10-24T09:00:00Z' }));
    expect(m.wrapper.get('[data-testid="person-badge"]').text()).toContain('Has a badge since');
    await m.wrapper.get('[data-testid="person-badge-remove"]').trigger('click');
    await flush();
    expect(posted(m)).toEqual([['/api/people/badge/remove', { person: 'saas:3' }]]);
  });

  it('what this administrator may not change is said, never offered', async () => {
    const m = await open();
    await m.result(
      m.call,
      'base.person.detail',
      detail({ role: 'hub_owner', ways: { account: true, pin: true, badge: true }, may: { remove_pin: false, set_badge: false } }),
    );
    expect(m.wrapper.find('[data-testid="person-pin-remove"]').exists()).toBe(false);
    expect(m.wrapper.find('[data-testid="person-badge-input"]').exists()).toBe(false);
    expect(m.wrapper.find('[data-testid="person-badge-remove"]').exists()).toBe(false);
    expect(m.wrapper.text()).toContain("Only the owner changes the owner's way in.");
  });

  it('one’s own badge is not one’s to give', async () => {
    const m = await open();
    await m.result(m.call, 'base.person.detail', detail({ me: true, role: 'hub_admin', may: { remove_pin: true, set_badge: false } }));
    expect(m.wrapper.find('[data-testid="person-badge-input"]').exists()).toBe(false);
    expect(m.wrapper.text()).toContain('Nobody registers their own badge');
  });

  it('a person who is not in this business, or a page that cannot be read, says so', async () => {
    const m = await open();
    m.call.push(errorFrame(subId(m.client, 'base.person.detail'), 'base.person_not_found'));
    await flush();
    expect(m.wrapper.text()).toContain('This person is not in this business.');
    const other = await open();
    other.call.push(errorFrame(subId(other.client, 'base.person.detail'), 'server_error'));
    await flush();
    expect(other.wrapper.text()).toContain('This person could not be opened.');
  });
});
