// Countries of the customer card: the card stores the ISO 3166-1 alpha-2 code (CUSTOMER-F01) and a
// person reads and picks its name in their language. The LIST is the server's: `countries.json`,
// generated from pycountry by `apps/customer/countries.py` (a Python test keeps them equal), so the
// screen never offers a country the server refuses (CLDR also names XK, AC, CP, DG, TA…). The
// runtime's CLDR data (`Intl.DisplayNames`) only gives their names.
import ISO_CODES from './countries.json';

/** Canarias (IC) and Ceuta y Melilla (EA) are Spain: the AEAT has no such country. */
const SPANISH_REGIONS = new Set(['IC', 'EA']);

/** The business's country while the platform has no setting for it (WORKBOOK «Antes de empezar»). */
const HOME_COUNTRY = 'ES';

export interface CountryOption {
  /** ISO alpha-2 code: what the card stores. */
  value: string;
  /** The country's name in the page language. */
  label: string;
}

/** The countries the server accepts (ISO 3166-1, pycountry). */
const REGION_CODES: readonly string[] = ISO_CODES;

const CODES = new Set(REGION_CODES);

function displayNames(locale: string): Intl.DisplayNames | null {
  try {
    return new Intl.DisplayNames([locale, 'en'], { type: 'region', fallback: 'none' });
  } catch {
    return null;
  }
}

/** Case, accents and spacing do not make another country. */
function normalize(text: string): string {
  return text.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase().replace(/\s+/g, ' ').trim();
}

const optionsByLocale = new Map<string, CountryOption[]>();

/** The picker's options in `locale`: Spain first, the rest by name. Shared: never mutate it. */
export function countryOptions(locale: string): CountryOption[] {
  const cached = optionsByLocale.get(locale);
  if (cached) return cached;
  const names = displayNames(locale);
  const option = (value: string): CountryOption => ({ value, label: names?.of(value) ?? value });
  let compare: (a: string, b: string) => number;
  try {
    compare = new Intl.Collator(locale).compare;
  } catch {
    compare = (a, b) => (a < b ? -1 : a > b ? 1 : 0);
  }
  const rest = REGION_CODES.filter((code) => code !== HOME_COUNTRY).map(option);
  rest.sort((a, b) => compare(a.label, b.label));
  const options = [option(HOME_COUNTRY), ...rest];
  optionsByLocale.set(locale, options);
  return options;
}

/** The stored code named in `locale`; empty stays empty and an unknown code is shown as stored. */
export function countryName(code: string | null | undefined, locale: string): string {
  const text = (code ?? '').trim().toUpperCase();
  if (!CODES.has(text)) return (code ?? '').trim();
  return displayNames(locale)?.of(text) ?? text;
}

const namesByLocale = new Map<string, Map<string, string>>();

function nameIndex(locale: string): Map<string, string> {
  let index = namesByLocale.get(locale);
  if (!index) {
    index = new Map();
    const names = displayNames(locale);
    for (const code of REGION_CODES) {
      const name = names?.of(code);
      if (name) index.set(normalize(name), code);
    }
    namesByLocale.set(locale, index);
  }
  return index;
}

/** The code a text names (a code, or a name in Spanish, English or `locale`); '' when none. */
export function countryCode(raw: string | null | undefined, locale?: string): string {
  const text = (raw ?? '').trim();
  if (!text) return '';
  if (/^[a-z]{2}$/i.test(text)) {
    const code = text.toUpperCase();
    if (SPANISH_REGIONS.has(code)) return HOME_COUNTRY;
    return CODES.has(code) ? code : '';
  }
  const key = normalize(text);
  for (const language of new Set(['es', 'en', ...(locale ? [locale] : [])])) {
    const code = nameIndex(language).get(key);
    if (code) return code;
  }
  return '';
}
