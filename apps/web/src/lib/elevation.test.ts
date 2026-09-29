// @vitest-environment node
// hub#363 — the shell half of the manager's PIN: the state one dialog hangs off, and the sentence
// a refusal earns.
//
// The transport (`@erplora/module-sdk`) decides WHEN approval is needed and what to do with the
// token; this file decides only what the person at the till sees while that happens. Two things are
// worth pinning here because both are ways to quietly undo a decision made in the runtime:
//
//   1. a second ask must not stack a second modal on top of the first, and
//   2. the refusals the runtime made INDISTINGUISHABLE must stay indistinguishable on screen.
import { describe, expect, it, beforeEach } from 'vitest';
import type { ElevationAsk } from '@erplora/module-sdk';
import { ErploraError } from '@erplora/module-sdk';

import {
  askForApproval,
  pendingElevation,
  resolveElevation,
  elevationRefusal,
} from './elevation';

function ask(payload: Record<string, unknown> = { sale_id: 's1' }): ElevationAsk {
  return {
    command: 'till.sale.void',
    payload,
    permission: 'till.void_sale',
    approve: async () => ({
      token: 'tok',
      permission: 'till.void_sale',
      approvedBy: 'u-sofia',
      approverName: 'Sofía',
      expiresInSeconds: 120,
    }),
    approveWithBadge: async () => ({
      token: 'tok',
      permission: 'till.void_sale',
      approvedBy: 'u-sofia',
      approverName: 'Sofía',
      expiresInSeconds: 120,
    }),
  };
}

beforeEach(() => {
  // Nothing on screen between tests: a leaked pending ask would make the next one look "already
  // open" and pass the busy test for the wrong reason.
  resolveElevation(null);
});

describe('the dialog the transport opens', () => {
  it('publishes what is being approved and waits for a person', async () => {
    const pending = askForApproval(ask());
    expect(pendingElevation.value?.command).toBe('till.sale.void');
    expect(pendingElevation.value?.permission).toBe('till.void_sale');

    let settled = false;
    void pending.then(() => {
      settled = true;
    });
    await Promise.resolve();
    expect(settled, 'nothing resolves until somebody taps').toBe(false);

    resolveElevation('tok-abc');
    expect(await pending).toBe('tok-abc');
    expect(pendingElevation.value, 'the dialog closes with the answer').toBeNull();
  });

  it('gives back `null` when the cashier closes it', async () => {
    const pending = askForApproval(ask());
    resolveElevation(null);
    expect(await pending).toBeNull();
    expect(pendingElevation.value).toBeNull();
  });

  it('refuses a second ask instead of stacking a modal over the open one', async () => {
    // A modal on top of a modal is how a manager approves the wrong action: they see one sentence
    // and a pinpad, and nothing on screen says which of the two it belongs to. The second caller
    // gets `null` — its own refusal, unchanged — and the cashier taps again when the first is done.
    const first = askForApproval(ask({ sale_id: 's1' }));
    const second = askForApproval(ask({ sale_id: 's2' }));

    expect(await second).toBeNull();
    expect(pendingElevation.value?.payload, 'the open dialog is untouched').toEqual({ sale_id: 's1' });

    resolveElevation('tok-abc');
    expect(await first).toBe('tok-abc');
  });

  it('is ready again once the first one is answered', async () => {
    const first = askForApproval(ask({ sale_id: 's1' }));
    resolveElevation(null);
    await first;

    const second = askForApproval(ask({ sale_id: 's2' }));
    expect(pendingElevation.value?.payload).toEqual({ sale_id: 's2' });
    resolveElevation('tok-2');
    expect(await second).toBe('tok-2');
  });

  it('answering when nothing is open changes nothing', () => {
    expect(() => resolveElevation('tok')).not.toThrow();
    expect(pendingElevation.value).toBeNull();
  });
});

describe('what a refused approval is told', () => {
  const refusal = (code: string): ErploraError => new ErploraError(code, 'whatever');

  it('gives each runtime refusal its own sentence', () => {
    expect(elevationRefusal(refusal('hub.elevation.rejected')).key).toBe('elevation.rejected');
    expect(elevationRefusal(refusal('hub.elevation.approver_cannot')).key).toBe(
      'elevation.approverCannot',
    );
    expect(elevationRefusal(refusal('hub.elevation.not_elevable')).key).toBe('elevation.notElevable');
    expect(elevationRefusal(refusal('hub.elevation.not_required')).key).toBe('elevation.notRequired');
    // hub#2285: the lock is the login pinpad's lock, and says the pinpad's sentence — with the
    // minutes when the refusal carries the wait.
    expect(elevationRefusal(refusal('too_many_attempts'))).toEqual({ key: 'login.pinTooManyAttemptsNoWait' });
    expect(elevationRefusal(Object.assign(refusal('too_many_attempts'), { retryAfterSecs: 61 }))).toEqual({
      key: 'login.pinTooManyAttempts',
      minutes: 2,
    });
  });

  it('falls back to «could not be done», never to «wrong PIN»', () => {
    // The login pinpad falls back to «Incorrect PIN» because there the only realistic cause IS the
    // digits. Here it is not: a dropped connection, a command that vanished with an app, a code
    // this build has never seen. Telling somebody their PIN is wrong when it is right is how the
    // shop ends up sharing the manager's credential — the exact outcome elevation exists to avoid.
    expect(elevationRefusal(new Error('network down')).key).toBe('elevation.failed');
    expect(elevationRefusal(refusal('hub.elevation.something_new')).key).toBe('elevation.failed');
    expect(elevationRefusal(refusal('command_not_found')).key).toBe('elevation.failed');
    expect(elevationRefusal(null).key).toBe('elevation.failed');
  });

  it('does not read a code out of anything but the code', () => {
    // A message is prose: it gets rewritten, translated and reworded. Matching on it is how a
    // refusal silently starts landing on the wrong sentence.
    const worded = new ErploraError('too_many_attempts', 'those details do not approve this action');
    expect(elevationRefusal(worded)).toEqual({ key: 'login.pinTooManyAttemptsNoWait' });
  });
});
