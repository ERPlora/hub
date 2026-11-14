// SERVICE-F12, F13: «New package» asks for Name, Discount type (Percentage or Fixed amount) and its
// value, Closed price, Validity (days) and Uses (each with its help), and «Services included»: a row per
// service with its Sessions, «Remove line» and «Add service»; «Create package» needs a name and a line.
// «Editing package — {name}» changes everything but the lines (they cannot change once created) and
// sends only what changed; empty validity, uses or closed price remove them.
import { Combo, InlineFeedback } from '@erplora/ui/components';
import { describe, expect, it, vi } from 'vitest';

import {
  expectAmountLeftWaitsForMoney,
  expectSaveWaitsForMoney,
  expectWindowSaysMoneyUnreadable,
} from '../../../../base/frontend/__tests__/save-waits-for-money';
import { itTellsTheCorrectedFieldApart } from '../../../../base/frontend/__tests__/same-words-refusal';
import { business, click, ionValue, JAPANESE, type MountOptions, mountService, POLISH, settle } from '../__tests__/mount-service';
import { PACKAGE, pkg } from '../__tests__/package';
import PackageFormModal from './PackageFormModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

type Control = HTMLElement & { label?: string; value?: unknown; errorText?: string; disabled?: boolean; helperText?: string };

async function setup(current: typeof PACKAGE | null = null, locale: 'en' | 'es' = 'en', options: MountOptions = {}) {
  const m = await mountService(PackageFormModal, { props: { open: false, pkg: current }, locale, path: '/service/packages', ...options });
  await m.wrapper.setProps({ 'onUpdate:open': (open: boolean) => m.wrapper.setProps({ open }) });
  await m.wrapper.setProps({ open: true });
  await settle();
  await m.live();
  const field = (name: string) => m.inDoc(`service-package-form-${name}`) as Control;
  const save = () => m.inDoc('service-package-form-submit') as Control;
  const lines = () => m.wrapper.findAllComponents(Combo);
  return { ...m, field, save, lines };
}

describe('PackageFormModal: New package', () => {
  it('asks for the old panel’s fields with their help, and a first empty line', async () => {
    const s = await setup();
    expect(s.inDoc('service-package-form')?.getAttribute('aria-label')).toBe('New package');
    expect([s.field('name').label, s.field('discount_type').label, s.field('discount_percent').label]).toEqual([
      'Name',
      'Discount type',
      'Discount (%)',
    ]);
    expect([s.field('fixed_price').label, s.field('fixed_price').helperText]).toEqual([
      'Closed price (EUR)',
      'Leave empty to price it as the sum of its lines minus the discount.',
    ]);
    expect([s.field('validity_days').helperText, s.field('max_uses').helperText]).toEqual([
      'Days redeemable from the purchase; empty = never expires.',
      'Uses the voucher grants; empty = unlimited.',
    ]);
    expect(s.lines().map((line) => line.props('label'))).toEqual(['Service']);
    expect(s.save().textContent).toContain('Create package');
    expect(s.save().disabled).toBe(true);
    const banner = s.wrapper.findAllComponents(InlineFeedback).find((b) => b.attributes('data-testid') === 'service-package-form-no-lines');
    expect(banner?.text()).toContain('Add at least one service: a package with no lines cannot be redeemed.');
  });

  it('creates the package with its lines, the discount in basis points and the money in cents', async () => {
    const s = await setup();
    s.answer(201, PACKAGE);
    await ionValue(s.field('name'), ' Bono 5 cortes ', 'ionInput');
    await ionValue(s.field('discount_percent'), '10,5', 'ionInput');
    await ionValue(s.field('fixed_price'), '90', 'ionInput');
    await ionValue(s.field('validity_days'), '180', 'ionInput');
    await ionValue(s.field('max_uses'), '5', 'ionInput');
    s.lines()[0].vm.$emit('update:modelValue', { id: 's1', label: 'Cut' });
    await settle();
    await ionValue(s.field('line-sessions-0'), '5', 'ionInput');
    await click(s.field('add-line'));
    s.lines()[1].vm.$emit('update:modelValue', { id: 's2', label: 'Colour' });
    await settle();
    await click(s.save());
    expect(s.sent()).toEqual([
      {
        method: 'POST',
        path: '/api/service/packages',
        query: {},
        body: {
          name: 'Bono 5 cortes',
          discount_type: 'percentage',
          discount_percent_bp: 1050,
          fixed_price: 9000,
          validity_days: 180,
          max_uses: 5,
          items: [
            { service_id: 's1', sessions: 5 },
            { service_id: 's2', sessions: 1 },
          ],
        },
      },
    ]);
    expect(s.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
  });

  it('a fixed discount is an amount; a line is removed with «Remove line»', async () => {
    const s = await setup();
    s.answer(201, PACKAGE);
    await ionValue(s.field('name'), 'Bono', 'ionInput');
    await ionValue(s.field('discount_type'), 'fixed', 'ionChange');
    expect(s.field('discount_amount').label).toBe('Discount (EUR)');
    await ionValue(s.field('discount_amount'), '5', 'ionInput');
    await click(s.field('add-line'));
    s.lines()[1].vm.$emit('update:modelValue', { id: 's2', label: 'Colour' });
    await settle();
    await click(s.field('remove-line-0'));
    await click(s.save());
    expect(s.sent()[0].body).toEqual({
      name: 'Bono',
      discount_type: 'fixed',
      discount_amount: 500,
      fixed_price: null,
      validity_days: null,
      max_uses: null,
      items: [{ service_id: 's2', sessions: 1 }],
    });
  });

  it('a discount that is not a percentage says so and nothing is sent', async () => {
    const s = await setup();
    await ionValue(s.field('name'), 'Bono', 'ionInput');
    await ionValue(s.field('discount_percent'), '120', 'ionInput');
    s.lines()[0].vm.$emit('update:modelValue', { id: 's1', label: 'Cut' });
    await settle();
    await click(s.save());
    expect(s.sent()).toEqual([]);
    expect(s.field('discount_percent').errorText).toBe('Type a percentage from 0 to 100, with at most two decimals.');
  });

  it('a refusal of a line goes under the line that was sent, empty lines aside', async () => {
    const s = await setup();
    const message = 'That service is archived: it cannot go into a voucher.';
    s.answer(422, { error: { code: 'invalid_payload', message: 'Invalid payload', fields: { 'items.1.service_id': message, 'items.0.sessions': 'Too many.' } } });
    await ionValue(s.field('name'), 'Bono', 'ionInput');
    await click(s.field('add-line'));
    await click(s.field('add-line'));
    s.lines()[1].vm.$emit('update:modelValue', { id: 's1', label: 'Cut' });
    s.lines()[2].vm.$emit('update:modelValue', { id: 's2', label: 'Perm' });
    await settle();
    await click(s.save());
    expect(s.sent()[0].body).toMatchObject({ items: [{ service_id: 's1', sessions: 1 }, { service_id: 's2', sessions: 1 }] });
    expect(s.lines().map((line) => line.props('errorText'))).toEqual([undefined, undefined, message]);
    expect([s.field('line-sessions-0').errorText, s.field('line-sessions-1').errorText]).toEqual([undefined, 'Too many.']);
  });

  it('a name already taken goes under Name', async () => {
    const s = await setup();
    const message = 'There is already a package with that name. Pick another name.';
    s.answer(409, { error: { code: 'service.package_name_taken', message, fields: { name: message } } });
    await ionValue(s.field('name'), 'Bono', 'ionInput');
    s.lines()[0].vm.$emit('update:modelValue', { id: 's1', label: 'Cut' });
    await settle();
    await click(s.save());
    expect(s.field('name').errorText).toBe(message);
  });
});

describe('PackageFormModal: fields refused with the same words (hub#888)', () => {
  // Name, the discount, Closed price, Validity, Uses and a line's service (the picker) and Sessions each paint a refusal
  // under their own key; a line's are named after its place in what was sent.
  const FIELD_OF: Record<string, string> = {
    discount_percent_bp: 'discount_percent',
    'items.0.service_id': 'line-service-0',
    'items.0.sessions': 'line-sessions-0',
  };
  async function filled(locale: 'en' | 'es', refusal: unknown, discount: (s: Awaited<ReturnType<typeof setup>>) => Promise<void>) {
    const s = await setup(null, locale);
    await ionValue(s.field('name'), 'Bono', 'ionInput');
    await discount(s);
    await ionValue(s.field('fixed_price'), '90', 'ionInput');
    await ionValue(s.field('validity_days'), '180', 'ionInput');
    await ionValue(s.field('max_uses'), '5', 'ionInput');
    s.lines()[0].vm.$emit('update:modelValue', { id: 's1', label: 'Cut' });
    await settle();
    s.answer(422, refusal);
    return { field: (key: string) => s.field(FIELD_OF[key] ?? key), send: () => click(s.save()), settle };
  }

  itTellsTheCorrectedFieldApart(
    ['name', 'discount_percent_bp', 'fixed_price', 'validity_days', 'max_uses', 'items.0.service_id', 'items.0.sessions'],
    (locale, refusal) => filled(locale, refusal, (s) => ionValue(s.field('discount_percent'), '5', 'ionInput')),
    'fixed_price',
  );

  describe('with a fixed discount', () => {
    itTellsTheCorrectedFieldApart(['discount_amount', 'fixed_price', 'max_uses'], (locale, refusal) =>
      filled(locale, refusal, async (s) => {
        await ionValue(s.field('discount_type'), 'fixed', 'ionChange');
        await ionValue(s.field('discount_amount'), '5', 'ionInput');
      }),
    );
  });
});

// The server refuses the lines as a whole (a service twice) on the line under them, not under one line: any change the
// person makes to the lines takes that line away at once, and only that line (hub#888).
describe('PackageFormModal: a refusal of the lines as a whole', () => {
  const REPEATED = 'A service is repeated in the lines: each service goes once.';
  const NAME_TAKEN = 'There is already a package with that name. Pick another name.';

  async function refusedLines(fields: Record<string, string> = { items: REPEATED }) {
    const s = await setup();
    await ionValue(s.field('name'), 'Bono', 'ionInput');
    s.lines()[0].vm.$emit('update:modelValue', { id: 's1', label: 'Cut' });
    await click(s.field('add-line'));
    s.lines()[1].vm.$emit('update:modelValue', { id: 's1', label: 'Cut' });
    await settle();
    s.answer(422, { error: { code: 'invalid_payload', message: 'Check the fields.', fields } });
    await click(s.save());
    const said = () => s.inDoc('service-package-form-no-lines')?.textContent ?? '';
    return { ...s, said };
  }

  const CHANGES: [string, (s: Awaited<ReturnType<typeof refusedLines>>) => Promise<void>][] = [
    ['choosing a line’s service', async (s) => {
      s.lines()[1].vm.$emit('update:modelValue', { id: 's2', label: 'Colour' });
      await settle();
    }],
    ['typing a line’s sessions', (s) => ionValue(s.field('line-sessions-1'), '3', 'ionInput')],
    ['removing a line', (s) => click(s.field('remove-line-1'))],
    ['adding a line', (s) => click(s.field('add-line'))],
  ];

  it.each(CHANGES)('%s takes it away before saving again', async (_, change) => {
    const s = await refusedLines();
    expect(s.said()).toContain(REPEATED);
    await change(s);
    expect(s.said()).not.toContain(REPEATED);
    expect(s.sent()).toHaveLength(1);
  });

  it('a change to the lines leaves another field’s refusal under it', async () => {
    const s = await refusedLines({ name: NAME_TAKEN, items: REPEATED });
    await ionValue(s.field('line-sessions-1'), '3', 'ionInput');
    expect([s.field('name').errorText, s.said().includes(REPEATED)]).toEqual([NAME_TAKEN, false]);
  });
});

// flow service-business-currency: a voucher's closed price and its amount off are the business's currency.
describe('PackageFormModal: in the business currency (service-business-currency)', () => {
  // SERVICE-F12, F13, hub#924: an amount off and a closed price are judged in the business's money: a euro one is no
  // złoty amount in Poland.
  it.each(['discount_amount', 'fixed_price'])('in Poland «13,50 €» in the %s says it is not an amount, and nothing is sent', async (name) => {
    const s = await setup(pkg({ discount_type: 'fixed', discount_percent_bp: 0, discount_amount: 500 }), 'en', { business: business(POLISH) });
    await ionValue(s.field(name), '13,50 €', 'ionInput');
    await click(s.save());
    expect([s.field(name).errorText, s.sent()]).toEqual(['This is not an amount. Type a figure, for example 12.50.', []]);
  });

  it('a business in Japan saves «9000» as a closed price of 9000 yen and «500» off as 500 yen', async () => {
    const s = await setup(null, 'en', { business: business(JAPANESE) });
    expect(s.field('fixed_price').label).toBe('Closed price (JPY)');
    s.answer(201, PACKAGE);
    await ionValue(s.field('name'), 'Bono', 'ionInput');
    await ionValue(s.field('discount_type'), 'fixed', 'ionChange');
    expect(s.field('discount_amount').label).toBe('Discount (JPY)');
    await ionValue(s.field('discount_amount'), '500', 'ionInput');
    await ionValue(s.field('fixed_price'), '9000', 'ionInput');
    s.lines()[0].vm.$emit('update:modelValue', { id: 's1', label: 'Cut' });
    await settle();
    await click(s.save());
    const [body] = s.sent().map((call) => call.body as { discount_amount: number; fixed_price: number });
    expect([body.discount_amount, body.fixed_price]).toEqual([500, 9000]);
  });

  it('a business in Poland edits the closed price in złoty', async () => {
    const s = await setup(PACKAGE, 'en', { business: business(POLISH) });
    expect([s.field('fixed_price').label, s.field('fixed_price').value]).toEqual(['Closed price (PLN)', '90.00']);
    s.answer(200, PACKAGE);
    await ionValue(s.field('fixed_price'), '95 zł', 'ionInput');
    await click(s.save());
    expect(s.sent().map((call) => call.body)).toEqual([{ id: 'p1', fixed_price: 9500 }]);
  });

  it('the business answers with the form open: the untouched closed price is rewritten in its decimals and not sent', async () => {
    const s = await setup({ ...PACKAGE, fixed_price: 9000 }, 'en', { business: null });
    expect([s.field('fixed_price').label, s.field('fixed_price').value]).toEqual(['Closed price', '90.00']);
    await s.result('base.business.get', business(JAPANESE));
    expect(s.field('fixed_price').value).toBe('9000');
    s.answer(200, PACKAGE);
    await ionValue(s.field('max_uses'), '10', 'ionInput');
    await click(s.save());
    expect(s.sent().map((call) => call.body)).toEqual([{ id: 'p1', max_uses: 10 }]);
  });

  // «1500» reads in any money, so alone it would not tell a guard put after the reading: «¥1500» is not an amount until
  // the money is known, and the field must not say so while the window waits.
  it.each(['1500', '¥1500'])(
    'a closed price typed before the business answers is never read without it: «Create package» waits in grey and the field says nothing, then «%s» is 1500 yen (hub#921)',
    async (typed) => {
      const s = await setup(null, 'en', { business: null });
      await ionValue(s.field('name'), 'Bono', 'ionInput');
      await ionValue(s.field('fixed_price'), typed, 'ionInput');
      s.lines()[0].vm.$emit('update:modelValue', { id: 's1', label: 'Cut' });
      await settle();
      s.answer(201, PACKAGE);
      await expectSaveWaitsForMoney({ ...s, amount: () => s.field('fixed_price'), settle }, () => s.result('base.business.get', business(JAPANESE)));
      expect([s.field('fixed_price').value, s.field('fixed_price').errorText]).toEqual([typed, undefined]);
      await click(s.save());
      expect(s.sent().map((call) => (call.body as { fixed_price: number }).fixed_price)).toEqual([1500]);
    },
  );

  it('editing, a closed price typed before the business answers stays as typed when it does and is read in yen (hub#921)', async () => {
    const s = await setup(PACKAGE, 'en', { business: null });
    await ionValue(s.field('fixed_price'), '1500', 'ionInput');
    s.answer(200, pkg({ fixed_price: 1500 }));
    await expectSaveWaitsForMoney({ ...s, amount: () => s.field('fixed_price'), settle }, () => s.result('base.business.get', business(JAPANESE)));
    expect(s.field('fixed_price').value).toBe('1500');
    await click(s.save());
    expect(s.sent().map((call) => call.body)).toEqual([{ id: 'p1', fixed_price: 1500 }]);
  });

  it('editing, an amount off typed before the business answers stays as typed when it does and is read in yen', async () => {
    const s = await setup(pkg({ discount_type: 'fixed', discount_percent_bp: 0, discount_amount: 500 }), 'en', { business: null });
    expect(s.field('discount_amount').value).toBe('5.00');
    await ionValue(s.field('discount_amount'), '700', 'ionInput');
    await s.result('base.business.get', business(JAPANESE));
    expect([s.field('discount_amount').value, s.field('fixed_price').value]).toEqual(['700', '9000']);
    s.answer(200, PACKAGE);
    await click(s.save());
    expect(s.sent().map((call) => call.body)).toEqual([{ id: 'p1', discount_amount: 700 }]);
  });

  // hub#945 (SERVICE-F12): a closed price or an amount off typed with its currency's sign and left before the business
  // answers is neither rewritten nor called «not an amount»; once it answers, it is read in its money.
  it.each([
    ['fixed_price', '¥9500', JAPANESE, 9500],
    ['discount_amount', '7,50 zł', POLISH, 750],
  ] as const)('the %s «%s» left before the business says its currency stays as typed and unmarked, then is read in it (hub#945)', async (name, typed, money, cents) => {
    const s = await setup(pkg({ discount_type: 'fixed', discount_percent_bp: 0, discount_amount: 500 }), 'en', { business: null });
    await expectAmountLeftWaitsForMoney({ amount: () => s.field(name), settle }, typed, () => s.result('base.business.get', business(money)));
    s.answer(200, PACKAGE);
    await click(s.save());
    expect(s.sent().map((call) => call.body)).toEqual([{ id: 'p1', [name]: cents }]);
  });
});

describe('PackageFormModal: Editing package — {name}', () => {
  it('is loaded, keeps its lines fixed and sends only what changed; empty removes a limit', async () => {
    const s = await setup(PACKAGE);
    expect(s.inDoc('service-package-form')?.getAttribute('aria-label')).toBe('Editing package — Bono 5 cortes');
    expect([s.field('name').value, s.field('discount_percent').value, s.field('fixed_price').value, s.field('validity_days').value, s.field('max_uses').value]).toEqual([
      'Bono 5 cortes',
      '10.5',
      '90.00',
      '180',
      '5',
    ]);
    expect(s.lines()).toHaveLength(0);
    expect(s.inDoc('service-package-form-lines-fixed')?.textContent).toContain(
      'The services included cannot be changed once created: delete this package and create a new one.',
    );
    expect(s.inDoc('service-package-form-lines')?.textContent).toContain('Cut × 5');
    s.answer(200, pkg({ max_uses: 10, validity_days: null }));
    await ionValue(s.field('max_uses'), '10', 'ionInput');
    await ionValue(s.field('validity_days'), '', 'ionInput');
    await click(s.save());
    expect(s.sent()).toEqual([
      { method: 'POST', path: '/api/service/packages/update', query: {}, body: { id: 'p1', validity_days: null, max_uses: 10 } },
    ]);
  });

  it('speaks Spanish', async () => {
    const s = await setup(PACKAGE, 'es');
    expect(s.inDoc('service-package-form')?.getAttribute('aria-label')).toBe('Editando paquete — Bono 5 cortes');
    expect(s.field('validity_days').label).toBe('Vigencia (días)');
    expect(s.field('discount_percent').value).toBe('10,5');
    // No word shouts in the help: «compra» as the old panel said it, not «COMPRA».
    expect(s.field('validity_days').helperText).toBe('Días canjeables desde la compra; vacío = no caduca.');
  });
});

// hub#938 (SERVICE-F12, F13): if the business's money cannot be read, the form says so with «Retry» instead of waiting in
// grey without a word, also when it opens after the read had failed (the page read the money on loading).
describe('PackageFormModal: a business whose money cannot be read (hub#938)', () => {
  it.each([false, true])('says so with «Retry»; once the yen arrives «Save» lights up (opened after the failure: %s)', async (late) => {
    const m = await mountService(PackageFormModal, { props: { open: !late, pkg: PACKAGE }, path: '/service/packages', business: null });
    await m.live();
    const opens = late ? () => m.wrapper.setProps({ open: true }) : undefined;
    await expectWindowSaysMoneyUnreadable(m, 'service-package-form-submit', m.sent, opens);
  });
});

describe('PackageFormModal: Android Back with unsaved changes (hub#1020, BASE-F05)', () => {
  it('as opened closes; a change asks; restored as opened closes again', async () => {
    const s = await setup();
    const { expectUnsavedFormAsksBeforeClosing } = await import('../../../../base/frontend/__tests__/unsaved-form');
    await expectUnsavedFormAsksBeforeClosing({
      overlay: () => s.inDoc('service-package-form'),
      change: () => ionValue(s.field('name'), 'Bono', 'ionInput'),
      restore: () => ionValue(s.field('name'), '', 'ionInput'),
    });
  });
});
