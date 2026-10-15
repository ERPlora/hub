// How the modifier screens paint a supplement and a group's rule (pages never format by hand), in the page
// language's own format (Intl). Money is whole cents of euros: the Hub has no currency setting and every
// ERPlora business invoices in euros. A supplement may be negative (a discount) and carries its sign;
// 0 is free.

const CURRENCY = 'EUR';

const formats = new Map<string, Intl.NumberFormat>();
const decimalMarks = new Map<string, string>();

function moneyFormat(locale: string, signed: boolean): Intl.NumberFormat {
  const key = `${locale}|${signed}`;
  let found = formats.get(key);
  if (!found) {
    found = new Intl.NumberFormat(locale, { style: 'currency', currency: CURRENCY, ...(signed ? { signDisplay: 'exceptZero' } : {}) });
    formats.set(key, found);
  }
  return found;
}

/** The decimal mark of `locale` («,» in Spanish, «.» in English). */
export function decimalMark(locale: string): string {
  let found = decimalMarks.get(locale);
  if (!found) {
    found = new Intl.NumberFormat(locale).formatToParts(1.5).find((part) => part.type === 'decimal')?.value ?? '.';
    decimalMarks.set(locale, found);
  }
  return found;
}

/** Whole cents as euros in `locale` («1,50 €», «€1.50»). */
export function formatMoney(cents: number, locale: string): string {
  return moneyFormat(locale, false).format(cents / 100);
}

/** A supplement with its sign («+1,00 €», «-0,50 €»); `free` for 0. */
export function formatDelta(cents: number, locale: string, free: string): string {
  return cents === 0 ? free : moneyFormat(locale, true).format(cents / 100);
}

/** What `choiceRule` reads of a group. */
export interface GroupRule {
  min_choices: number;
  max_choices: number;
  allow_repeat: boolean;
}

type Translate = (key: string, named?: Record<string, unknown>) => string;

/** «Optional» or «Required (min. N)», then « · max. N» with a ceiling and « · repeats» when it repeats. */
export function choiceRule(group: GroupRule, t: Translate): string {
  const parts = [group.min_choices >= 1 ? t('modifier.rule.required', { min: group.min_choices }) : t('modifier.rule.optional')];
  if (group.max_choices > 0) parts.push(t('modifier.rule.max', { max: group.max_choices }));
  if (group.allow_repeat) parts.push(t('modifier.rule.repeat'));
  return parts.join(' · ');
}
