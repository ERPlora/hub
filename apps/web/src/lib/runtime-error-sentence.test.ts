// The rule this file protects (hub#1693): a screen never puts a runtime CODE in front of the
// business. `cloud_unreachable` is a word the engine and the shell agree on, not a sentence
// somebody running a shop can act on.
//
// It became visible with hub#1689: before it, the proxies answered with `reqwest`'s own Display
// (which carried the control plane's address), so what leaked was worse and no screen could
// translate it — it was library prose. Now the body IS a short stable code, so it CAN be
// translated, and every surface that paints the runtime's words has to.
import { describe, it, expect } from 'vitest';
import { localDoorSentence, runtimeErrorKey, runtimeErrorSentence } from './runtime-error-sentence';
import en from '../i18n/locales/en';
import es from '../i18n/locales/es';

/** The real catalogue, read the way `vue-i18n` reads it: `te` answers, `t` returns the sentence. */
function catalogue(messages: Record<string, unknown>) {
  const read = (key: string): unknown =>
    key.split('.').reduce<unknown>((node, part) => (node as Record<string, unknown>)?.[part], messages);
  return {
    t: (key: string) => (typeof read(key) === 'string' ? (read(key) as string) : key),
    te: (key: string) => typeof read(key) === 'string',
  };
}

const EN = catalogue(en as unknown as Record<string, unknown>);
const ES = catalogue(es as unknown as Record<string, unknown>);

/** Every stable code the back-office can receive from a cloud-facing door, with its own sentence. */
const TRANSLATED_CODES = [
  'cloud_unreachable',
  'cloud_rejected',
  'cloud_unreadable',
  'hub_not_enrolled',
  'install_cloud_unavailable',
] as const;

describe('runtimeErrorKey · a stable code becomes a catalogue key, prose does not', () => {
  it('maps the code the runtime sent as the whole body', () => {
    expect(runtimeErrorKey(new Error('cloud_unreachable'), EN)).toBe('runtimeErrors.cloud_unreachable');
  });

  it('prefers the error object own `code` over its technical message', () => {
    // What `InstallFailedError` looks like: the message is for the log (`request-install sales →
    // 502`), the code is the branchable fact, and `detail` is the engine's `cloud: cloud_unreachable`.
    const error = Object.assign(new Error('request-install sales → 502'), {
      code: 'install_cloud_unavailable',
      detail: 'cloud: cloud_unreachable',
    });
    expect(runtimeErrorKey(error, EN)).toBe('runtimeErrors.install_cloud_unavailable');
  });

  it('returns null for a real sentence, so the server keeps its own words', () => {
    // Integrity failures and «the SaaS answered 404» are prose worth reading: they say WHICH
    // thing broke, and no generic line replaces that.
    expect(runtimeErrorKey(new Error('el SaaS contestó 404 al resolver el blueprint'), EN)).toBeNull();
    expect(runtimeErrorKey(new Error('Object Storage devolvió 500 al bajar el blueprint'), EN)).toBeNull();
  });

  it('returns null for a code the catalogue does not know, so it is never painted', () => {
    // The point of going through `te`: a code invented next year has no sentence, and the caller
    // has to fall back rather than show it.
    expect(runtimeErrorKey(new Error('some_code_invented_next_year'), EN)).toBeNull();
  });
});

describe('runtimeErrorSentence · what the person actually reads', () => {
  it('says the sentence, never the code', () => {
    const said = runtimeErrorSentence(new Error('cloud_unreachable'), EN);
    expect(said).toBe(en.runtimeErrors.cloud_unreachable);
    expect(said).not.toContain('cloud_unreachable');
  });

  it('keeps the server sentence when the server sent one', () => {
    const prose = 'el SaaS contestó 404 al resolver el blueprint';
    expect(runtimeErrorSentence(new Error(prose), EN)).toBe(prose);
  });

  it('falls back to the generic line for an unknown code — never to the code itself', () => {
    expect(runtimeErrorSentence(new Error('some_code_invented_next_year'), EN)).toBe(
      en.runtimeErrors.default,
    );
  });

  it('uses the caller fallback when it has one and there is nothing to say', () => {
    expect(runtimeErrorSentence(new Error('   '), EN, 'Could not export')).toBe('Could not export');
  });

  it('never leaks a code even when it arrives as a non-Error value', () => {
    expect(runtimeErrorSentence('cloud_unreachable', EN)).toBe(en.runtimeErrors.cloud_unreachable);
    expect(runtimeErrorSentence(null, EN)).toBe(en.runtimeErrors.default);
  });
});

describe('runtimeErrors catalogue · a sentence in both languages (ADR-0055/0199)', () => {
  it.each([...TRANSLATED_CODES, 'default'] as const)('%s reads as a sentence in `en` and in `es`', (code) => {
    for (const [language, cat, messages] of [
      ['en', EN, en],
      ['es', ES, es],
    ] as const) {
      const key = `runtimeErrors.${code}`;
      expect(cat.te(key), `${key} has no sentence in \`${language}\``).toBe(true);
      const sentence = messages.runtimeErrors[code];
      // A sentence, not the code with a coat of paint: it must not contain the key it translates.
      expect(sentence).not.toContain(code);
      expect(sentence.length).toBeGreaterThan(20);
    }
  });

  it('says the same thing as the WhatsApp screen for the same fact', () => {
    // hub#1689 wrote this sentence for the connect screen. The same failure on the import screen
    // is the same failure: one fact, one sentence, or the business learns two different stories.
    expect(en.runtimeErrors.cloud_unreachable).toBe(en.whatsappConnect.errors.cloud_unreachable);
    expect(es.runtimeErrors.cloud_unreachable).toBe(es.whatsappConnect.errors.cloud_unreachable);
  });
});

// ── hub#1697 · las puertas LOCALES no son las de nube ────────────────────────────────────────
//
// hub#1693 arregló las pantallas que hablan con erplora.com, donde la prosa del cuerpo era la del
// SaaS y valía la pena conservarla. Las ocho pantallas de ajustes hablan con puertas LOCALES del
// runtime (`/api/devices`, `/api/device/mode`, `/api/hub/users`, `/api/keys`, `/api/hub/events/…`),
// y ahí la prosa NO es del servidor de nadie: es la línea que escribió quien programó el runtime,
// en inglés a propósito (regla del idioma del código). Un TPV en español leyendo «the device name
// is at most 40 characters» no está leyendo un mensaje: está leyendo el log.
//
// Por eso la regla cambia de forma: aquí un código se traduce y **lo demás es la frase de la
// pantalla**. La prosa del motor no se pinta nunca.
describe('localDoorSentence · una puerta local nunca enseña las palabras del motor', () => {
  const FALLBACK = 'The device list could not be loaded.';

  it('traduce el código en el namespace de la pantalla', () => {
    const error = Object.assign(new Error('the device name is at most 40 characters'), {
      code: 'device_name_too_long',
    });

    const said = localDoorSentence(error, EN, ['devices.errors'], FALLBACK);
    expect(said).toBe(en.devices.errors.device_name_too_long);
    expect(said).not.toContain('at most 40');
  });

  it('cae al namespace COMPARTIDO cuando la pantalla no conoce el código', () => {
    // `runtimeErrors` lo escribió hub#1693 y sirve a todas: un fallo de transporte es el mismo
    // hecho en las ocho pantallas, y escribirlo ocho veces es como se separan las frases.
    const error = Object.assign(new Error('boom'), { code: 'cloud_unreachable' });

    expect(localDoorSentence(error, EN, ['devices.errors', 'runtimeErrors'], FALLBACK)).toBe(
      en.runtimeErrors.cloud_unreachable,
    );
  });

  it('🔴 NUNCA enseña la prosa del motor: sin código traducible, la frase de la pantalla', () => {
    // Esta es la diferencia con `runtimeErrorSentence`, y el motivo de que exista esta función.
    const english = new Error('role `admin` is a base role of the hub and cannot be renamed');

    expect(localDoorSentence(english, EN, ['roles.errors', 'runtimeErrors'], FALLBACK)).toBe(FALLBACK);
    expect(localDoorSentence(english, EN, ['roles.errors'], FALLBACK)).not.toContain('base role');
  });

  it('tampoco enseña el CÓDIGO cuando nadie le escribió frase', () => {
    const error = Object.assign(new Error('nope'), { code: 'invented_next_year' });

    const said = localDoorSentence(error, EN, ['devices.errors', 'runtimeErrors'], FALLBACK);
    expect(said).toBe(FALLBACK);
    expect(said).not.toContain('invented_next_year');
  });

  it('el orden de los namespaces manda: la pantalla gana al compartido', () => {
    // `not_found` significa cosas distintas en cada pantalla («esa clave ya no está» / «esa
    // dead-letter ya no está»), así que la frase propia tiene que poder ganarle a la genérica.
    const error = Object.assign(new Error('gone'), { code: 'not_found' });

    expect(localDoorSentence(error, EN, ['apiKeys.errors', 'runtimeErrors'], FALLBACK)).toBe(
      en.apiKeys.errors.not_found,
    );
    expect(localDoorSentence(error, EN, ['system.errors', 'runtimeErrors'], FALLBACK)).toBe(
      en.system.errors.not_found,
    );
  });

  it('un código con punto es un código (`flow.release_revoked`)', () => {
    const error = Object.assign(new Error('cannot be replayed'), { code: 'flow.release_revoked' });

    // Un punto en el código es ANIDAMIENTO para `vue-i18n`, así que la clave plana
    // `'flow.release_revoked'` sería inalcanzable desde `t()`: el catálogo la anida.
    expect(localDoorSentence(error, EN, ['system.errors'], FALLBACK)).toBe(
      en.system.errors.flow.release_revoked,
    );
  });

  it('sin error ninguno, la frase de la pantalla', () => {
    expect(localDoorSentence(null, EN, ['devices.errors', 'runtimeErrors'], FALLBACK)).toBe(FALLBACK);
  });
});

describe('catálogo de las puertas locales · cadena `en` + `es` (ADR-0055/0199)', () => {
  const NEW_SENTENCES: ReadonlyArray<readonly [string, readonly string[]]> = [
    ['devices.errors', ['device_name_too_long', 'device_not_found']],
    ['apiKeys.errors', ['not_found', 'rate_limited']],
    ['system.errors', ['not_found', 'invalid_payload', 'flow.release_revoked', 'module.capability_denied']],
    ['employeeForm.errors', ['last_admin', 'self_deactivation', 'self_badge_enrollment', 'not_found']],
  ];

  it.each(NEW_SENTENCES)('%s tiene frase en los DOS idiomas, sin huérfanas', (ns, codes) => {
    for (const [language, cat] of [
      ['en', EN],
      ['es', ES],
    ] as const) {
      for (const code of codes) {
        const key = `${ns}.${code}`;
        expect(cat.te(key), `${key} no tiene frase en \`${language}\``).toBe(true);
        const sentence = cat.t(key);
        // Una frase, no el código con una capa de pintura.
        expect(sentence).not.toContain(code);
        expect(sentence.length).toBeGreaterThan(20);
      }
    }
  });
});
