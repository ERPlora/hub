// The recipient of a full invoice (INVOICE-F03, F05): «Name or company name», «Country», «Tax ID»,
// «Address» and, outside Spain, the «Document type» the AEAT reads as `IDOtro` (EU → 02 «EU VAT number»,
// elsewhere → 04 «Tax ID of their country»; Spain → none). Prefilled from a customer card of Customers;
// sent with the business's own country as an empty code (the server's «empty = Spain»).
import { describe, expect, it } from 'vitest';

import type { CustomerSnapshot } from '../../../customer/frontend/components/CustomerSearch.vue';
import { defaultIdType, HOME_COUNTRY, ID_TYPES, type Recipient, recipientComplete, recipientFrom, recipientPayload } from './recipient';

const CARD: CustomerSnapshot = {
  customer_id: 'c1',
  customer_name: 'Bar Pepe SL',
  customer_tax_id: 'B12345674',
  customer_address: 'Calle Mayor 1, 28001 Madrid, España',
  customer_country: 'ES',
};

const BLANK: Recipient = { customerId: null, name: '', taxId: '', address: '', country: HOME_COUNTRY, idType: '' };

describe('recipient of a full invoice', () => {
  it('the business is in Spain; every kind of foreign document the AEAT reads is offered', () => {
    expect(HOME_COUNTRY).toBe('ES');
    expect(ID_TYPES).toEqual(['02', '04', '03', '05', '06', '07']);
  });

  it('defaults the kind of document by country: none at home, 02 in the EU, 04 elsewhere', () => {
    expect([defaultIdType('ES'), defaultIdType('PT'), defaultIdType('GB'), defaultIdType('US')]).toEqual(['', '02', '04', '04']);
  });

  it('is prefilled from a card, and blank at home without one', () => {
    expect(recipientFrom(CARD)).toEqual({
      customerId: 'c1',
      name: 'Bar Pepe SL',
      taxId: 'B12345674',
      address: 'Calle Mayor 1, 28001 Madrid, España',
      country: 'ES',
      idType: '',
    });
    expect(recipientFrom({ ...CARD, customer_country: 'FR' })).toMatchObject({ country: 'FR', idType: '02' });
    expect(recipientFrom(null)).toEqual(BLANK);
  });

  it('is complete with a name, a tax ID and an address', () => {
    expect(recipientComplete(recipientFrom(CARD))).toBe(true);
    expect(recipientComplete({ ...recipientFrom(CARD), taxId: '  ' })).toBe(false);
    expect(recipientComplete(BLANK)).toBe(false);
  });

  it('travels trimmed, with home as an empty country and no kind of document, and the card it came from', () => {
    expect(recipientPayload({ ...recipientFrom(CARD), name: ' Bar Pepe SL ' })).toEqual({
      customer_id: 'c1',
      customer_name: 'Bar Pepe SL',
      customer_tax_id: 'B12345674',
      customer_address: 'Calle Mayor 1, 28001 Madrid, España',
      customer_country: '',
      customer_id_type: '',
    });
    expect(recipientPayload({ ...BLANK, name: 'Jean', country: 'FR', idType: '02', taxId: 'FR40303265045', address: 'Rue 1' })).toEqual({
      customer_name: 'Jean',
      customer_tax_id: 'FR40303265045',
      customer_address: 'Rue 1',
      customer_country: 'FR',
      customer_id_type: '02',
    });
  });
});
