// What a spec that sells in a business outside Spain needs of that country's tax rules, without Playwright (the unit
// tests read it: playwright-environment.test.ts). Spain alone has factory rules (TAX-F16); anywhere else a category with
// no rule of the business's country is not charged (PLAN-HUB §81), so the spec mounts the rule a business of that
// country makes before it sells (`createRule` of tax-helpers.ts) and deletes it after (`dropCountryRules`, there).

/** The statement that deletes every rule of `country`, components first: the ones a run mounted and any a killed run
 *  left. Never Spain's, which every other spec charges with, nor anything that is not an ISO country code. */
export function countryRulesCleanup(country: string): string {
  if (!/^[A-Z]{2}$/.test(country) || country === 'ES') throw new Error(`countryRulesCleanup(${JSON.stringify(country)}): only another country's rules are a run's`);
  return [
    `delete from tax_taxrule where parent_id is not null and country_code = '${country}'`,
    `delete from tax_taxrule where country_code = '${country}'`,
  ].join('; ');
}
