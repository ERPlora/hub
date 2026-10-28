// SERVICE-F12, F13: «New package» asks for Name, Discount type (Percentage or Fixed amount) and its
// value, Closed price, Validity (days) and Uses (each with its help), and «Services included»: a row per
// service with its Sessions, «Remove line» and «Add service»; «Create package» needs a name and a line.
// «Editing package — {name}» changes everything but the lines (they cannot change once created) and
// sends only what changed; empty validity, uses or closed price remove them.
import { Combo, InlineFeedback } from '@erplora/ui/components';
import { describe, expect, it, vi } from 'vitest';

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

// flow service-business-currency: a voucher's closed price and its amount off are the business's currency.
describe('PackageFormModal: in the business currency (service-business-currency)', () => {
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
