import { describe, expect, it } from 'vitest';

import { moduleFailureMessage } from './module-failure-message';
import { InstallBlockedError, InstallFailedError, ModuleActionError } from './runtime';

// When installing a module fails, the person is told WHY (hub#673).
//
// Every failure looked the same: «No se pudo iniciar la instalación de {name}» — a missing machine
// token, a bad signature, a version that does not exist, a dependency that could not be resolved, a
// SHA-256 that did not match, a migration that blew up. The runtime says exactly which of those it
// was, in the body, with a stable code. The frontend threw the sentence away and reached for its own.
//
// That is what made the fleet-wide install breakage of 2026-08-09 (saas#1352) invisible: every hub
// in the field said «no se puede instalar» and nobody could tell the six causes apart.
//
// The rule this encodes, and the whole reason it is not just «show `e.message`»: use the sentence
// the SERVER said, and ONLY that. When the body could not be read there is no server sentence —
// only a technical string we made up for the logs («request-install sales → 500»), and putting THAT
// in front of a shop owner is worse than the generic line. `detail` is how the two are told apart:
// it exists when the runtime spoke, and is `null` when it did not.

const FALLBACK = 'Could not start installing Sales.';

describe('moduleFailureMessage', () => {
  it('says what the runtime said', () => {
    const error = new InstallFailedError('The signature of the package is not valid.', 'bad_signature', 'The signature of the package is not valid.');

    expect(moduleFailureMessage(error, FALLBACK)).toBe('The signature of the package is not valid.');
  });

  it('falls back when the runtime could not be read — our own line beats a stack trace', () => {
    // Body unreadable (a 502 from a proxy, a truncated answer): `message` carries the technical
    // string for the logs and `detail` is null, so nothing server-side is shown.
    const error = new InstallFailedError('request-install sales → 502', 'install_failed', null);

    expect(moduleFailureMessage(error, FALLBACK)).toBe(FALLBACK);
  });

  it('falls back for a failure that never reached the runtime at all', () => {
    // No network. There is no server sentence because there was no server.
    expect(moduleFailureMessage(new TypeError('Failed to fetch'), FALLBACK)).toBe(FALLBACK);
    expect(moduleFailureMessage(null, FALLBACK)).toBe(FALLBACK);
    expect(moduleFailureMessage('boom', FALLBACK)).toBe(FALLBACK);
  });

  it('ignores an empty sentence instead of showing a blank toast', () => {
    expect(moduleFailureMessage(new InstallFailedError('x', 'install_failed', '   '), FALLBACK)).toBe(FALLBACK);
  });

  it('carries the reason of an action the runtime REFUSED', () => {
    // hub#314: deactivating or removing a module that still owes records to the AEAT is refused
    // with a domain code and a sentence that says how many are left. Same rule, same helper — this
    // used to live in a private `reasonOf` inside AppsPage, which is why install never got it.
    const error = new ModuleActionError('VeriFactu still has 3 records to submit.', 'verifactu.unsent_records');

    expect(moduleFailureMessage(error, FALLBACK)).toBe('VeriFactu still has 3 records to submit.');
  });

  it('does not invent a reason for a transport failure of a module action', () => {
    // `ModuleActionError` with no code = a 500 or a broken connection, not a business rule.
    expect(moduleFailureMessage(new ModuleActionError('modules/x/uninstall → 500'), FALLBACK)).toBe(FALLBACK);
  });

  it('lets the caller keep its own treatment for «blocked»', () => {
    // `InstallBlockedError` is NOT a breakdown (ADR-0060): the plan needs paid modules nobody has
    // subscribed to, nothing was installed and nothing was charged. The screen names what is
    // missing and stays sticky, so it never comes through here — but if it ever does, the runtime's
    // sentence is still the better one.
    const error = new InstallBlockedError('Needs: reservations.', ['reservations'], [], 'Needs: reservations.');

    expect(moduleFailureMessage(error, FALLBACK)).toBe('Needs: reservations.');
  });
});
