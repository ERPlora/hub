// @vitest-environment happy-dom
// What a module has SPENT of what its plan includes — ERPlora/whatsapp_inbox#131.
//
// The «Plan» tab painted the allowance (`billing.tiers[].quota`) and never the consumption, so the
// one number that says «your channel is about to stop answering» was invisible: a salon found out
// its WhatsApp quota was gone because WhatsApp stopped replying.
//
// This is the PURE half — reading the module's answer and turning it into a fraction and a tone.
// The I/O and the painting are `ModulePlanPanel.vue`; kept apart so the contract of «what counts as
// a readable number» can be pinned without mounting a component.
import { describe, expect, it } from 'vitest';

import {
  readModuleUsage,
  usageFraction,
  usageTone,
  type ModuleUsageDef,
} from './module-usage';

/** The `billing.usage` block of the published `whatsapp_inbox` manifest. */
const DEF: ModuleUsageDef = {
  query: 'whatsapp_inbox.usage.get',
  metric: 'conversations_per_month',
  used: 'inbound_this_month',
  limit: 'monthly_limit',
};

describe('readModuleUsage — the module answers, the shell reads', () => {
  it('reads used and limit out of the first row', () => {
    const rows = [{ inbound_this_month: 24, monthly_limit: 30 }];
    expect(readModuleUsage(rows, DEF)).toEqual({ used: 24, limit: 30 });
  });

  it('reads a single object as well as a one-row array', () => {
    // `client.query` hands back whatever the query shapes; `ModuleSettingsForm` already accepts
    // both, and a module author must not have to know which one the shell prefers.
    expect(readModuleUsage({ inbound_this_month: 7, monthly_limit: 30 }, DEF)).toEqual({
      used: 7,
      limit: 30,
    });
  });

  it('reads numbers that arrive as strings, which is what SQLite counts do over JSON', () => {
    expect(readModuleUsage([{ inbound_this_month: '24', monthly_limit: '30' }], DEF)).toEqual({
      used: 24,
      limit: 30,
    });
  });

  it('treats a limit of 0 as no cap, because that is what the manifest means by it', () => {
    // `whatsapp_inbox.usage.get`: «the monthly allowance of the plan (0 = no cap)».
    expect(readModuleUsage([{ inbound_this_month: 24, monthly_limit: 0 }], DEF)).toEqual({
      used: 24,
      limit: null,
    });
  });

  it('has no limit when the manifest names no limit column', () => {
    const noLimit: ModuleUsageDef = { ...DEF, limit: undefined };
    expect(readModuleUsage([{ inbound_this_month: 24, monthly_limit: 30 }], noLimit)).toEqual({
      used: 24,
      limit: null,
    });
  });

  it('gives up when the query answers nothing', () => {
    expect(readModuleUsage([], DEF)).toBeNull();
    expect(readModuleUsage(null, DEF)).toBeNull();
    expect(readModuleUsage(undefined, DEF)).toBeNull();
  });

  it('gives up when the used column is missing or is not a number', () => {
    // Painting «NaN of 30» is worse than painting nothing: it is a number the customer will read.
    expect(readModuleUsage([{ monthly_limit: 30 }], DEF)).toBeNull();
    expect(readModuleUsage([{ inbound_this_month: 'many', monthly_limit: 30 }], DEF)).toBeNull();
    expect(readModuleUsage([{ inbound_this_month: null, monthly_limit: 30 }], DEF)).toBeNull();
    expect(readModuleUsage([{ inbound_this_month: -1, monthly_limit: 30 }], DEF)).toBeNull();
  });

  it('keeps the count when only the limit is unreadable — the consumption is still true', () => {
    expect(readModuleUsage([{ inbound_this_month: 24, monthly_limit: 'lots' }], DEF)).toEqual({
      used: 24,
      limit: null,
    });
  });
});

describe('usageFraction — how full the bar is', () => {
  it('is used over limit', () => {
    expect(usageFraction({ used: 15, limit: 30 })).toBe(0.5);
  });

  it('never goes over 1, so a hub over its allowance still paints a full bar', () => {
    expect(usageFraction({ used: 45, limit: 30 })).toBe(1);
  });

  it('is null without a limit: there is no bar to fill', () => {
    expect(usageFraction({ used: 45, limit: null })).toBeNull();
  });
});

describe('usageTone — the same thresholds the hub plan screen already uses', () => {
  // `PlanLimitsPanel.toneFor`: green under 80 %, amber 80–90 %, red at 90 % and over. Two screens
  // about what your plan includes must not disagree on when a number turns worrying.
  it('is calm below 80 %', () => {
    expect(usageTone(0.5)).toBe('success');
    expect(usageTone(0.79)).toBe('success');
  });

  it('warns from 80 %', () => {
    expect(usageTone(0.8)).toBe('warning');
    expect(usageTone(0.89)).toBe('warning');
  });

  it('alarms from 90 %', () => {
    expect(usageTone(0.9)).toBe('danger');
    expect(usageTone(1)).toBe('danger');
  });

  it('is neutral with no fraction to judge', () => {
    expect(usageTone(null)).toBe('neutral');
  });
});
