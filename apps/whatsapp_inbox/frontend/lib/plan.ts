// The plan's WhatsApp messages as the screens read them (WHATSAPP_INBOX-F13).
import type { ChannelOut } from '../operations';

/** The plan includes no WhatsApp messages (0 = none, ADR-0474; never «unlimited»), as erplora.com said: before it
 *  speaks, the 0 is only the channel's default. */
export function noAllowance(channel: ChannelOut | null | undefined): boolean {
  return !!channel && channel.synced_at !== null && channel.monthly_limit === 0;
}
