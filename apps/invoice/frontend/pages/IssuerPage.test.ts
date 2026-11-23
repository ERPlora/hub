// Invoicing → Issuer (INVOICE-F21, F22): the business's tax identity that every new invoice carries —
// Legal name, Tax ID, Address, Postal code, City, Province, Country and whether it is registered for intra-EU
// operations (ROI), which makes its documents print its EU VAT number — followed live, with «Without the
// issuer no invoice can be issued.» until it is complete and, when the ERPlora account sent it, when. The
// owner and the admin save it (`invoice.issuer.update`); a refusal goes under its field; anyone else only
// looks.
import { toastSuccess } from '@erplora/ui/shell';
import { describe, expect, it } from 'vitest';

import { click, errorFrame, flush, ionChecked, ionValue, MANAGER, type MountOptions, mountInvoice } from '../__tests__/mount-invoice';
import type { IssuerOut } from '../operations';
import IssuerPage from './IssuerPage.vue';

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
  intra_eu_operator: false,
  vat_number: '',
};
const SET: IssuerOut = { ...EMPTY, configured: true, legal_name: 'Peluquería Ana SL', tax_id: 'B12345674', vat_number: 'B12345674', address: 'Calle Mayor 1', city: 'Madrid' };

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
        body: { legal_name: 'Peluquería Ana SL', tax_id: 'B12345674', address: 'Calle Mayor 1', postal_code: '', city: 'Madrid', province: 'Madrid', country: 'ES', intra_eu_operator: false },
      },
    ]);
    expect(toastSuccess).toHaveBeenCalledWith('Issuer saved.');
  });

  describe('registered for intra-EU operations (ROI)', () => {
    const toggle = (s: Awaited<ReturnType<typeof setup>>) => s.field('intra-eu-operator');

    it('is off until the business says so, and says what it changes', async () => {
      const s = await setup();
      await s.result(OP, SET);
      expect(prop(toggle(s), 'checked')).toBe(false);
      expect(toggle(s).textContent?.trim()).toBe('Registered in the ROI (intra-EU operations)');
      expect(prop(toggle(s), 'helperText')).toBe(
        'Your invoices and tickets will print your tax ID with your country’s prefix (ES…). VeriFactu keeps receiving it without the prefix.',
      );
    });

    it('paints the saved mark', async () => {
      const s = await setup();
      await s.result(OP, { ...SET, intra_eu_operator: true, vat_number: 'ESB12345674' });
      expect(prop(toggle(s), 'checked')).toBe(true);
    });

    it('turned on, it is saved with the rest of the issuer', async () => {
      const s = await setup();
      await s.result(OP, SET);
      await ionChecked(toggle(s), true);
      s.answer(200, { ...SET, intra_eu_operator: true, vat_number: 'ESB12345674' });
      await click(s.find('invoice-issuer-save').element);
      expect(s.sent()[0]?.body).toMatchObject({ tax_id: 'B12345674', intra_eu_operator: true });
      expect(prop(toggle(s), 'checked')).toBe(true);
    });

    it('a manager only looks at it', async () => {
      const s = await setup({ session: MANAGER });
      await s.result(OP, { ...SET, intra_eu_operator: true, vat_number: 'ESB12345674' });
      expect([prop(toggle(s), 'checked'), prop(toggle(s), 'disabled')]).toEqual([true, true]);
    });

    it('speaks Spanish', async () => {
      const s = await setup({ locale: 'es' });
      await s.result(OP, SET);
      expect(toggle(s).textContent?.trim()).toBe('Inscrito en el ROI (operaciones intracomunitarias)');
      expect(prop(toggle(s), 'helperText')).toBe(
        'Tus facturas y tiques imprimirán tu NIF con el prefijo de tu país (ES…). VeriFactu lo sigue recibiendo sin prefijo.',
      );
    });
  });

  it('a refusal goes under its field', async () => {
    const s = await setup();
    await s.result(OP, SET);
    s.answer(422, { error: { code: 'invalid_payload', message: 'Invalid payload', fields: { tax_id: 'That tax ID is not valid.' } } });
    await click(s.find('invoice-issuer-save').element);
    await flush();
    expect(prop(s.field('tax-id'), 'errorText')).toBe('That tax ID is not valid.');
  });

  describe('a refusal by fields (hub#854, as FormModal and the Services settings do: hub#821)', () => {
    const TAX_ID = 'That tax ID is not valid.';
    const POSTAL = 'Ensure this value has at most 5 characters.';
    const REFUSAL = { error: { code: 'invalid_payload', message: 'Invalid payload', fields: { tax_id: TAX_ID, postal_code: POSTAL } } };

    /** Saves a tax ID and a postal code the server refuses. */
    async function refused() {
      const s = await setup();
      await s.result(OP, SET);
      s.answer(422, REFUSAL);
      await ionValue(s.field('tax-id'), 'B1', 'ionInput');
      await ionValue(s.field('postal-code'), '280011', 'ionInput');
      await click(s.find('invoice-issuer-save').element);
      await flush();
      const says = (key: string) => (prop(s.field(key), 'errorText') as string | undefined) ?? '';
      const marked = (key: string) => s.field(key).classList.contains('ion-invalid');
      return { ...s, says, marked };
    }

    it('says it under the fields only, and a field’s message goes as soon as that field is changed', async () => {
      const s = await refused();
      expect(s.find('invoice-issuer-error').exists()).toBe(false);
      expect([s.says('tax-id'), s.says('postal-code')]).toEqual([TAX_ID, POSTAL]);
      await ionValue(s.field('tax-id'), 'B12345674', 'ionInput');
      expect([s.says('tax-id'), s.marked('tax-id')]).toEqual(['', false]);
      expect([s.says('postal-code'), s.marked('postal-code')]).toEqual([POSTAL, true]);
    });

    it('a change in another field takes no field’s message away', async () => {
      const s = await refused();
      await ionValue(s.field('city'), 'Toledo', 'ionInput');
      expect([s.says('tax-id'), s.says('postal-code')]).toEqual([TAX_ID, POSTAL]);
    });

    it('the next refusal says it all again', async () => {
      const s = await refused();
      await ionValue(s.field('tax-id'), 'B2', 'ionInput');
      await ionValue(s.field('postal-code'), '280012', 'ionInput');
      expect([s.says('tax-id'), s.says('postal-code'), s.find('invoice-issuer-error').exists()]).toEqual(['', '', false]);
      await click(s.find('invoice-issuer-save').element);
      await flush();
      expect([s.says('tax-id'), s.says('postal-code'), s.marked('tax-id')]).toEqual([TAX_ID, POSTAL, true]);
    });

    it('a refusal that names no field stays until the next try: nothing else says it', async () => {
      const s = await setup();
      await s.result(OP, SET);
      s.answer(409, { error: { code: 'conflict', message: 'Someone else is saving it.' } });
      await click(s.find('invoice-issuer-save').element);
      await flush();
      await ionValue(s.field('city'), 'Toledo', 'ionInput');
      expect(s.find('invoice-issuer-error').text()).toContain('Someone else is saving it.');
    });
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
