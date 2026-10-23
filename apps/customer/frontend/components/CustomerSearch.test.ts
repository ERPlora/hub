// The till's customer search (WORKBOOK «Buscador de cliente del TPV»; CUSTOMER-F17, F18): a button
// «Assign customer» (or the chosen customer's name) opens a search by name, phone or email over the
// first 20 cards; a pick reads the whole card and hands the sale a COPY of its tax details; «+ New
// customer «…»» creates one with name and phone (or picks the live card that already has that phone)
// and assigns it; «Remove customer» leaves the sale without one. The sale owns the hole; this paints it.
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { defineComponent, h, ref, render } from 'vue';

import { customerRow, DETAIL, pageOf } from '../__tests__/fixtures';
import { EMPLOYEE, flush, json, mountCustomer, refusal, sent, VIEWER } from '../__tests__/mount-customer';
import type { SessionMe } from '@erplora/ui/shell';
import CustomerSearch, { type CustomerSnapshot, snapshotOf } from './CustomerSearch.vue';
import source from './CustomerSearch.vue?raw';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});
// No timer may outlive a test: Vitest tears the page's window down at the end of the file, and a timer
// still armed then (Ionic's searchbar arms one for 300 ms when it loads) fires into a missing
// `requestAnimationFrame`: an «Unhandled error» and exit 1 with every test green. Fake timeouts that follow
// the real clock (the harness's flush() still runs) let each test's end count them.
beforeAll(() => {
  // Vue arms a one-off 3 s timer (its devtools hook) the first time it renders: armed here, on the real
  // clock, it is not a test's.
  render(null, document.createElement('div'));
});
beforeEach(() => {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'], shouldAdvanceTime: true, advanceTimeDelta: 1 });
});
afterEach(async () => {
  try {
    document.body.innerHTML = '';
    // What was taken off the page before it loaded arms its timer in the next frames: let them run first.
    await flush();
    expect(vi.getTimerCount(), 'timers still armed when the test ends').toBe(0);
  } finally {
    vi.useRealTimers();
  }
});

// DETAIL is Ana García of ACME: the document goes to the company, the screen names the person.
const SNAPSHOT: CustomerSnapshot = {
  customer_id: 'c1',
  customer_name: 'ACME',
  display_name: 'Ana García',
  customer_tax_id: '12345678Z',
  customer_address: 'Calle Mayor 1, 28001 Madrid, Spain',
  customer_country: 'ES',
};
const PHONE_INVALID = 'Not a valid phone of its country: check the digits or write it with its international prefix (+44…).';

/** Waits until Ionic has loaded every component on the page (Stencil marks each one `hydrated`), as a
 *  browser paints a screen before anyone taps it: a component taken off the page before it loads finishes
 *  loading off it, and the timer it arms then (the searchbar's) is never cleared. */
async function loaded(): Promise<void> {
  const loading = () =>
    [...document.querySelectorAll('*')].filter(
      (el) => el.localName.startsWith('ion-') && customElements.get(el.localName) && !el.classList.contains('hydrated'),
    );
  for (let frame = 0; frame < 10 && loading().length; frame++) await new Promise(requestAnimationFrame);
  expect(loading().map((el) => el.localName), 'Ionic components still loading').toEqual([]);
}

async function setup(initial: CustomerSnapshot | null = null, session?: SessionMe, open = false) {
  const value = ref<CustomerSnapshot | null>(initial);
  const isOpen = ref(open);
  const Host = defineComponent({
    setup: () => () =>
      h(CustomerSearch, {
        modelValue: value.value,
        'onUpdate:modelValue': (v: CustomerSnapshot | null) => (value.value = v),
        open: isOpen.value,
        'onUpdate:open': (v: boolean) => (isOpen.value = v),
      }),
  });
  const m = await mountCustomer(Host, { attachTo: document.body, session });
  await loaded();
  const el = <T extends HTMLElement = HTMLElement & { value?: string; disabled?: boolean; errorText?: string }>(id: string) =>
    document.querySelector<T>(`[data-testid="${id}"]`);
  const click = async (id: string) => {
    el(id)!.click();
    await flush();
  };
  async function type(id: string, text: string) {
    const input = el(id)!;
    input.value = text;
    input.dispatchEvent(new CustomEvent('ionInput', { detail: { value: text } }));
    await flush();
  }
  async function results(rows = [customerRow('c1', 'Ana García'), customerRow('c2', 'Luis')]) {
    const call = await m.live();
    await m.result(call, 'customer.customer.list', pageOf(rows));
    return call;
  }
  return { ...m, value, isOpen, el, click, type, results };
}

describe('snapshotOf: the tax copy the sale keeps', () => {
  it('names the company as the fiscal recipient when the card has one, and keeps the person to show', () => {
    expect(snapshotOf(DETAIL, 'en')).toEqual(SNAPSHOT);
  });

  it('names the person when the card has no company', () => {
    expect(snapshotOf({ ...DETAIL, company_name: '  ' }, 'en')).toMatchObject({ customer_name: 'Ana García', display_name: 'Ana García' });
  });
});

describe('CustomerSearch: the button', () => {
  it('says «Assign customer» with no customer, and the customer\'s name once chosen', async () => {
    const none = await setup();
    expect(none.el('customer-search-trigger')!.textContent?.trim()).toBe('Assign customer');
    document.body.innerHTML = '';
    const chosen = await setup(SNAPSHOT);
    // The person, not the company the document goes to.
    expect(chosen.el('customer-search-trigger')!.textContent?.trim()).toBe('Ana García');
  });

  it('opens the search («Choose customer») over the first 20 cards; the sale can open it too', async () => {
    const s = await setup();
    expect(s.el('customer-search-modal')?.querySelector('[data-testid="customer-picker-search"]')).toBeFalsy();
    await s.click('customer-search-trigger');
    expect(s.isOpen.value).toBe(true);
    expect(s.el('customer-search-modal')!.getAttribute('aria-label')).toBe('Choose customer');
    await s.results();
    expect(s.params('customer.customer.list')).toEqual([{ limit: 20, sort: 'name' }]);
    document.body.innerHTML = '';
    const required = await setup(null, undefined, true);
    expect(required.el('customer-picker-search')).not.toBeNull();
  });
});

describe('CustomerSearch: assigning (F17)', () => {
  it('a pick reads the whole card and hands the sale a copy of its tax details, then closes', async () => {
    const s = await setup(null, undefined, true);
    await s.results();
    s.net.onApi(() => json(DETAIL));
    await s.click('customer-picker-result-c1');
    expect(sent(s.net.api[0])).toMatchObject({ path: '/api/customer/customers/detail', query: { id: 'c1' } });
    expect(s.value.value).toEqual(SNAPSHOT);
    expect(s.isOpen.value).toBe(false);
  });

  it('if the card cannot be read the customer is not assigned, and it says so', async () => {
    const s = await setup(null, undefined, true);
    await s.results();
    s.net.onApi(() => refusal(500, 'server_error', 'boom'));
    await s.click('customer-picker-result-c2');
    expect(s.value.value).toBeNull();
    expect(s.el('customer-search-error')!.textContent).toContain("Could not load Luis's tax details. Tap again to retry.");
    expect(s.isOpen.value).toBe(true);
  });

  it('«Remove customer» leaves the sale without one', async () => {
    const s = await setup(SNAPSHOT, undefined, true);
    await s.click('customer-search-remove');
    expect(s.value.value).toBeNull();
    expect(s.isOpen.value).toBe(false);
  });

  it('marks the customer already chosen', async () => {
    const s = await setup(SNAPSHOT, undefined, true);
    await s.results();
    expect(s.el('customer-picker-result-c1')!.classList.contains('customer-picker__item--selected')).toBe(true);
  });
});

describe('CustomerSearch: «+ New customer» (F18)', () => {
  it('offers «+ New customer «…»» with what was typed: a phone goes to «Phone», anything else to «Name»', async () => {
    const s = await setup(null, undefined, true);
    await s.results([]);
    await s.type('customer-picker-search', '600 111 222');
    expect(s.el('customer-search-quick-add')!.textContent?.trim()).toBe('+ New customer «600 111 222»');
    await s.click('customer-search-quick-add');
    expect([s.el('customer-search-quick-name')!.value, s.el('customer-search-quick-phone')!.value]).toEqual(['', '600 111 222']);
    await s.click('customer-search-quick-cancel');
    await s.type('customer-picker-search', 'Marta');
    await s.click('customer-search-quick-add');
    expect([s.el('customer-search-quick-name')!.value, s.el('customer-search-quick-phone')!.value]).toEqual(['Marta', '']);
  });

  it('«Create and assign» waits for a name, creates the card (walk-in) and assigns it', async () => {
    const s = await setup(null, undefined, true);
    await s.results([]);
    await s.type('customer-picker-search', 'Marta');
    await s.click('customer-search-quick-add');
    await s.type('customer-search-quick-phone', '600 999 888');
    s.net.onApi((call) =>
      sent(call).path.endsWith('/by_phone') ? json({ rows: [] }) : json({ ...DETAIL, id: 'c9', name: 'Marta', company_name: '', tax_id: '', address: '', city: '', postal_code: '', country: '' }, 201),
    );
    await s.click('customer-search-quick-submit');
    expect(s.net.api.map((c) => sent(c).path)).toEqual(['/api/customer/customers/by_phone', '/api/customer/customers']);
    expect(sent(s.net.api[1]).body).toEqual({ name: 'Marta', phone: '600 999 888', source: 'walk_in' });
    expect(s.value.value).toEqual({
      customer_id: 'c9',
      customer_name: 'Marta',
      display_name: 'Marta',
      customer_tax_id: '',
      customer_address: '',
      customer_country: '',
    });
  });

  it('a phone that is already a live card\'s is shown and asked about: nothing is assigned until a choice (F12, F18)', async () => {
    const s = await setup(null, undefined, true);
    await s.results([]);
    await s.type('customer-picker-search', '600 111 222');
    await s.click('customer-search-quick-add');
    await s.type('customer-search-quick-name', 'Marta López');
    s.net.onApi((call) =>
      sent(call).path.endsWith('/by_phone')
        ? json({ rows: [{ id: 'c1', name: 'Ana García', email: '', phone: '+34600111222' }] })
        : json(DETAIL),
    );
    await s.click('customer-search-quick-submit');
    expect(s.net.api.map((c) => sent(c).path)).toEqual(['/api/customer/customers/by_phone']);
    expect(s.value.value).toBeNull();
    expect(s.el('customer-search-phone-taken')!.textContent).toContain(
      'There is already Ana García with this phone. Use that card or create a new one?',
    );
    await s.click('customer-search-use-c1');
    expect(s.net.api.map((c) => sent(c).path)).toEqual(['/api/customer/customers/by_phone', '/api/customer/customers/detail']);
    expect(s.value.value).toEqual(SNAPSHOT);
  });

  it('«Create a new one» creates the card despite the shared phone (a mother and her daughter)', async () => {
    const s = await setup(null, undefined, true);
    await s.results([]);
    await s.type('customer-picker-search', 'Marta López');
    await s.click('customer-search-quick-add');
    await s.type('customer-search-quick-phone', '600 111 222');
    s.net.onApi((call) =>
      sent(call).path.endsWith('/by_phone')
        ? json({ rows: [{ id: 'c1', name: 'Ana García', email: '', phone: '+34600111222' }] })
        : json({ ...DETAIL, id: 'c9', name: 'Marta López', tax_id: '', address: '', city: '', postal_code: '', country: '' }, 201),
    );
    await s.click('customer-search-quick-submit');
    await s.click('customer-search-create-anyway');
    expect(sent(s.net.api.at(-1)!)).toMatchObject({ path: '/api/customer/customers', body: { name: 'Marta López', phone: '600 111 222' } });
    expect(s.value.value?.customer_id).toBe('c9');
  });

  it('with several cards on that phone, lists them all to choose', async () => {
    const s = await setup(null, undefined, true);
    await s.results([]);
    await s.type('customer-picker-search', '600 111 222');
    await s.click('customer-search-quick-add');
    await s.type('customer-search-quick-name', 'Marta');
    s.net.onApi(() =>
      json({
        rows: [
          { id: 'c1', name: 'Ana García', email: '', phone: '+34600111222' },
          { id: 'c2', name: 'Lucía García', email: '', phone: '+34600111222' },
        ],
      }),
    );
    await s.click('customer-search-quick-submit');
    expect(s.el('customer-search-phone-taken')!.textContent).toContain(
      'These customers already have this phone. Use one of them or create a new one?',
    );
    expect([s.el('customer-search-use-c1'), s.el('customer-search-use-c2')].map((b) => b?.textContent?.trim())).toEqual([
      'Use Ana García',
      'Use Lucía García',
    ]);
    expect(s.value.value).toBeNull();
  });

  it('a phone that is not one of its country is said inside the form', async () => {
    const s = await setup(null, undefined, true);
    await s.results([]);
    await s.type('customer-picker-search', 'Marta');
    await s.click('customer-search-quick-add');
    await s.type('customer-search-quick-phone', '600111');
    s.net.onApi((call) =>
      sent(call).path.endsWith('/by_phone') ? json({ rows: [] }) : refusal(422, 'customer.phone_invalid', PHONE_INVALID, { phone: PHONE_INVALID }),
    );
    await s.click('customer-search-quick-submit');
    expect(s.el('customer-search-quick-phone')!.errorText).toBe(PHONE_INVALID);
    expect(s.value.value).toBeNull();
  });

  it('who cannot manage cards is not offered to create one', async () => {
    const s = await setup(null, { ...EMPLOYEE, permissions: ['customer.view'] }, true);
    await s.results([]);
    await s.type('customer-picker-search', 'Marta');
    expect(s.el('customer-search-quick-add')).toBeNull();
    document.body.innerHTML = '';
    const viewer = await setup(null, VIEWER, true);
    expect(viewer.el('customer-search-quick-add')).toBeNull();
  });
});

describe('CustomerSearch: markup', () => {
  it('has no OutfitKit tag and every filled control declares mode="md"', () => {
    expect(source).not.toMatch(/<ok[-]/);
    for (const tag of source.match(/<ion-(input|select|textarea)\b[^>]*>/gs) ?? []) if (/fill=/.test(tag)) expect(tag).toMatch(/mode="md"/);
  });
});
