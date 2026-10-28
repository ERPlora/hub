// What the rules table and a list's row paint (the old module's `rule-value.ts`, pricing#28): the VALUE
// of a rule with its unit in ONE column («10 %», «0,50 € por unidad», «Compra 2, llévate 1», «3+: 10 % ·
// 6+: 15 %»), never a bare number whose unit has to be guessed; what it applies to, with its customer
// group after it (or «Deleted group» when Customers deleted it); and the tax basis of a list, where an empty one follows the business and says so.
import type { RuleOut } from '../operations';
import { formatMoney, formatPercent, formatQuantity, type Money } from './format';

type Translate = (key: string, named?: Record<string, unknown>) => string;

/** A rule's value; an amount per unit in the business's `money` (a bare figure until it answers). */
export function ruleValueLabel(rule: RuleOut, t: Translate, locale: string, money?: Money): string {
  switch (rule.rule_type) {
    case 'percent':
      return formatPercent(rule.percent ?? 0, locale);
    case 'fixed':
      return t('pricing.rules.value.perUnit', { amount: formatMoney(rule.amount ?? 0, locale, money) });
    case 'buy_x_get_y':
      return t('pricing.rules.value.buyGet', { buy: rule.buy_quantity ?? 0, get: rule.get_quantity ?? 0 });
    default:
      return rule.tiers
        .map((tier) =>
          t('pricing.rules.value.tier', { quantity: formatQuantity(tier.min_quantity, locale), percent: formatPercent(tier.percent, locale) }),
        )
        .join(' · ');
  }
}

/** The scope, or the name of its category, product or service; the customer group after it. */
export function appliesToLabel(rule: RuleOut, t: Translate): string {
  const named: Partial<Record<RuleOut['applies_to'], string | null>> = {
    category: rule.category_name,
    product: rule.product_name,
    service: rule.service_name,
  };
  const own = named[rule.applies_to] ?? t('pricing.none');
  const target =
    rule.applies_to in named
      ? rule.target_deleted
        ? t('pricing.rules.targetDeleted', { name: own })
        : own
      : t(`pricing.rules.scope.${rule.applies_to}`);
  if (!rule.customer_group_id) return target;
  return t('pricing.rules.forGroup', { target, group: groupName(rule.customer_group_id, rule.customer_group_name, t) });
}

/** A customer group's name; «Deleted group» when Customers no longer has it; «—» for none. */
export function groupName(id: string | null, name: string | null, t: Translate): string {
  if (name) return name;
  return id ? t('pricing.deletedGroup') : t('pricing.none');
}

/** «Tax included», «Tax excluded», or «Business default» for an empty one. */
export function taxBasisLabel(value: boolean | null, t: Translate): string {
  if (value === null) return t('pricing.taxBasis.business');
  return t(value ? 'pricing.taxBasis.included' : 'pricing.taxBasis.excluded');
}
