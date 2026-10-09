import { describe, expect, it } from 'vitest';

import { moduleFailureMessage } from './module-failure-message';
import { ModuleActionError } from './runtime';
import en from '../i18n/locales/en';
import es from '../i18n/locales/es';

const FALLBACK = 'No se pudo cambiar el estado de la app.';

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
