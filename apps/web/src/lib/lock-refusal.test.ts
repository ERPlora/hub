// hub#2285 — **every door with a PIN or a badge says how long the lock lasts**, with one sentence.
//
// hub#2283 taught the login pinpad to read the wait off `429 too_many_attempts` and say «wait N
// minutes». The badge, the hand-over overlay and the manager's approval kept «a few minutes» — and
// the badge added «or use your PIN», which is wrong advice when the lock is on the whole address
// (hub#2282): the PIN is locked too. This is the one reader the four doors share.
import { describe, expect, it } from 'vitest';
import { createI18n } from 'vue-i18n';

import { lockRefusal, sayRefusal } from './lock-refusal';
import en from '../i18n/locales/en';
import es from '../i18n/locales/es';

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: { en, es },
});

/** A refusal shaped like `RuntimeError`: the stable `code` and, on a lock, the wait. */
function locked(retryAfterSecs?: number): Error & { code: string; retryAfterSecs?: number } {
  return Object.assign(
    new Error('refused'),
    { code: 'too_many_attempts' },
    retryAfterSecs === undefined ? {} : { retryAfterSecs },
  );
}

describe('lockRefusal', () => {
  it('names the wait in whole minutes', () => {
    expect(lockRefusal(locked(240))).toEqual({ key: 'login.pinTooManyAttempts', minutes: 4 });
  });

  it('rounds a part-minute UP, so nobody retries into a lock that is still on', () => {
    expect(lockRefusal(locked(61))).toEqual({ key: 'login.pinTooManyAttempts', minutes: 2 });
  });

  it('never says «0 minutes» when the lock is lifting right now', () => {
    expect(lockRefusal(locked(0))).toEqual({ key: 'login.pinTooManyAttempts', minutes: 1 });
  });

  it('still says «wait» when the hub named no wait', () => {
    expect(lockRefusal(locked())).toEqual({ key: 'login.pinTooManyAttemptsNoWait' });
    expect(lockRefusal(Object.assign(locked(), { retryAfterSecs: '240' }))).toEqual({
      key: 'login.pinTooManyAttemptsNoWait',
    });
  });
});

describe('sayRefusal', () => {
  it.each(['en', 'es'] as const)('says one minute in the singular (%s)', (locale) => {
    i18n.global.locale.value = locale;
    const t = i18n.global.t;
    const one = sayRefusal(t, { key: 'login.pinTooManyAttempts', minutes: 1 });
    const two = sayRefusal(t, { key: 'login.pinTooManyAttempts', minutes: 2 });

    expect(one).toContain('1');
    expect(two).toContain('2');
    expect(one).not.toBe(two.replace('2', '1'));
  });

  it('says a sentence without minutes as it is', () => {
    i18n.global.locale.value = 'es';
    expect(sayRefusal(i18n.global.t, { key: 'login.pinTooManyAttemptsNoWait' })).toBe(
      es.login.pinTooManyAttemptsNoWait,
    );
  });
});
