// What a person reads when something of Automations fails (hub#2320; the pattern of printing's and
// sale's `refusal.ts`): the server's refusal as it came, already in the person's language; a failure the
// server did not word — the network, an answer that is not the API's envelope, a failure of the server
// itself (`internal_error`, any 5xx), anything that is not an API error — says the screen's sentence.
import { ApiError } from '@erplora/ui/sdk';

/** Codes of failures that carry no sentence for a person: the SDK's, and the server's own breakdown. */
const UNWORDED = new Set(['client_error', 'network_error', 'unexpected_response', 'internal_error']);

/** The sentence to show for `error`, or `''` when nothing failed. Also takes a live query's error frame
 *  (`{code, message}`), which the server always words unless it broke. */
export function wording(error: unknown, fallback: string): string {
  if (error === null || error === undefined) return '';
  if (error instanceof ApiError) {
    const worded = !UNWORDED.has(error.code) && error.status > 0 && error.status < 500 && error.message.trim() !== '';
    return worded ? error.message : fallback;
  }
  if (error instanceof Error || typeof error !== 'object') return fallback;
  const { code, message } = error as { code?: unknown; message?: unknown };
  const worded = typeof message === 'string' && message.trim() !== '' && !(typeof code === 'string' && UNWORDED.has(code));
  return worded ? message : fallback;
}
