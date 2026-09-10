// The NAME of a plan, in the language of the hub — hub#1748.
//
// `billing.tiers[].name` is written by the module author in the source language (ADR-0055), so a
// Spanish hub read «Free · Basic · Pro · Enterprise» on the very screen where the owner decides how
// much to spend a month — while the line right below each price, what the plan includes, had
// already been translated by hub#1604. The module ALREADY publishes the missing half:
// `whatsapp_inbox` ships `billing.tiers = {"free": "Gratis", …}` in its `locales/es.json`, keyed by
// the SLUG of the manifest. The shell simply never read that key.
//
// Same order as its sibling `quotaMetricLabel`: module locale → what the manifest itself says.
import { describe, expect, it } from 'vitest';
import { tierName, type ModuleBillingLocale } from './module-quota';
import type { BillingTierDef } from '@erplora/module-types';

const tier = (over: Partial<BillingTierDef> = {}): BillingTierDef =>
  ({ slug: 'free', name: 'WhatsApp Free', price: 0, ...over }) as BillingTierDef;

describe('tierName (hub#1748)', () => {
  it('takes the name the module ships for that tier slug', () => {
    expect(tierName(tier(), { tiers: { free: 'Gratis' } })).toBe('Gratis');
  });

  it('falls back to the name of the manifest when the module ships no locale', () => {
    expect(tierName(tier(), undefined)).toBe('WhatsApp Free');
    expect(tierName(tier(), { tiers: {} })).toBe('WhatsApp Free');
  });

  it('keeps the manifest name of a slug the locale does not know: older locale, newer tier', () => {
    // The bundle installed here can be newer than the translations shipped with it, exactly like
    // the quota metrics: what the locale does not name stays in the source language, never blank.
    expect(tierName(tier({ slug: 'flex', name: 'WhatsApp Flex' }), { tiers: { free: 'Gratis' } })).toBe(
      'WhatsApp Flex',
    );
  });

  it('treats a blank translation as absent: an untitled card says less than an English one', () => {
    expect(tierName(tier(), { tiers: { free: '   ' } })).toBe('WhatsApp Free');
  });

  it('falls back to the manifest when the "translation" is not a string, instead of breaking the tab', () => {
    // A module author who types the price where the name goes (`"free": 0`) must not blank the
    // whole «Plan» tab with a render error — the same promise `quotaMetricLabel` already keeps.
    const broken = { tiers: { free: 0 } } as unknown as ModuleBillingLocale;

    expect(tierName(tier(), broken)).toBe('WhatsApp Free');
  });

  it('never hands back an empty title: a nameless card says nothing, its slug at least identifies it', () => {
    expect(tierName(tier({ name: '   ' }), { tiers: {} })).toBe('free');
    expect(tierName({ slug: 'pro' } as BillingTierDef, undefined)).toBe('pro');
  });

  it('does not read the quota block as if it named tiers', () => {
    // `quota` is keyed by METRIC and `tiers` by SLUG; one is never a fallback for the other, or a
    // module with a metric called like one of its tiers would retitle a card with a unit of quota.
    const locale = { quota: { free: 'mensajes al mes' } } as ModuleBillingLocale;

    expect(tierName(tier(), locale)).toBe('WhatsApp Free');
  });
});
