// What a person reads when a back-office command failed (a FormModal's `error`, a page notice): the
// server's refusal as it came, translated and with its 422 `fields`; a failure the server did not word
// (the network, an answer that is not the API's envelope) says the screen's own sentence instead.
import type { FormModalError } from '@erplora/ui/components';
import type { ApiError } from '@erplora/ui/sdk';

/** Codes the SDK gives to failures that carry no sentence of the server. */
const UNWORDED = new Set(['client_error', 'unexpected_response']);

export function refusal(error: ApiError | null | undefined, fallback: string): FormModalError | null {
  if (!error) return null;
  const worded = !UNWORDED.has(error.code) && error.message.trim() !== '';
  return {
    message: worded ? error.message : fallback,
    code: error.code,
    status: error.status,
    ...(error.fields ? { fields: error.fields } : {}),
  };
}
