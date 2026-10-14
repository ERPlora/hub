// The recipient of an invoice (SALE-F04): name, tax id, address, country and, outside Spain, the kind of
// document the AEAT reads as `IDOtro` (02 EU VAT number, 04 tax id of their country, 03 passport, 06
// other). The sheet asks for it with «Invoice» and above the ticket limit; the server refuses an invoice
// without the three (`sale.invoice_recipient_incomplete`) whatever the screen says.
import type { CustomerSnapshot } from '../../../../customer/frontend/components/CustomerSearch.vue';
import type { CompleteIn, IdType } from '../../operations';

/** The business's country while the platform has no setting for it (WORKBOOK «Antes de empezar»). */
export const HOME_COUNTRY = 'ES';

/** The kinds of document offered abroad, in the order of the old screen. */
export const ID_TYPES = ['02', '04', '03', '06'] as const satisfies readonly IdType[];

const EU_MEMBERS = new Set('AT BE BG CY CZ DE DK EE ES FI FR GR HR HU IE IT LT LU LV MT NL PL PT RO SE SI SK'.split(' '));

export interface Recipient {
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

/** The recipient the sheet opens with: the check's customer, or blank at home. */
export function recipientFrom(customer: CustomerSnapshot | null): Recipient {
  const country = customer?.customer_country?.trim().toUpperCase() || HOME_COUNTRY;
  return {
    name: customer?.customer_name ?? '',
    taxId: customer?.customer_tax_id ?? '',
    address: customer?.customer_address ?? '',
    country,
    idType: defaultIdType(country),
  };
}

/** Name, tax id and address: what an invoice cannot go without. */
export function recipientComplete(recipient: Recipient): boolean {
  return [recipient.name, recipient.taxId, recipient.address].every((part) => part.trim() !== '');
}

type RecipientFields = Required<
  Pick<CompleteIn, 'customer_name' | 'customer_tax_id' | 'customer_address' | 'customer_country' | 'customer_id_type'>
>;

/** The recipient as the charge sends it: trimmed, the business's own country as an empty code. */
export function recipientPayload(recipient: Recipient): RecipientFields {
  const home = recipient.country === HOME_COUNTRY;
  return {
    customer_name: recipient.name.trim(),
    customer_tax_id: recipient.taxId.trim(),
    customer_address: recipient.address.trim(),
    customer_country: home ? '' : recipient.country,
    customer_id_type: home ? '' : recipient.idType,
  };
}
