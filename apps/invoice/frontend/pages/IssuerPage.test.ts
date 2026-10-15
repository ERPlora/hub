// Invoicing → Issuer (INVOICE-F21, F22): the business's tax identity that every new invoice carries —
// Legal name, Tax ID, Address, Postal code, City, Province and Country — followed live, with «Without the
// issuer no invoice can be issued.» until it is complete and, when the ERPlora account sent it, when. The
// owner and the admin save it (`invoice.issuer.update`); a refusal goes under its field; anyone else only
// looks.
import { toastSuccess } from '@erplora/ui/shell';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { click, errorFrame, flush, ionValue, MANAGER, type MountOptions, mountInvoice } from '../__tests__/mount-invoice';
import type { IssuerOut } from '../operations';
import IssuerPage from './IssuerPage.vue';

vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...((await importOriginal()) as object),
  toastSuccess: vi.fn(() => Promise.resolve()),
}));
beforeEach(() => vi.mocked(toastSuccess).mockClear());

const OP = 'invoice.issuer.get';
const prop = (el: Element | null, name: string): unknown => (el as unknown as Record<string, unknown>)[name];

const EMPTY: IssuerOut = {
  configured: false,
  legal_name: '',
  tax_id: '',
  address: '',
  postal_code: '',
  city: '',
  province: '',
  country: 'ES',
  address_line: '',
  source: 'manual',
  synced_version: null,
  synced_at: null,
  updated_at: null,
};
const SET: IssuerOut = { ...EMPTY, configured: true, legal_name: 'Peluquería Ana SL', tax_id: 'B12345674', address: 'Calle Mayor 1', city: 'Madrid' };

async function setup(options: MountOptions = {}) {
  const m = await mountInvoice(IssuerPage, { path: '/invoice/issuer', ...options });
  const call = await m.live();
  const field = (key: string) => m.find(`invoice-issuer-${key}`).element;
  return { ...m, call, field };
}

describe('IssuerPage', () => {
  it('follows invoice.issuer.get and says that without it nothing is issued', async () => {
    const s = await setup();
    expect(s.params(OP)).toEqual([{}]);
    await s.result(OP, EMPTY);
    expect(s.find('invoice-issuer-missing').text()).toBe('Without the issuer no invoice can be issued.');
    expect(['legal-name', 'tax-id', 'address', 'postal-code', 'city', 'province', 'country'].map((key) => prop(s.field(key), 'label'))).toEqual([
      'Legal name',
      'Tax ID',
      'Address',
      'Postal code',
      'City',
      'Province',
      'Country',
    ]);
    expect(prop(s.field('country'), 'value')).toBe('ES');
    // What VeriFactu's record holds: NombreRazonEmisor 120, the NIF 9 (20 for a document abroad).
    expect([prop(s.field('legal-name'), 'maxlength'), prop(s.field('tax-id'), 'maxlength')]).toEqual([120, 20]);
  });

  it('paints what is saved, and when the account sent it', async () => {
    const s = await setup();
    await s.result(OP, { ...SET, source: 'saas', synced_at: '2026-10-14T10:00:00Z', synced_version: 3 });
    expect([prop(s.field('legal-name'), 'value'), prop(s.field('tax-id'), 'value'), prop(s.field('city'), 'value')]).toEqual(['Peluquería Ana SL', 'B12345674', 'Madrid']);
    expect(s.find('invoice-issuer-missing').exists()).toBe(false);
    expect(s.find('invoice-issuer-from-saas').text()).toContain('Received from your ERPlora account on');
  });

  it('the owner saves it and is told so', async () => {
    const s = await setup();
    await s.result(OP, SET);
    await ionValue(s.field('province'), 'Madrid', 'ionInput');
    s.answer(200, { ...SET, province: 'Madrid' });
    await click(s.find('invoice-issuer-save').element);
    expect(s.sent()).toEqual([
      {
        method: 'POST',
        path: '/api/invoice/issuer',
        query: {},
        body: { legal_name: 'Peluquería Ana SL', tax_id: 'B12345674', address: 'Calle Mayor 1', postal_code: '', city: 'Madrid', province: 'Madrid', country: 'ES' },
      },
    ]);
    expect(toastSuccess).toHaveBeenCalledWith('Issuer saved.');
  });

  it('a refusal goes under its field', async () => {
    const s = await setup();
    await s.result(OP, SET);
    s.answer(422, { error: { code: 'invalid_payload', message: 'Invalid payload', fields: { tax_id: 'That tax ID is not valid.' } } });
    await click(s.find('invoice-issuer-save').element);
    await flush();
    expect(prop(s.field('tax-id'), 'errorText')).toBe('That tax ID is not valid.');
  });

  it('a manager only looks', async () => {
    const s = await setup({ session: MANAGER });
    await s.result(OP, SET);
    expect(s.find('invoice-issuer-readonly').text()).toBe('You can look at the issuer but not change it.');
    expect(prop(s.field('legal-name'), 'readonly')).toBe(true);
    expect(s.find('invoice-issuer-save').exists()).toBe(false);
  });

  it('an error says it could not be loaded', async () => {
    const s = await setup();
    s.call.push(errorFrame(s.subId(OP), 'invoice.boom'));
    await flush();
    expect(s.find('invoice-issuer-load-error').text()).toContain('The issuer could not be loaded');
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    await s.result(OP, EMPTY);
    expect(s.find('invoice-issuer-missing').text()).toBe('Sin el emisor no se puede emitir ninguna factura.');
    expect(prop(s.field('legal-name'), 'label')).toBe('Razón social');
    expect(s.find('invoice-issuer-save').text()).toBe('Guardar');
  });
});
