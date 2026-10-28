// SERVICE-F01, F02, F03: «New service» asks for Name, Pricing, Price, Duration (min), Category («No
// category» or one, searched) and Tax category (no empty option; the settings' default comes chosen),
// with «Create service», which cannot be pressed without a name and a tax category; with no tax
// category in Taxes at all it says where to make them. A row opens «Editing service — {name}» with
// «Save changes», which sends only what changed, and below it who performs the service.
import { Combo, InlineFeedback } from '@erplora/ui/components';
import { describe, expect, it, vi } from 'vitest';

import type { ServiceOut, SettingsOut } from '../operations';
import { business, click, ionValue, JAPANESE, type MountOptions, mountService, page, POLISH, settle } from '../__tests__/mount-service';
import ServiceFormModal from './ServiceFormModal.vue';
import ServiceProfessionals from './ServiceProfessionals.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

type Control = HTMLElement & { label?: string; value?: unknown; errorText?: string; disabled?: boolean };

const CUT: ServiceOut = {
  id: 's1',
  name: 'Cut',
  description: '',
  short_description: '',
  category_id: 'c1',
  category_name: 'Hair',
  pricing_type: 'fixed',
  price: 2000,
  min_price: null,
  max_price: null,
  cost: 0,
  duration_minutes: 30,
  buffer_before: 0,
  buffer_after: 0,
  max_capacity: 1,
  is_bookable: true,
  requires_confirmation: false,
  allow_online_booking: true,
  sort_order: 0,
  is_featured: false,
  sku: '',
  barcode: '',
  notes: '',
  tax_category_id: 't1',
  tax_category_key: 'service.generic',
  tax_category_name: 'Service — generic',
  needs_tax_setup: false,
  status: 'active',
  is_active: true,
  archived_at: null,
  created_at: '2026-10-01T10:00:00Z',
  updated_at: '2026-10-01T10:00:00Z',
};
const SETTINGS: SettingsOut = {
  default_duration: 60,
  default_buffer_time: 0,
  default_tax_category_id: 't1',
  default_tax_category_key: 'service.generic',
  default_tax_category_name: 'Service — generic',
  show_prices: true,
  show_duration: true,
  allow_online_booking: true,
  updated_at: null,
};

async function setup(service: ServiceOut | null = null, locale: 'en' | 'es' = 'en', canChange = true, options: MountOptions = {}) {
  const m = await mountService(ServiceFormModal, { props: { open: false, service, canChange }, locale, ...options });
  await m.wrapper.setProps({ 'onUpdate:open': (open: boolean) => m.wrapper.setProps({ open }) });
  await m.wrapper.setProps({ open: true });
  await settle();
  await m.live();
  const field = (name: string) => m.inDoc(`service-form-${name}`) as Control;
  const save = () => m.inDoc('service-form-submit') as Control;
  const combo = (testid: string) =>
    m.wrapper.findAllComponents(Combo).find((c) => c.props('testid') === testid)!;
  return { ...m, field, save, combo };
}

describe('ServiceFormModal: New service', () => {
  it('asks for the old panel’s fields, the settings’ tax category chosen, and Create service', async () => {
    const s = await setup();
    await s.result('service.settings.get', SETTINGS);
    await s.result('tax.category.list', page([{ key: 'service.generic' }], 11, 1));
    expect(s.inDoc('service-form')?.getAttribute('aria-label')).toBe('New service');
    expect([s.field('name').label, s.field('pricing_type').label, s.field('price').label, s.field('duration').label]).toEqual([
      'Name',
      'Pricing',
      'Price (EUR)',
      'Duration (min)',
    ]);
    expect([s.combo('service-form-category').props('label'), s.combo('service-form-category').props('placeholder')]).toEqual([
      'Category',
      'No category',
    ]);
    expect([s.combo('service-form-tax').props('label'), s.combo('service-form-tax').props('modelValue')]).toEqual([
      'Tax category',
      { id: 'service.generic', label: 'Service — generic' },
    ]);
    expect(s.field('pricing_type').value).toBe('fixed');
    expect(s.save().textContent).toContain('Create service');
    expect(s.wrapper.findComponent(ServiceProfessionals).exists()).toBe(false);
  });

  it('creates the service with the price in cents and the duration typed, and closes', async () => {
    const s = await setup();
    await s.result('service.settings.get', SETTINGS);
    s.answer(201, CUT);
    await ionValue(s.field('name'), ' Haircut ', 'ionInput');
    await ionValue(s.field('pricing_type'), 'from', 'ionChange');
    await ionValue(s.field('price'), '22,50', 'ionInput');
    await ionValue(s.field('duration'), '30', 'ionInput');
    s.combo('service-form-category').vm.$emit('update:modelValue', { id: 'c1', label: 'Hair' });
    await settle();
    await click(s.save());
    expect(s.sent()).toEqual([
      {
        method: 'POST',
        path: '/api/service/services',
        query: {},
        body: { name: 'Haircut', pricing_type: 'from', price: 2250, duration_minutes: 30, category_id: 'c1', tax_category_key: 'service.generic' },
      },
    ]);
    expect(s.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
  });

  it('cannot be created without a tax category, and says where to make them when Taxes has none', async () => {
    const s = await setup();
    await s.result('service.settings.get', { ...SETTINGS, default_tax_category_key: null, default_tax_category_name: null });
    await s.result('tax.category.list', page([], 0, 1));
    await ionValue(s.field('name'), 'Cut', 'ionInput');
    expect(s.save().disabled).toBe(true);
    const banner = s.wrapper.findAllComponents(InlineFeedback).find((b) => b.attributes('data-testid') === 'service-form-tax-missing');
    expect(banner?.text()).toContain('There are no tax categories yet. Set them up in Taxes before adding services.');
  });

  it('a price that is not an amount is said under the field and nothing is sent', async () => {
    const s = await setup();
    await s.result('service.settings.get', SETTINGS);
    await ionValue(s.field('name'), 'Cut', 'ionInput');
    await ionValue(s.field('price'), 'abc', 'ionInput');
    await click(s.save());
    expect(s.sent()).toEqual([]);
    expect(s.field('price').errorText).toBe('This is not an amount. Type a figure, for example 12.50.');
  });

  it('a refusal of the server goes under its field', async () => {
    const s = await setup();
    await s.result('service.settings.get', SETTINGS);
    const message = 'That category is not available: it does not exist in this business or it has been deleted.';
    s.answer(422, { error: { code: 'service.category_unavailable', message, fields: { category_id: message } } });
    await ionValue(s.field('name'), 'Cut', 'ionInput');
    await click(s.save());
    expect(s.combo('service-form-category').props('errorText')).toBe(message);
  });
});

describe('ServiceFormModal: Editing service — {name}', () => {
  it('is named after the service, loaded, and saves only what changed', async () => {
    const s = await setup(CUT);
    expect(s.inDoc('service-form')?.getAttribute('aria-label')).toBe('Editing service — Cut');
    expect([s.field('name').value, s.field('price').value, s.field('duration').value]).toEqual(['Cut', '20.00', '30']);
    expect(s.combo('service-form-category').props('modelValue')).toEqual({ id: 'c1', label: 'Hair' });
    expect(s.save().textContent).toContain('Save changes');
    s.answer(200, CUT);
    await ionValue(s.field('price'), '24', 'ionInput');
    s.combo('service-form-category').vm.$emit('update:modelValue', null);
    await settle();
    await click(s.save());
    expect(s.sent()).toEqual([
      { method: 'POST', path: '/api/service/services/update', query: {}, body: { id: 's1', price: 2400, category_id: null } },
    ]);
  });

  it('shows who performs the service below the form', async () => {
    const s = await setup(CUT);
    expect(s.wrapper.findComponent(ServiceProfessionals).props()).toEqual({ serviceId: 's1', canChange: true });
  });

  it('speaks Spanish', async () => {
    const s = await setup(CUT, 'es');
    expect(s.inDoc('service-form')?.getAttribute('aria-label')).toBe('Editando servicio — Cut');
    expect([s.field('pricing_type').label, s.field('price').label, s.combo('service-form-category').props('placeholder')]).toEqual([
      'Tarifa',
      'Precio (EUR)',
      'Sin categoría',
    ]);
    expect(s.save().textContent).toContain('Guardar cambios');
  });
});

// flow service-business-currency: the price is typed, read and saved in the business's currency (its country's),
// in its minor units: «1500» is 1500 yen in Japan, as Sales then charges it; never a euro fixed in the app.
describe('ServiceFormModal: in the business currency (service-business-currency)', () => {
  it('a business in Japan types «1500» and the service is saved at 1500 yen, under «Price (JPY)»', async () => {
    const s = await setup(null, 'en', true, { business: business(JAPANESE) });
    await s.result('service.settings.get', SETTINGS);
    s.answer(201, CUT);
    expect(s.field('price').label).toBe('Price (JPY)');
    await ionValue(s.field('name'), 'Haircut', 'ionInput');
    await ionValue(s.field('price'), '1500', 'ionInput');
    await click(s.save());
    expect(s.sent().map((call) => (call.body as { price: number }).price)).toEqual([1500]);
  });

  it('a business in Poland edits the price in złoty: «24,50 zł» is 2450 grosze', async () => {
    const s = await setup(CUT, 'en', true, { business: business(POLISH) });
    expect([s.field('price').label, s.field('price').value]).toEqual(['Price (PLN)', '20.00']);
    s.answer(200, CUT);
    await ionValue(s.field('price'), '24,50 zł', 'ionInput');
    await click(s.save());
    expect(s.sent().map((call) => call.body)).toEqual([{ id: 's1', price: 2450 }]);
  });

  it('a price in another currency’s sign is not an amount and nothing is sent', async () => {
    const s = await setup(CUT, 'en', true, { business: business(POLISH) });
    await ionValue(s.field('price'), '24,50 €', 'ionInput');
    await click(s.save());
    expect(s.sent()).toEqual([]);
    expect(s.field('price').errorText).toBe('This is not an amount. Type a figure, for example 12.50.');
  });

  it('says «Price» without a code until the business answers', async () => {
    const s = await setup(null, 'en', true, { business: null });
    expect(s.field('price').label).toBe('Price');
  });

  it('the business answers with the form open: the untouched price is rewritten in its decimals and not sent', async () => {
    const s = await setup({ ...CUT, price: 1500 }, 'en', true, { business: null });
    expect(s.field('price').value).toBe('15.00');
    await s.result('base.business.get', business(JAPANESE));
    expect(s.field('price').value).toBe('1500');
    s.answer(200, CUT);
    await ionValue(s.field('name'), 'Cut and wash', 'ionInput');
    await click(s.save());
    expect(s.sent().map((call) => call.body)).toEqual([{ id: 's1', name: 'Cut and wash' }]);
  });

  it('what was typed before the business answered stays as typed and is read in its currency', async () => {
    const s = await setup(null, 'en', true, { business: null });
    await s.result('service.settings.get', SETTINGS);
    await ionValue(s.field('name'), 'Haircut', 'ionInput');
    await ionValue(s.field('price'), '1500', 'ionInput');
    await s.result('base.business.get', business(JAPANESE));
    expect(s.field('price').value).toBe('1500');
    s.answer(201, CUT);
    await click(s.save());
    expect(s.sent().map((call) => (call.body as { price: number }).price)).toEqual([1500]);
  });
});

describe('ServiceFormModal: two rows opened one after the other', () => {
  it('shows the second one, never what was left of the first (pm#459)', async () => {
    const s = await setup(CUT);
    expect(s.field('name').value).toBe('Cut');
    await s.wrapper.setProps({ service: { ...CUT, id: 's2', name: 'Beard', price: 1200, duration_minutes: 15 } });
    await settle();
    expect([s.field('name').value, s.field('duration').value]).toEqual(['Beard', '15']);
  });
});
