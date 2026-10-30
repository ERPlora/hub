// The plan's WhatsApp messages as the screens read them (WHATSAPP_INBOX-F13).
import type { ChannelOut } from '../operations';

/** The plan includes no WhatsApp messages (0 = none, ADR-0474; never «unlimited»), as erplora.com said: before it
 *  speaks, the 0 is only the channel's default. */
export function noAllowance(channel: ChannelOut | null | undefined): boolean {
  return !!channel && channel.synced_at !== null && channel.monthly_limit === 0;
}

/** From 80 % of the month's messages the screens say how many are left (BASE-F104 does the same for the assistant). */
export const WARN_FROM = 0.8;

/** How many of the month's messages are left of how many, from 80 % of them; nothing below, once they are spent (the
 *  cap says it instead), with a plan that includes none, or before erplora.com speaks. */
export function nearCap(channel: ChannelOut | null | undefined): { left: number; limit: number } | null {
  if (!channel || channel.synced_at === null || channel.cap_reached || channel.monthly_limit <= 0) return null;
  if (channel.monthly_usage / channel.monthly_limit < WARN_FROM) return null;
  return { left: Math.max(channel.monthly_limit - channel.monthly_usage, 0), limit: channel.monthly_limit };
}
