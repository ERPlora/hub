// The countries a tax rule may be set for (TAX-F04, taxes#41): a country is CHOSEN, never typed, so
// a code no business can hold («ZZ») never becomes a rule that matches nothing.
//
// The codes are the server's: `apps/tax/schemas.py` accepts the 249 officially assigned ISO 3166-1
// alpha-2 codes of pycountry. This copy is the closed list the pickers offer until the op types are
// generated from the OpenAPI document; should it ever drift, the server still refuses the code with
// a 422 painted under «Country».
//
// The NAMES come from the platform (`Intl.DisplayNames`), in the reader's language, with no assets
// and no network; where the runtime cannot name a code, the code alone is shown.

/** One entry of a country picker. */
export interface CountryOption {
  /** ISO 3166-1 alpha-2: what travels in `country_code`. */
  value: string;
  /** «España (ES)»: the name the reader reads, with its code so typing «ES» finds it. */
  label: string;
}

/** The 249 officially assigned ISO 3166-1 alpha-2 codes (no ZZ, EU or XK), as the server's. */
export const COUNTRY_CODES: readonly string[] = Object.freeze(
  (
    'AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ BA BB BD BE BF BG BH BI BJ BL BM BN BO BQ BR BS BT BV ' +
    'BW BY BZ CA CC CD CF CG CH CI CK CL CM CN CO CR CU CV CW CX CY CZ DE DJ DK DM DO DZ EC EE EG EH ER ES ' +
    'ET FI FJ FK FM FO FR GA GB GD GE GF GG GH GI GL GM GN GP GQ GR GS GT GU GW GY HK HM HN HR HT HU ID IE ' +
    'IL IM IN IO IQ IR IS IT JE JM JO JP KE KG KH KI KM KN KP KR KW KY KZ LA LB LC LI LK LR LS LT LU LV LY ' +
    'MA MC MD ME MF MG MH MK ML MM MN MO MP MQ MR MS MT MU MV MW MX MY MZ NA NC NE NF NG NI NL NO NP NR NU ' +
    'NZ OM PA PE PF PG PH PK PL PM PN PR PS PT PW PY QA RE RO RS RU RW SA SB SC SD SE SG SH SI SJ SK SL SM ' +
    'SN SO SR SS ST SV SX SY SZ TC TD TF TG TH TJ TK TL TM TN TO TR TT TV TW TZ UA UG UM US UY UZ VA VC VE ' +
    'VG VI VN VU WF WS YE YT ZA ZM ZW'
  ).split(' '),
);

const KNOWN = new Set(COUNTRY_CODES);

/** `Intl.DisplayNames` for `locale`, or `null` where the runtime cannot build one. */
function regionNames(locale: string): Intl.DisplayNames | null {
  try {
    // `fallback: 'none'`: an unknown code comes back `undefined` instead of echoing itself.
    return new Intl.DisplayNames([locale, 'en'], { type: 'region', fallback: 'none' });
  } catch {
    return null;
  }
}

function compareIn(locale: string): (a: string, b: string) => number {
  try {
    return new Intl.Collator(locale).compare;
  } catch {
    return (a, b) => (a < b ? -1 : a > b ? 1 : 0);
  }
}

function labelOf(code: string, names: Intl.DisplayNames | null): string {
  const name = KNOWN.has(code) ? names?.of(code) : undefined;
  return name ? `${name} (${code})` : code;
}

/** Built lists, one per language: a form re-renders on every keystroke. */
const byLocale = new Map<string, readonly CountryOption[]>();

/** The picker's options, named and sorted for whoever reads them. Shared: read it, never mutate it. */
export function countryOptions(locale: string): readonly CountryOption[] {
  const cached = byLocale.get(locale);
  if (cached) return cached;
  const names = regionNames(locale);
  const compare = compareIn(locale);
  const options = Object.freeze(
    COUNTRY_CODES.map((value) => ({ value, label: labelOf(value, names) })).sort((a, b) => compare(a.label, b.label)),
  );
  byLocale.set(locale, options);
  return options;
}

/** One code as the reader reads it («Portugal (PT)»); a code outside the list stays as it came. */
export function countryLabel(code: string, locale: string): string {
  return labelOf(code, regionNames(locale));
}

/** Some codes (those a business has rules for) as a filter offers them: named, sorted by name, once. */
export function countryChoices(codes: Iterable<string>, locale: string): CountryOption[] {
  const names = regionNames(locale);
  const compare = compareIn(locale);
  return [...new Set(codes)].map((value) => ({ value, label: labelOf(value, names) })).sort((a, b) => compare(a.label, b.label));
}
