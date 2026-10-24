// The charge of the charge sheet (SALE-F01, F06, F14). Its contract with the server:
//   - The attempt key is born with the sheet (this composable lives as long as one opening of it) and
//     travels on every retry of that attempt: the server records at most one sale per key and answers
//     a repeat with the sale it already has (`already`). It changes only after a definitive refusal,
//     when the server said nothing was charged under it.
//   - The door: `sale.sale.complete`; a discount over the business's cap that nobody approved comes back
//     as `sale.discount_over_limit`, and the charge goes again through `sale.sale.complete_over_limit`
//     with the same payload and key: directly for whoever may approve it (`sale.discount_over_limit`),
//     with a manager's approval on this very device for anybody else (BASE-F84).
//   - A lost answer (no network, a 5xx, a page that is not the API's) or the same attempt already being
//     recorded (`sale.checkout_in_progress`) is never read as «not charged»: the sale is looked up by
//     its key, up to twice. Charged → it finishes as a charge; not there → the server is not answering
//     and the next press reuses the key; no answer either → unknown, to be checked in Sales.
import { useSession } from '@erplora/ui/shell';
import { ApiError, useLiveClient } from '@erplora/ui/sdk';
import { readonly, shallowRef } from 'vue';

import { throughManager } from '../../lib/approval';
import type { CompleteIn, SaleOut } from '../../operations';

/** The wait between the two lookups of a lost answer (a restarting server needs a moment). */
export const RECOVERY_DELAY_MS = 1500;
const LOOKUPS = 2;

export type CheckoutFailure =
  | { kind: 'refused'; code: string; message: string; fields?: Record<string, string> }
  | { kind: 'not_charged' }
  | { kind: 'unknown' };

type Lookup = { outcome: 'charged'; sale: SaleOut } | { outcome: 'not_charged' } | { outcome: 'unknown' };

export interface UseCheckoutOptions {
  /** The sale is recorded (also when the lookup found it). */
  onCharged: (sale: SaleOut) => void;
}

const newKey = (): string => `sale-${globalThis.crypto.randomUUID()}`;

/** The answer never arrived or could not be read: whether it charged is unknown. */
function answerLost(error: unknown): boolean {
  if (!(error instanceof ApiError)) return true;
  return error.status === 0 || error.status >= 500 || error.code === 'unexpected_response' || error.code === 'sale.checkout_in_progress';
}

export function useCheckout(options: UseCheckoutOptions) {
  const client = useLiveClient();
  const session = useSession();
  const key = shallowRef(newKey());
  const busy = shallowRef(false);
  const failure = shallowRef<CheckoutFailure | null>(null);

  function send(input: CompleteIn): Promise<SaleOut> {
    return throughManager(
      () => client.api.call('sale.sale.complete', input),
      () => client.api.call('sale.sale.complete_over_limit', input),
      { code: 'sale.discount_over_limit', may: session.can('sale.discount_over_limit') },
    );
  }

  const pause = (ms: number) => new Promise<void>((resolve) => client.schedule(resolve, ms));

  async function lookUp(attemptKey: string): Promise<Lookup> {
    for (let attempt = 1; attempt <= LOOKUPS; attempt++) {
      try {
        const found = await client.api.call('sale.sale.by_idempotency_key', { idempotency_key: attemptKey });
        return found.found && found.sale ? { outcome: 'charged', sale: found.sale } : { outcome: 'not_charged' };
      } catch {
        if (attempt < LOOKUPS) await pause(RECOVERY_DELAY_MS);
      }
    }
    return { outcome: 'unknown' };
  }

  /** Charges `input` with this attempt's key; a press while one is in flight does nothing. */
  async function charge(input: Omit<CompleteIn, 'idempotency_key'>): Promise<void> {
    if (busy.value) return;
    busy.value = true;
    failure.value = null;
    const attemptKey = key.value;
    try {
      options.onCharged(await send({ ...input, idempotency_key: attemptKey }));
    } catch (error) {
      if (!answerLost(error)) {
        const refused = error as ApiError;
        failure.value = {
          kind: 'refused',
          code: refused.code,
          message: refused.message,
          ...(refused.fields ? { fields: { ...refused.fields } } : {}),
        };
        key.value = newKey();
        return;
      }
      const found = await lookUp(attemptKey);
      if (found.outcome === 'charged') options.onCharged(found.sale);
      else failure.value = { kind: found.outcome };
    } finally {
      busy.value = false;
    }
  }

  return { key: readonly(key), busy: readonly(busy), failure: readonly(failure), charge };
}
