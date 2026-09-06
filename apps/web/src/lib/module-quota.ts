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
  const translated = locale?.quota?.[metric]?.trim();
  if (translated) return translated;
  // A metric made only of separators humanises to nothing; then its own name is the last resort,
  // because a bare number tells the customer even less than an ugly word does.
  return humanizeQuotaMetric(metric) || metric;
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
