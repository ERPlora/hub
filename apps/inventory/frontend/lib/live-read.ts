import type { ApiError, LiveStatus } from '@erplora/ui/sdk';

/** Whether a field fed by a live read has to say the read failed. An error frame always says it. A failure the stream
 *  heard before the read ever answered says it too while the stream tries again: the field has nothing to show and the
 *  page's «Reconnecting…» strip lies behind the dialog. Over what it already answered it says nothing: what is painted
 *  stays until the stream is back. */
export function readFailed(status: LiveStatus, error: ApiError | null, answered: boolean): boolean {
  return !!error && (status === 'error' || !answered);
}
