// What the WhatsApp e2e ask erplora.com's own test seed (whatsapp_hub_seed.py) and what it leaves in `a`: the month's
// usage it is told (`--used`) and the templates it keeps as Meta lists them (FIX-HUB-WHATSAPP-INBOX-E2E-SEED-TEMPLATES-AND-CAP-UNUSED).
// flow: WHATSAPP_INBOX-F13, WHATSAPP_INBOX-F27, WHATSAPP_INBOX-F28
import { describe, expect, it } from 'vitest';

import { SEED_TEMPLATES, seedArguments } from './whatsapp-seed';

describe('seedArguments', () => {
  it('asks nothing more without a usage: the seed leaves the month at 0', () => {
    expect(seedArguments({})).toEqual([]);
  });

  it('passes the month’s usage as the seed takes it, 0 included', () => {
    expect(seedArguments({ used: 150 })).toEqual(['--used', '150']);
    expect(seedArguments({ used: 0 })).toEqual(['--used', '0']);
  });

  it('refuses what the seed would refuse, before running it', () => {
    for (const used of [-1, 1.5, Number.NaN, Number.POSITIVE_INFINITY]) {
      expect(() => seedArguments({ used }), String(used)).toThrow(/whole number not below zero/);
    }
  });
});

describe('SEED_TEMPLATES', () => {
  it('names the seed’s templates, which the e2e’s cleanUp deletes after a run', () => {
    for (const name of Object.values(SEED_TEMPLATES)) expect(name).toMatch(/^e2e_seed_[a-z_]+$/);
  });

  it('has one of each verdict of Meta and one made in WhatsApp Manager the Hub cannot fill', () => {
    expect(Object.keys(SEED_TEMPLATES).sort()).toEqual(['approved', 'inReview', 'manager', 'rejected']);
    expect(new Set(Object.values(SEED_TEMPLATES)).size).toBe(4);
  });
});
