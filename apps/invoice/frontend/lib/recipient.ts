// The recipient of a full invoice (INVOICE-F03, F05): name, tax ID, address, country and, outside Spain,
// the kind of document the AEAT reads as `IDOtro` (02 EU VAT number, 04 tax ID of their country, 03
// passport, 05 residence certificate, 06 other, 07 not registered). Prefilled from a customer card of
// Customers (its snapshot); the server checks a Spanish tax ID and refuses a full invoice without the
// three, whatever the screen says.
import type { CustomerSnapshot } from '../../../customer/frontend/components/CustomerSearch.vue';
import type { IdType, RecipientIn } from '../operations';

/** The business's country while the platform has no setting for it (WORKBOOK «Antes de empezar»). */
export const HOME_COUNTRY = 'ES';

/** The kinds of document offered abroad. */
export const ID_TYPES = ['02', '04', '03', '05', '06', '07'] as const satisfies readonly IdType[];

const EU_MEMBERS = new Set('AT BE BG CY CZ DE DK EE ES FI FR GR HR HU IE IT LT LU LV MT NL PL PT RO SE SI SK'.split(' '));

export interface Recipient {
  /** The card it came from, if any. */
  customerId: string | null;
  name: string;
  taxId: string;
  address: string;
  /** ISO 3166-1 alpha-2. */
  country: string;
  idType: IdType;
}

/** The kind of document a country starts with: none at home, the EU VAT number in the EU, else 04. */
export function defaultIdType(country: string): IdType {
  if (country === HOME_COUNTRY) return '';
  return EU_MEMBERS.has(country) ? '02' : '04';
}

/** The recipient a form opens with: the card's, or blank at home. */
export function recipientFrom(card: CustomerSnapshot | null): Recipient {
  const country = card?.customer_country?.trim().toUpperCase() || HOME_COUNTRY;
  return {
    customerId: card?.customer_id ?? null,
    name: card?.customer_name ?? '',
    taxId: card?.customer_tax_id ?? '',
    address: card?.customer_address ?? '',
    country,
    idType: defaultIdType(country),
  };
}

/** Name, tax ID and address: what a full invoice cannot go without. */
export function recipientComplete(recipient: Recipient): boolean {
  return [recipient.name, recipient.taxId, recipient.address].every((part) => part.trim() !== '');
}

/** The recipient as the commands take it: trimmed, the business's own country as an empty code. */
export function recipientPayload(recipient: Recipient): RecipientIn {
  const home = recipient.country === HOME_COUNTRY;
  return {
    ...(recipient.customerId ? { customer_id: recipient.customerId } : {}),
    customer_name: recipient.name.trim(),
    customer_tax_id: recipient.taxId.trim(),
    customer_address: recipient.address.trim(),
    customer_country: home ? '' : recipient.country,
    customer_id_type: home ? '' : recipient.idType,
  };
}
