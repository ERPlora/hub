// SALE-F04: the recipient of an invoice, checked in the sheet as the server checks it
// (`apps.customer.tax_ids`, python-stdnum): a Spanish NIF, NIE or CIF must check (DNI letter, NIE letter,
// CIF control digit or letter); abroad, the kind of document is required. An EU VAT number (02) and any
// other foreign document are left to the server, which answers on the field.
import { describe, expect, it } from 'vitest';

import type { Recipient } from './recipient';
import { recipientIssue, spanishTaxIdValid } from './taxId';

const at = (over: Partial<Recipient>): Recipient => ({ name: 'Bar', taxId: '', address: 'C/ Mayor 1', country: 'ES', idType: '', ...over });

describe('spanishTaxIdValid', () => {
  it('a DNI, a NIE, a CIF (digit or letter) and the K/L/M ones check, also with spaces, dashes or ES', () => {
    for (const valid of ['12345678Z', 'X1234567L', 'Y7654321G', 'Z0000000M', 'B12345674', 'B1234567D', 'Q2826000H', 'K1234567L', 'ESB12345674', 'b-1234567-4', '12 345 678 z']) {
      expect(spanishTaxIdValid(valid), valid).toBe(true);
    }
  });

  it('a wrong letter or control digit, a short one or letters inside do not', () => {
    for (const invalid of ['12345678A', 'B12345678', 'Q28260004', 'X1234567A', '1234567Z', 'B1234A674', 'I12345674', '']) {
      expect(spanishTaxIdValid(invalid), invalid).toBe(false);
    }
  });
});

describe('recipientIssue', () => {
  it('at home, a tax ID that does not check', () => {
    expect(recipientIssue(at({ taxId: 'B12345678' }))).toBe('taxIdInvalid');
    expect(recipientIssue(at({ taxId: 'B12345674' }))).toBeNull();
    // Nothing typed yet is «incomplete», not «invalid».
    expect(recipientIssue(at({ taxId: '' }))).toBeNull();
  });

  it('abroad, its kind of document is required; the number itself is the server’s to check', () => {
    expect(recipientIssue(at({ country: 'GB', taxId: 'AB123', idType: '' }))).toBe('idTypeRequired');
    expect(recipientIssue(at({ country: 'GB', taxId: 'AB123', idType: '04' }))).toBeNull();
    expect(recipientIssue(at({ country: 'FR', taxId: '40303265045', idType: '02' }))).toBeNull();
  });
});
