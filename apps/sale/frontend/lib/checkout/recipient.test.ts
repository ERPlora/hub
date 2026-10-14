// SALE-F04: an invoice names its recipient — «Name or company name», «Country», «Tax ID», «Address» and,
// outside Spain, the «Kind of document» (EU → 02 «EU VAT number», elsewhere → 04 «Tax ID of their
// country»; Spain → none). Prefilled from the customer the check has; the charge sends them, with the
// business's own country as an empty code (the server's «empty = the business's»).
import { describe, expect, it } from 'vitest';

import type { CustomerSnapshot } from '../../../../customer/frontend/components/CustomerSearch.vue';
import { defaultIdType, HOME_COUNTRY, ID_TYPES, type Recipient, recipientComplete, recipientFrom, recipientPayload } from './recipient';

const CUSTOMER: CustomerSnapshot = {
  customer_id: 'c1',
  customer_name: 'Bar Pepe SL',
  customer_tax_id: 'B12345678',
  customer_address: 'Calle Mayor 1, 28001 Madrid, España',
  customer_country: 'ES',
};

const BLANK: Recipient = { name: '', taxId: '', address: '', country: HOME_COUNTRY, idType: '' };

describe('recipient of an invoice', () => {
  it('the business is in Spain; the kinds of document offered abroad are 02, 04, 03 and 06', () => {
    expect(HOME_COUNTRY).toBe('ES');
    expect(ID_TYPES).toEqual(['02', '04', '03', '06']);
  });

  it('defaults the kind of document by country: none at home, 02 in the EU, 04 elsewhere', () => {
    expect(defaultIdType('ES')).toBe('');
    expect(defaultIdType('PT')).toBe('02');
    expect(defaultIdType('DE')).toBe('02');
    expect(defaultIdType('GB')).toBe('04');
    expect(defaultIdType('US')).toBe('04');
  });

  it('is prefilled from the customer of the check', () => {
    expect(recipientFrom(CUSTOMER)).toEqual({
      name: 'Bar Pepe SL',
      taxId: 'B12345678',
      address: 'Calle Mayor 1, 28001 Madrid, España',
      country: 'ES',
      idType: '',
    });
    expect(recipientFrom({ ...CUSTOMER, customer_country: 'FR' })).toMatchObject({ country: 'FR', idType: '02' });
  });

  it('a customer without country, or no customer at all, starts at home and blank', () => {
    expect(recipientFrom({ ...CUSTOMER, customer_country: '' })).toMatchObject({ country: 'ES', idType: '' });
    expect(recipientFrom(null)).toEqual(BLANK);
  });

  it('is complete with a name, a tax id and an address (blank spaces do not count)', () => {
    expect(recipientComplete(recipientFrom(CUSTOMER))).toBe(true);
    expect(recipientComplete({ ...recipientFrom(CUSTOMER), taxId: '  ' })).toBe(false);
    expect(recipientComplete({ ...recipientFrom(CUSTOMER), address: '' })).toBe(false);
    expect(recipientComplete(BLANK)).toBe(false);
  });

  it('travels trimmed, with home as an empty country and no kind of document', () => {
    expect(recipientPayload({ ...recipientFrom(CUSTOMER), name: ' Bar Pepe SL ' })).toEqual({
      customer_name: 'Bar Pepe SL',
      customer_tax_id: 'B12345678',
      customer_address: 'Calle Mayor 1, 28001 Madrid, España',
      customer_country: '',
      customer_id_type: '',
    });
  });

  it('abroad, the country and its kind of document travel too', () => {
    expect(recipientPayload({ name: 'Smith Ltd', taxId: 'GB123', address: '1 High St, London', country: 'GB', idType: '03' })).toEqual({
      customer_name: 'Smith Ltd',
      customer_tax_id: 'GB123',
      customer_address: '1 High St, London',
      customer_country: 'GB',
      customer_id_type: '03',
    });
  });
});
