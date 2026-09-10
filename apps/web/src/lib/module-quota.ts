/**
 * What a paid tier INCLUDES, put into words the customer can read — hub#1604.
 *
 * `billing.tiers[].quota` of a manifest is a dict of `{ metric: limit }` (`module.schema.json`), and
 * the metric is a snake_case identifier its author writes: `conversations_per_month`. The «Plan» tab
 * used to paint it by swapping the underscores for spaces, so a Spanish hub read «Incluye 30
 * conversations per month» — half the sentence translated, half of it not, on the screen where the
 * owner decides how much to spend every month.
 *
 * The way out is the one hub#1094 already settled for the generated settings screen, which had the
 * very same shape of defect: the words come from the module's own `locales/<lang>.json`, because the
 * only one who knows what `conversations_per_month` means in Spanish is whoever wrote the manifest.
 * The shell does NOT keep a table of metric names — that would be the shell knowing the vocabulary
 * of every module ever published.
 *
 * Order: **module locale → canonical English of the metric**. English is the source language
 * (ADR-0055), so a module that ships no translation shows English, exactly like its settings screen.
 */
import type { BillingTierDef } from '@erplora/module-types';

/**
 * The `billing` block of a module's `locales/<lang>.json` (ADR-0055) — hub#1604.
 *
 * Same shape as the `settings` and `widgets` blocks the shell already reads from that file, keyed by
 * the metric the manifest declares: `{ "quota": { "conversations_per_month": "conversaciones al mes" } }`.
 */
export interface ModuleBillingLocale {
  /** One label per quota METRIC, keyed by the metric name written in `billing.tiers[].quota`. */
  quota?: Record<string, string | undefined>;
  /** One name per TIER, keyed by the slug written in `billing.tiers[].slug` — hub#1748. */
  tiers?: Record<string, string | undefined>;
}

/**
 * A snake_case metric → the English prose it already is: `conversations per month`.
 *
 * Lower case on purpose, unlike [`humanizeSettingKey`] (hub#1094): that one names a form field on a
 * line of its own, where Title Case reads as a label. This one lands in the middle of a sentence
 * («Includes 30 conversations per month»), where capitals would shout.
 */
export function humanizeQuotaMetric(metric: string): string {
  return metric.replace(/_/g, ' ').trim();
}

/**
 * How ONE metric is named on screen.
 *
 * A blank-but-present translation counts as absent: a module shipping `"  "` would otherwise paint a
 * number with no unit after it, which says strictly less than the English it replaced.
 */
export function quotaMetricLabel(
  locale: ModuleBillingLocale | undefined,
  metric: string,
): string {
  const raw = locale?.quota?.[metric];
  // Only a string is a label. A module author who types the limit where the label goes
  // (`"conversations_per_month": 30`) must not blank the whole tab with a render error: the runtime
  // promises that an invalid locale never breaks a screen, so English takes over here as well.
  const translated = typeof raw === 'string' ? raw.trim() : '';
  if (translated) return translated;
  // A metric made only of separators humanises to nothing; then its own name is the last resort,
  // because a bare number tells the customer even less than an ugly word does.
  return humanizeQuotaMetric(metric) || metric;
}

/**
 * How ONE tier is NAMED on screen — hub#1748.
 *
 * The sibling of [`quotaMetricLabel`] one field over: `billing.tiers[].name` is prose the module
 * author writes in the source language, so a Spanish hub read «Free · Basic · Pro · Enterprise»
 * right above a quota line that hub#1604 had already translated. The module publishes the names in
 * the same `billing` block of its `locales/<lang>.json`, keyed by tier SLUG — the shell only has to
 * read them, and it keeps no table of its own: the plans of every module ever published are not
 * vocabulary the shell can own.
 *
 * Order: **module locale → the name in the manifest → its slug**. The last step is the floor: a
 * card with no title at all says strictly less than an untranslated one.
 */
export function tierName(
  tier: BillingTierDef,
  locale: ModuleBillingLocale | undefined,
): string {
  const raw = locale?.tiers?.[tier.slug];
  // Only a string is a name — an author who types the price where the name goes (`"free": 0`) must
  // not blank the «Plan» tab with a render error, the same promise `quotaMetricLabel` keeps. Blank
  // counts as absent for the same reason.
  const translated = typeof raw === 'string' ? raw.trim() : '';
  if (translated) return translated;
  const declared = typeof tier.name === 'string' ? tier.name.trim() : '';
  return declared || tier.slug;
}

/**
 * Everything a tier includes, in one line: `200 conversaciones al mes · 3 usuarios`.
 *
 * Empty when the tier declares no quota, and empty as well when `quota` is not the dict the schema
 * declares — a scalar carries no metric to name, so there is nothing truthful to paint (hub#1609).
 */
export function quotaLabel(
  tier: BillingTierDef,
  locale: ModuleBillingLocale | undefined,
): string {
  const quota = tier.quota;
  if (!quota || typeof quota !== 'object') return '';
  return Object.entries(quota)
    .map(([metric, limit]) => `${limit} ${quotaMetricLabel(locale, metric)}`)
    .join(' · ');
}
