// A business outside Spain charges nothing without a tax rule of its own country: Spain alone has factory rules (TAX-F16),
// and every category with no rule of the business's country refuses to be charged, with
// «cannot be charged: no tax rule applies to its tax category … here» on the till and `sale.no_tax_rule` (409) from
// `POST /sale/sales`. A spec that moves hub `a` out of Spain and charges there, or reads the till's total there, has to
// mount the rule a business of that country makes before it sells (TAX-F04), as the Japanese one did after hub#1069.
// sale-business-currency.spec.ts and table-business-currency.spec.ts did not, and stayed red for days (hub#1152): the CI
// does not run the e2e, and this check runs with `pnpm test`, which it does.
// flow: SALE-F01 (the till charges in the business's currency) — FIX tests/e2e
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import { countryRulesCleanup } from './country-rules';

const E2E_DIR = dirname(fileURLToPath(import.meta.url));

const read = (name: string): string => readFileSync(join(E2E_DIR, name), 'utf8');
const specs = (): string[] => readdirSync(E2E_DIR).filter((name) => name.endsWith('.spec.ts'));

/** The countries other than Spain the spec registers hub `a` in (`registerBusinessIn(…, 'PL')`). */
function countriesOutsideSpain(source: string): string[] {
  const found = [...source.matchAll(/registerBusinessIn\([^)]*'([A-Z]{2})'\)/g)].map((match) => match[1]);
  return [...new Set(found)].filter((country) => country !== 'ES');
}

/** Whether the spec charges a sale or reads the till's total: both need a rule of the business's country. */
function chargesOrValues(source: string): boolean {
  return /\bchargeByApi\(|data-testid=pos-charge\b|data-testid=pos-total\b|data-testid=sale-checkout-confirm\b/.test(source);
}

/** Whether the spec mounts a tax rule (`createRule` of tax-helpers.ts, or a `POST /tax/rules` of its own). */
function mountsTaxRule(source: string): boolean {
  return /\bcreateRule\(|['`]\/tax\/rules['`]/.test(source);
}

/** Why a spec would charge out of Spain with no rule; '' when it does not. */
function missingRule(source: string): string {
  const countries = countriesOutsideSpain(source);
  if (countries.length === 0 || !chargesOrValues(source) || mountsTaxRule(source)) return '';
  return `charges or reads the till's total in ${countries.join(', ')} and mounts no tax rule there`;
}

describe('the specs that charge in a business outside Spain', () => {
  it('there are specs that move hub a out of Spain and charge there to look at', () => {
    const charging = specs().filter((name) => countriesOutsideSpain(read(name)).length > 0 && chargesOrValues(read(name)));
    expect(charging).toEqual(expect.arrayContaining(['sale-business-currency.spec.ts', 'table-business-currency.spec.ts', 'service-business-currency.spec.ts']));
  });

  it('each one mounts a tax rule of that country before it charges (hub#1152)', () => {
    const offenders = specs()
      .map((name) => [name, missingRule(read(name))])
      .filter(([, why]) => why)
      .map(([name, why]) => `${name}: ${why}`);
    expect(offenders).toEqual([]);
  });

  it('the check catches a spec that charges in Poland with no rule, and lets one with its rule through', () => {
    const charging = "await registerBusinessIn(original, 'PL');\nawait shown(page).locator('[data-testid=pos-charge]').click();";
    expect(missingRule(charging)).toBe("charges or reads the till's total in PL and mounts no tax rule there");
    expect(missingRule("await registerBusinessIn(original, 'JP');\nconst sale = await chargeByApi(context, body);")).not.toBe('');
    expect(missingRule(`${charging}\nawait createRule(context, { country_code: 'PL', tax_category_key: 'product.generic', rate_pct: 23 });`)).toBe('');
    expect(missingRule(`${charging}\nawait post(context, '/tax/rules', { country_code: 'PL' });`)).toBe('');
    // Spain has its factory rules, and a spec that only reads in Poland needs none.
    expect(missingRule("await registerBusinessIn(original, 'ES');\nawait chargeByApi(context, body);")).toBe('');
    expect(missingRule("await registerBusinessIn(original, 'PL');\nawait expect(row).toContainText(ZLOTY);")).toBe('');
    // A page's URL is not a rule.
    expect(missingRule(`${charging}\nawait expect(page).toHaveURL(\`\${A}/tax/rules\`);`)).not.toBe('');
  });
});

describe('countryRulesCleanup: what a run deletes of the rules it mounted', () => {
  it('deletes the components first, then every rule of that country', () => {
    expect(countryRulesCleanup('PL')).toBe(
      "delete from tax_taxrule where parent_id is not null and country_code = 'PL'; delete from tax_taxrule where country_code = 'PL'",
    );
  });

  it('never Spain, whose rules are the factory ones every other spec charges with, nor what is not a country code', () => {
    for (const country of ['ES', 'pl', 'POL', '', "PL' or 1=1 --"]) {
      expect(() => countryRulesCleanup(country), JSON.stringify(country)).toThrow(/only another country's rules are a run's/);
    }
  });
});
