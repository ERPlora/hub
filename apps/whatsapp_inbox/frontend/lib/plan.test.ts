// The plan's WhatsApp messages as the screens read them (WHATSAPP_INBOX-F13): erplora.com sends how many the plan
// includes each month, and 0 means none (ADR-0474: there is no «unlimited»). Before erplora.com speaks, the 0 is
// only the channel's default: nothing is known of the plan yet. From 80 % of the month's messages the screens say how
// many are left of how many, as the assistant does with its own (BASE-F104).
import { describe, expect, it } from 'vitest';

import type { ChannelOut } from '../operations';
import { nearCap, noAllowance } from './plan';

const CHANNEL: ChannelOut = {
  status: 'connected',
  phone_number: '+34910000000',
  display_name: 'Peluquería Ana',
  monthly_limit: 0,
  monthly_usage: 0,
  cap_reached: true,
  synced_at: '2026-10-15T09:00:00Z',
  manage_url: 'https://erplora.com',
  plans_url: 'https://erplora.com/store/plans',
};

describe('noAllowance', () => {
  it('is a plan that includes no WhatsApp messages, as erplora.com said', () => {
    expect(noAllowance(CHANNEL)).toBe(true);
  });

  it('is not a plan with messages, spent or not', () => {
    expect(noAllowance({ ...CHANNEL, monthly_limit: 150, monthly_usage: 150 })).toBe(false);
    expect(noAllowance({ ...CHANNEL, monthly_limit: 150, cap_reached: false })).toBe(false);
  });

  it('is not known before erplora.com speaks, nor without the channel', () => {
    expect(noAllowance({ ...CHANNEL, synced_at: null, cap_reached: false })).toBe(false);
    expect(noAllowance(null)).toBe(false);
    expect(noAllowance(undefined)).toBe(false);
  });
});

describe('nearCap', () => {
  const WITH = { ...CHANNEL, monthly_limit: 150, monthly_usage: 0, cap_reached: false };

  it('from 80 % of the month\'s messages, how many are left of how many', () => {
    expect(nearCap({ ...WITH, monthly_usage: 120 })).toEqual({ left: 30, limit: 150 });
    expect(nearCap({ ...WITH, monthly_usage: 149 })).toEqual({ left: 1, limit: 150 });
    expect(nearCap({ ...WITH, monthly_limit: 10, monthly_usage: 8 })).toEqual({ left: 2, limit: 10 });
  });

  it('is nothing below 80 %', () => {
    expect(nearCap({ ...WITH, monthly_usage: 119 })).toBeNull();
    expect(nearCap({ ...WITH, monthly_usage: 0 })).toBeNull();
    expect(nearCap({ ...WITH, monthly_limit: 10, monthly_usage: 7 })).toBeNull();
  });

  it('is nothing once the month is spent: the cap says it instead', () => {
    expect(nearCap({ ...WITH, monthly_usage: 150, cap_reached: true })).toBeNull();
  });

  it('is nothing with a plan without messages, before erplora.com speaks, nor without the channel', () => {
    expect(nearCap(CHANNEL)).toBeNull();
    // Even if a photo said 0 without the cap: never «0 of 0 left».
    expect(nearCap({ ...WITH, monthly_limit: 0, monthly_usage: 0, cap_reached: false })).toBeNull();
    expect(nearCap({ ...WITH, monthly_usage: 140, synced_at: null })).toBeNull();
    expect(nearCap(null)).toBeNull();
    expect(nearCap(undefined)).toBeNull();
  });
});
