// What a person reads when a command of printing failed (a FormModal's `error`, a page's notice): the
// server's refusal as it came, translated and with its 422 `fields`; a failure the server did not word (the
// network, an answer that is not the API's envelope, a failure of the server itself — `internal_error`,
// any 5xx —, anything that is not an API error) says the screen's own sentence instead.
import type { FormModalError } from '@erplora/ui/components';
import { ApiError } from '@erplora/ui/sdk';

/** Codes of failures that carry no sentence for a person: the SDK's, and the server's own breakdown. */
const UNWORDED = new Set(['client_error', 'network_error', 'unexpected_response', 'internal_error']);

export function refusal(error: unknown, fallback: string): FormModalError | null {
  if (error === null || error === undefined) return null;
  if (!(error instanceof ApiError)) return { message: fallback };
  const worded = !UNWORDED.has(error.code) && error.status < 500 && error.message.trim() !== '';
  return {
    message: worded ? error.message : fallback,
    code: error.code,
    status: error.status,
    ...(error.fields ? { fields: error.fields } : {}),
  };
}
