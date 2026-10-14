// A phone on screen. The card keeps it in E.164 (CUSTOMER-F11) and a person reads it with the calling
// code apart and the digits grouped: «+34 600 111 222». The calling code is told by the ITU-T E.164
// plan (one digit: 1 and 7; the two-digit codes below; three digits otherwise). The national number
// goes in threes, the last group taking the remainder. Until `@erplora/ui` brings libphonenumber's
// formats per country (UI-REQUESTS.md), this is how the app shows a phone; it never changes one.

/** The two-digit calling codes of the ITU-T E.164 plan. */
const TWO_DIGITS = new Set([
  '20', '27', '30', '31', '32', '33', '34', '36', '39', '40', '41', '43', '44', '45', '46', '47', '48', '49',
  '51', '52', '53', '54', '55', '56', '57', '58', '60', '61', '62', '63', '64', '65', '66', '81', '82', '84',
  '86', '90', '91', '92', '93', '94', '95', '98',
]);

const E164 = /^\+(\d{8,15})$/;

function callingCode(digits: string): string {
  if (digits[0] === '1' || digits[0] === '7') return digits[0];
  return TWO_DIGITS.has(digits.slice(0, 2)) ? digits.slice(0, 2) : digits.slice(0, 3);
}

/** «+34600111222» → «+34 600 111 222»; anything else as stored. */
export function formatPhone(phone: string | null | undefined): string {
  const text = (phone ?? '').trim();
  const match = E164.exec(text);
  if (!match) return text;
  const digits = match[1];
  const code = callingCode(digits);
  const national = digits.slice(code.length);
  const groups: string[] = [];
  let rest = national;
  while (rest.length > 4) {
    groups.push(rest.slice(0, 3));
    rest = rest.slice(3);
  }
  if (rest.length === 4 && national.length % 3 === 0) groups.push(rest.slice(0, 1), rest.slice(1));
  else groups.push(rest);
  return `+${code} ${groups.join(' ')}`;
}
