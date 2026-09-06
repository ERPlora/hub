// What a paid tier INCLUDES, in words the customer reads — hub#1604.
import { describe, expect, it } from 'vitest';
import {
  humanizeQuotaMetric,
  quotaLabel,
  quotaMetricLabel,
  type ModuleBillingLocale,
} from './module-quota';
import type { BillingTierDef } from '@erplora/module-types';

const tier = (quota: unknown): BillingTierDef =>
  ({ slug: 'free', name: 'Free', price: 0, quota }) as unknown as BillingTierDef;

describe('quotaMetricLabel', () => {
  it('takes the label the module ships for that metric', () => {
    const locale = { quota: { conversations_per_month: 'conversaciones al mes' } };

    expect(quotaMetricLabel(locale, 'conversations_per_month')).toBe('conversaciones al mes');
  });

  it('falls back to the canonical English of the metric when the module ships none', () => {
    expect(quotaMetricLabel(undefined, 'conversations_per_month')).toBe('conversations per month');
    expect(quotaMetricLabel({ quota: {} }, 'messages_per_month')).toBe('messages per month');
  });

  it('treats a blank translation as absent: an empty label is worse than an English one', () => {
    expect(quotaMetricLabel({ quota: { conversations_per_month: '   ' } }, 'conversations_per_month'))
      .toBe('conversations per month');
  });

  it('falls back to English when the "translation" is not a string, instead of breaking the screen', () => {
    // A module author who types the limit where the label goes (`"conversations_per_month": 30`)
    // must not blank the whole «Plan» tab with a render error: the runtime promises that an invalid
    // locale never breaks a screen (`load_locales` is best-effort), so English takes over here too.
    const broken = { quota: { conversations_per_month: 30 } } as unknown as ModuleBillingLocale;

    expect(quotaMetricLabel(broken, 'conversations_per_month')).toBe('conversations per month');
  });

  it('never hands back a metric that reads as an identifier', () => {
    expect(quotaMetricLabel(undefined, 'conversations_per_month')).not.toContain('_');
    // Degenerate metric: humanising it leaves nothing, so the name itself is the last resort —
    // a number with no unit next to it says even less than an ugly one.
    expect(quotaMetricLabel(undefined, '__')).toBe('__');
  });
});

describe('humanizeQuotaMetric', () => {
  it('reads as prose inside a sentence, so it is not Title Cased', () => {
    // `humanizeSettingKey` (hub#1094) Title Cases because it labels a form field on its own line.
    // This one lands mid-sentence — «Includes 30 conversations per month» — where capitals shout.
    expect(humanizeQuotaMetric('conversations_per_month')).toBe('conversations per month');
  });
});

describe('quotaLabel', () => {
  it('states every metric of the tier, translated', () => {
    const locale = { quota: { conversations_per_month: 'conversaciones al mes', seats: 'usuarios' } };

    expect(quotaLabel(tier({ conversations_per_month: 200, seats: 3 }), locale))
      .toBe('200 conversaciones al mes · 3 usuarios');
  });

  it('says nothing when the tier declares no quota', () => {
    expect(quotaLabel(tier(undefined), undefined)).toBe('');
    expect(quotaLabel(tier({}), undefined)).toBe('');
  });

  it('says nothing when the quota is not the dict the schema declares', () => {
    // `module.schema.json` says `{ metric: limit }`; the TS type still says `number | string`
    // (hub#1609). Until that is settled, a scalar is not paintable and stays silent.
    expect(quotaLabel(tier(200), undefined)).toBe('');
    expect(quotaLabel(tier('200 messages'), undefined)).toBe('');
  });
});
