// What the till says when one of its actions fails: the server's refusal as it came; a request that never reached the
// server, the SDK's own sentence, already in the person's language, which says the connection is missing (on a
// tablet that lost its wifi, the action's sentence made the waiter think the product or the kitchen was at fault);
// any other failure nobody worded, the till's sentence for that action (`fallbackKey`).
import { ApiError } from '@erplora/ui/sdk';

import { refusal } from '../../lib/refusal';
import { useT } from '../useT';

export function useWordsOf(): (error: unknown, fallbackKey: string) => string {
  const t = useT();
  return (error, fallbackKey) => {
    if (error instanceof ApiError && error.code === 'network_error') return error.message;
    const fallback = t(fallbackKey);
    return refusal(error, fallback)?.message ?? fallback;
  };
}
