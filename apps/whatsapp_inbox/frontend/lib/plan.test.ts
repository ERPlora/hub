// The plan's WhatsApp messages as the screens read them (WHATSAPP_INBOX-F13): erplora.com sends how many the plan
// includes each month, and 0 means none (ADR-0474: there is no «unlimited»). Before erplora.com speaks, the 0 is
// only the channel's default: nothing is known of the plan yet.
import { describe, expect, it } from 'vitest';

import type { ChannelOut } from '../operations';
import { noAllowance } from './plan';

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
