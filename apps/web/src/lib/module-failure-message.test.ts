import { describe, expect, it } from 'vitest';

import { moduleFailureMessage } from './module-failure-message';
import { InstallBlockedError, InstallFailedError, ModuleActionError } from './runtime';
import en from '../i18n/locales/en';
import es from '../i18n/locales/es';

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

  it('carries the reason of an action the runtime REFUSED with a code the catalogue does not know', () => {
    // hub#314: deactivating or removing a module that still owes work to an authority is refused
    // with a domain code and a sentence. Same rule, same helper — this used to live in a private
    // `reasonOf` inside AppsPage, which is why install never got it. The engine's sentence is the
    // last resort for a code this shell has no line for yet (an engine published after it); the
    // codes it does know are translated (hub#2579, below).
    const error = new ModuleActionError('Acme still has 3 filings to submit.', 'acme.unsent_records');

    expect(moduleFailureMessage(error, FALLBACK, I18N)).toBe('Acme still has 3 filings to submit.');
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
    // hub#2251 — the marketplace took the call and went silent.
    'install_cloud_timeout',
  ] as const;

  it.each(CAUSES)('%s reads as a sentence of the catalogue, never as the engine prose', (code) => {
    const error = new InstallFailedError(`request-install sales → 424`, code, ENGINE_PROSE);

    const said = moduleFailureMessage(error, FALLBACK, I18N);

    expect(said).toBe((en.runtimeErrors as Record<string, unknown>)[code]);
    expect(said).not.toBe(ENGINE_PROSE);
    expect(said).not.toBe(FALLBACK);
  });

  it('and the three new causes do NOT share a sentence: telling them apart is the point', () => {
    const sentences = CAUSES.map((code) => (en.runtimeErrors as Record<string, unknown>)[code]);

    expect(new Set(sentences).size).toBe(CAUSES.length);
  });
});

// hub#1763 — the gravest answer of `POST /api/modules/:id/update`: the new version failed AND the
// previous one could not be restored, so the module is GONE from this hub. The runtime says so with
// `module.update_lost`. What the person must never read there is the fallback of AppsPage — «it
// keeps running the version it had» — which is a lie about a module that has just disappeared.
describe('moduleFailureMessage — an update that lost the module', () => {
  const KEEPS_RUNNING = 'Could not update Sales. It keeps running the version it had.';
  const lost = new InstallFailedError('`sales`: rollback failed', 'module.update_lost', '`sales`: rollback failed');

  it('says the module is gone, never that it keeps running', () => {
    const sentence = moduleFailureMessage(lost, KEEPS_RUNNING, I18N);
    expect(sentence).toBe(en.runtimeErrors.module.update_lost);
    expect(sentence).not.toContain('keeps running');
  });

  it('has its Spanish sentence too (en + es, ADR-0055)', () => {
    expect(typeof es.runtimeErrors.module.update_lost).toBe('string');
    expect(es.runtimeErrors.module.update_lost).not.toBe(en.runtimeErrors.module.update_lost);
  });
});

// hub#2579 — the two FISCAL refusals of switching off or uninstalling an app reached a Spanish
// screen in English. The runtime refuses with a stable code (ADR-0055) and an English sentence for
// the log: `verifactu.unsent_records` (the engine still owes records to the AEAT, ADR-0202 R2) and
// `fiscal.no_provider_left` (the hub would be left with no app filing its regime, ADR-0273 D5).
// Neither code had a line in `runtimeErrors`, so `moduleFailureMessage` fell through to the log
// sentence and the owner read «3 VeriFactu record(s) have not reached the AEAT yet…».
describe('moduleFailureMessage — the fiscal refusals read in the screen language (hub#2579)', () => {
  const catalogue = (root: unknown) => {
    const read = (key: string): unknown =>
      key.split('.').reduce<unknown>((node, part) => (node as Record<string, unknown>)?.[part], root);
    return {
      t: (key: string) => (typeof read(key) === 'string' ? (read(key) as string) : key),
      te: (key: string) => typeof read(key) === 'string',
    };
  };
  const ES = catalogue(es);
  const EN = catalogue(en);

  // The sentences the runtime writes today, word for word: what the screen must NOT paint.
  const REFUSALS = [
    {
      code: 'verifactu.unsent_records',
      engine: '3 VeriFactu record(s) have not reached the AEAT yet: send them before disabling or removing the module',
    },
    {
      code: 'fiscal.no_provider_left',
      engine:
        'this hub files under `verifactu` and this would leave it with no module fulfilling that regime: install another provider first, or close the fiscal period',
    },
  ] as const;

  for (const { code, engine } of REFUSALS) {
    for (const fallback of ['No se pudo cambiar el estado de VeriFactu.', 'No se pudo desinstalar VeriFactu.']) {
      it(`${code} on a Spanish screen reads the Spanish line, not the engine's (${fallback})`, () => {
        const said = moduleFailureMessage(new ModuleActionError(engine, code), fallback, ES);

        expect(said).toBe(ES.t(`runtimeErrors.${code}`));
        expect(ES.te(`runtimeErrors.${code}`), `es.runtimeErrors.${code} is missing`).toBe(true);
        expect(said).not.toBe(engine);
        expect(said).not.toBe(fallback);
      });
    }

    it(`${code} has its English source line too, and the two differ`, () => {
      expect(EN.te(`runtimeErrors.${code}`), `en.runtimeErrors.${code} is missing`).toBe(true);
      const said = moduleFailureMessage(new ModuleActionError(engine, code), FALLBACK, EN);
      expect(said).toBe(EN.t(`runtimeErrors.${code}`));
      expect(said).not.toBe(engine);
      expect(EN.t(`runtimeErrors.${code}`)).not.toBe(ES.t(`runtimeErrors.${code}`));
    });
  }

  it('the two refusals do not share a sentence: their way out is different', () => {
    expect(ES.t('runtimeErrors.verifactu.unsent_records')).not.toBe(ES.t('runtimeErrors.fiscal.no_provider_left'));
  });
});
