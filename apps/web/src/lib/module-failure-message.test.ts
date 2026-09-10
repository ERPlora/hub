import { describe, expect, it } from 'vitest';

import { moduleFailureMessage } from './module-failure-message';
import { InstallBlockedError, InstallFailedError, ModuleActionError } from './runtime';
import en from '../i18n/locales/en';

// The REAL catalogue, read the way `vue-i18n` reads it. Not a stub: hub#1693 turns on whether a
// code has a sentence, and a fake catalogue would answer «yes» to every code ever invented.
const read = (key: string): unknown =>
  key.split('.').reduce<unknown>((node, part) => (node as Record<string, unknown>)?.[part], en as unknown as Record<string, unknown>);
const I18N = {
  t: (key: string) => (typeof read(key) === 'string' ? (read(key) as string) : key),
  te: (key: string) => typeof read(key) === 'string',
};

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

    expect(moduleFailureMessage(error, FALLBACK, I18N)).toBe('The signature of the package is not valid.');
  });

  it('falls back when the runtime could not be read — our own line beats a stack trace', () => {
    // Body unreadable (a 502 from a proxy, a truncated answer): `message` carries the technical
    // string for the logs and `detail` is null, so nothing server-side is shown.
    const error = new InstallFailedError('request-install sales → 502', 'install_failed', null);

    expect(moduleFailureMessage(error, FALLBACK, I18N)).toBe(FALLBACK);
  });

  it('falls back for a failure that never reached the runtime at all', () => {
    // No network. There is no server sentence because there was no server.
    expect(moduleFailureMessage(new TypeError('Failed to fetch'), FALLBACK, I18N)).toBe(FALLBACK);
    expect(moduleFailureMessage(null, FALLBACK, I18N)).toBe(FALLBACK);
    expect(moduleFailureMessage('boom', FALLBACK, I18N)).toBe(FALLBACK);
  });

  it('ignores an empty sentence instead of showing a blank toast', () => {
    expect(moduleFailureMessage(new InstallFailedError('x', 'install_failed', '   '), FALLBACK, I18N)).toBe(FALLBACK);
  });

  it('carries the reason of an action the runtime REFUSED', () => {
    // hub#314: deactivating or removing a module that still owes records to the AEAT is refused
    // with a domain code and a sentence that says how many are left. Same rule, same helper — this
    // used to live in a private `reasonOf` inside AppsPage, which is why install never got it.
    const error = new ModuleActionError('VeriFactu still has 3 records to submit.', 'verifactu.unsent_records');

    expect(moduleFailureMessage(error, FALLBACK, I18N)).toBe('VeriFactu still has 3 records to submit.');
  });

  it('does not invent a reason for a transport failure of a module action', () => {
    // `ModuleActionError` with no code = a 500 or a broken connection, not a business rule.
    expect(moduleFailureMessage(new ModuleActionError('modules/x/uninstall → 500'), FALLBACK, I18N)).toBe(FALLBACK);
  });

  it('lets the caller keep its own treatment for «blocked»', () => {
    // `InstallBlockedError` is NOT a breakdown (ADR-0060): the plan needs paid modules nobody has
    // subscribed to, nothing was installed and nothing was charged. The screen names what is
    // missing and stays sticky, so it never comes through here — but if it ever does, the runtime's
    // sentence is still the better one.
    const error = new InstallBlockedError('Needs: reservations.', ['reservations'], [], 'Needs: reservations.');

    expect(moduleFailureMessage(error, FALLBACK, I18N)).toBe('Needs: reservations.');
  });
});

// hub#1693 — the marketplace toast is the fourth surface of the same defect, and the one the
// reviewer of hub#1695 measured: with erplora.com down, installing answers
// `{"code":"install_cloud_unavailable","error":"cloud: cloud_unreachable"}` and the toast said
// «cloud: cloud_unreachable». The code is the thing to translate; the sentence-shaped `detail` is
// not a sentence.
describe('moduleFailureMessage · un código estable gana a la prosa técnica del motor', () => {
  it('traduce el código del install cuando la nube no contesta', () => {
    const error = new InstallFailedError(
      'request-install sales → 502',
      'install_cloud_unavailable',
      'cloud: cloud_unreachable',
    );

    const said = moduleFailureMessage(error, FALLBACK, I18N);
    expect(said).toBe(en.runtimeErrors.install_cloud_unavailable);
    expect(said).not.toContain('cloud_unreachable');
    expect(said).not.toContain('cloud:');
  });

  it('traduce igual el código cuando llega como cuerpo desnudo', () => {
    // Some proxy doors answer `{"ok":false,"error":"cloud_unreachable"}`, so `detail` IS the code.
    const error = new InstallFailedError('update sales → 502', 'install_cloud_unavailable', 'cloud_unreachable');

    expect(moduleFailureMessage(error, FALLBACK, I18N)).toBe(en.runtimeErrors.install_cloud_unavailable);
  });

  it('no toca los códigos que ya tenían su propio trato', () => {
    // `install_blocked` is a purchase decision with its own screen (ADR-0060): it must NOT be
    // swallowed by the generic catalogue, which is why it is not in it.
    const blocked = new InstallBlockedError('Needs: reservations.', ['reservations'], [], 'Needs: reservations.');
    expect(moduleFailureMessage(blocked, FALLBACK, I18N)).toBe('Needs: reservations.');
  });
});

// hub#1720 — **the three causes a person has to be able to tell apart.**
//
// Until hub#1720 the install pipeline reported «erplora.com refused this hub's key», «that app is
// not in your catalogue» and «erplora.com did not answer» as the SAME code, inside a `502` whose
// body the edge replaced with its own page. Two halves were fixed in the runtime: the status now
// crosses the proxy, and the codes are three. This is the third half, and it is the only one the
// person actually reads: a code with no sentence here is never painted — `moduleFailureMessage`
// falls through to the engine's own prose, which is written in Spanish for the log (the
// code-language rule), so an English till would read half a sentence in a language it did not pick.
describe('moduleFailureMessage · cada causa de instalación tiene SU frase, no la del motor', () => {
  const ENGINE_PROSE = 'el Cloud no aceptó la credencial de este hub';

  const CAUSES = [
    'install_cloud_unavailable',
    'install_cloud_denied',
    'install_not_in_catalog',
    'install_cloud_rejected',
  ] as const;

  it.each(CAUSES)('%s reads as a sentence of the catalogue, never as the engine prose', (code) => {
    const error = new InstallFailedError(`request-install sales → 424`, code, ENGINE_PROSE);

    const said = moduleFailureMessage(error, FALLBACK, I18N);

    expect(said).toBe((en.runtimeErrors as Record<string, string>)[code]);
    expect(said).not.toBe(ENGINE_PROSE);
    expect(said).not.toBe(FALLBACK);
  });

  it('and the three new causes do NOT share a sentence: telling them apart is the point', () => {
    const sentences = CAUSES.map((code) => (en.runtimeErrors as Record<string, string>)[code]);

    expect(new Set(sentences).size).toBe(CAUSES.length);
  });
});
