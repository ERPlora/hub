// The recipient's tax ID of an invoice, checked in the sheet the way the server checks it
// (`apps.customer.tax_ids`, python-stdnum's `es.nif`): a Spanish NIF (DNI letter), NIE (X/Y/Z, the same
// letter), the K/L/M ones (DNI letter over their seven digits) and a CIF (Luhn control, as a digit or
// as a letter of «JABCDEFGHI»). Abroad, the kind of document (02–07) is required: VeriFactu declares a
// foreign tax ID as IDOtro, refused without it. An EU VAT number and other foreign documents are the
// server's to check; it answers on the field.
import type { Recipient } from './recipient';
import { HOME_COUNTRY } from './recipient';

const DNI_LETTERS = 'TRWAGMYFPDXBNJZSQVHLCKE';
const CIF_LETTERS = 'JABCDEFGHI';
const CIF_KINDS = 'ABCDEFGHJNPQRSUVW';

/** As written, without spaces, dashes or dots, in capitals and without the «ES» of a VAT number. */
function compact(value: string): string {
  const text = value.replace(/[\s.-]/g, '').toUpperCase();
  return text.startsWith('ES') ? text.slice(2) : text;
}

const dniLetter = (digits: string): string => DNI_LETTERS[Number(digits) % 23] ?? '';

/** The Luhn check digit of `digits` (python-stdnum's `luhn.calc_check_digit`). */
function luhnDigit(digits: string): number {
  let sum = 0;
  [...`${digits}0`].reverse().forEach((char, index) => {
    const digit = Number(char);
    if (index % 2 === 0) sum += digit;
    else sum += Math.floor((digit * 2) / 10) + ((digit * 2) % 10);
  });
  return (10 - (sum % 10)) % 10;
}

export function spanishTaxIdValid(value: string): boolean {
  const number = compact(value);
  if (number.length !== 9 || !/^\d{7}$/.test(number.slice(1, 8))) return false;
  const [first, last] = [number[0] as string, number[8] as string];
  if (/\d/.test(first)) return dniLetter(number.slice(0, 8)) === last;
  if ('XYZ'.includes(first)) return dniLetter(`${'XYZ'.indexOf(first)}${number.slice(1, 8)}`) === last;
  if ('KLM'.includes(first)) return dniLetter(number.slice(1, 8)) === last;
  if (!CIF_KINDS.includes(first)) return false;
  const check = luhnDigit(number.slice(1, 8));
  return last === String(check) || last === CIF_LETTERS[check];
}

export type RecipientIssue = 'taxIdInvalid' | 'idTypeRequired';

/** What is wrong with a recipient the sheet can tell before charging; `null` when nothing (or nothing yet). */
export function recipientIssue(recipient: Recipient): RecipientIssue | null {
  const taxId = recipient.taxId.trim();
  if (!taxId) return null;
  if (recipient.country !== HOME_COUNTRY) return recipient.idType ? null : 'idTypeRequired';
  return spanishTaxIdValid(taxId) ? null : 'taxIdInvalid';
}
