// What the tax screens read off a rule or a category (TAX-F03–F06). The server decides and checks
// everything (the roots a component may hang from, the 0 % of a class without tax, the overlap);
// these helpers only shape how the screen PAINTS a row.
import type { CategoryOut, OperationClass, RuleOut, TaxType } from '../operations';

/** The tax families, in the order the form offers them (VAT, the default, first). */
export const TAX_TYPES: readonly TaxType[] = Object.freeze([
  'vat',
  'igic',
  'ipsi',
  'surcharge',
  'sales_tax',
  'withholding',
  'excise',
  'import_duty',
]);

/** The fiscal qualifications, subject (the default) first. */
export const OPERATION_CLASSES: readonly OperationClass[] = Object.freeze([
  'subject',
  'subject_reverse',
  'exempt',
  'not_subject',
  'not_subject_location',
]);

/** Every class but `subject` reaches the AEAT without a quota, so its rate is 0 % (TAX-F05). */
export function chargesNoTax(operationClass: OperationClass | null | undefined): boolean {
  return !!operationClass && operationClass !== 'subject';
}

/** The Category cell of a rule: its key; a component, «↳» and its label, under its root. */
export function ruleCategoryText(rule: RuleOut): string {
  if (!rule.parent_id) return rule.tax_category_key;
  return `↳ ${rule.component_label?.trim() || rule.tax_category_key}`;
}

/** A rule card's title: the category a person reads; a component names its root category and its label. */
export function ruleCardTitle(rule: RuleOut): string {
  const name = rule.tax_category_name.trim() || rule.tax_category_key;
  const label = rule.component_label?.trim();
  return rule.parent_id && label ? `↳ ${name} · ${label}` : name;
}

type NamedCategory = Pick<CategoryOut, 'key' | 'name' | 'display_name'>;

/** The name of a category to show: the one the server resolved for the reader, never blank. */
export function categoryDisplayName(category: NamedCategory): string {
  return category.display_name.trim() || category.name.trim() || category.key;
}

/** A category in a picker: «Restaurant — food (restaurant.food)». */
export function categoryOptionLabel(category: NamedCategory): string {
  return `${categoryDisplayName(category)} (${category.key})`;
}
