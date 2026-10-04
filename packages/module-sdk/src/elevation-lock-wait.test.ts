// hub#2290 — the manager's approval is locked by too many failed tries, and the hub says for how
// long: `POST /api/elevation/approve` answers `429 {ok:false, error:{code:"too_many_attempts",
// message, retry_after_secs}}` (crates/server/src/elevation.rs). The shell's dialog already turns a
// wait into «Wait 4 minutes» (`lockRefusal`, hub#2285) — but only if the wait reaches it, and the
// approval travels through THIS transport. `unwrap` dropped it, so the dialog was the one door of
// the four that said «wait a few minutes».
//
// Correr: pnpm -F @erplora/module-sdk test
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ErploraError, HttpWsTransport } from './index.ts';

const REFUSED = {
  ok: false,
  error: {
    code: 'requires_elevation',
    message: 'requires elevation: `till.void_sale` needs approval from a manager',
    permission: 'till.void_sale',
  },
};

/** The runtime's lock refusal at the approval door, with whatever `retry_after_secs` it named. */
function locked(retryAfter?: unknown): unknown {
  return {
    ok: false,
    error: {
      code: 'too_many_attempts',
      message: 'too many failed attempts: wait a few minutes before approving again',
      ...(retryAfter === undefined ? {} : { retry_after_secs: retryAfter }),
    },
  };
}

/** What `ask.approve` (or `ask.approveWithBadge`) throws when the approval door answers `reply`. */
async function approvalRefusal(reply: unknown, door: 'pin' | 'badge' = 'pin'): Promise<ErploraError> {
  const replies = [REFUSED, reply];
  let n = 0;
  const fetchImpl = (async () => {
    const body = replies[n++];
    return { json: async () => body };
  }) as unknown as typeof fetch;
  let thrown: unknown;
  const t = new HttpWsTransport({
    fetchImpl,
    elevationApprover: async (ask) => {
      try {
        await (door === 'pin' ? ask.approve('Sofía', '8317') : ask.approveWithBadge('0009171456'));
      } catch (e) {
        thrown = e;
      }
      return null;
    },
  });
  await assert.rejects(() => t.command('till.sale.void', { sale_id: 's1' }));
  assert.ok(thrown instanceof ErploraError, `the approval threw ${String(thrown)}`);
  return thrown;
}

test('hub#2290: a locked approval keeps the wait the hub named', async () => {
  const err = await approvalRefusal(locked(240));
  assert.equal(err.code, 'too_many_attempts');
  assert.equal(err.retryAfterSecs, 240);
});

test('hub#2290: the badge door of the approval keeps the wait too', async () => {
  const err = await approvalRefusal(locked(61), 'badge');
  assert.equal(err.retryAfterSecs, 61);
});

test('hub#2290: a lock that is about to lift (0 s) is still a wait, not «no wait»', async () => {
  // `lockRefusal` rounds up to at least one minute; dropping a 0 would fall back to «a few minutes».
  const err = await approvalRefusal(locked(0));
  assert.equal(err.retryAfterSecs, 0);
});

test('hub#2290: no usable wait leaves retryAfterSecs undefined, never a made-up number', async () => {
  for (const unusable of [undefined, '240', -5, null, Number.NaN]) {
    const err = await approvalRefusal(locked(unusable));
    assert.equal(err.code, 'too_many_attempts');
    assert.equal(err.retryAfterSecs, undefined, `retry_after_secs = ${String(unusable)}`);
  }
});

test('hub#2290: a refusal that is not a lock carries no wait', async () => {
  const err = await approvalRefusal({
    ok: false,
    error: { code: 'hub.elevation.rejected', message: 'those details do not approve this action.' },
  });
  assert.equal(err.code, 'hub.elevation.rejected');
  assert.equal(err.retryAfterSecs, undefined);
});

test('hub#2290: the wait is a constructor argument, after the fields', () => {
  const err = new ErploraError('too_many_attempts', 'locked', undefined, undefined, 120);
  assert.equal(err.retryAfterSecs, 120);
  assert.equal(new ErploraError('error', 'x').retryAfterSecs, undefined);
});
