// The rule this file protects (hub#1693): a screen never puts a runtime CODE in front of the
// business. `cloud_unreachable` is a word the engine and the shell agree on, not a sentence
// somebody running a shop can act on.
//
// It became visible with hub#1689: before it, the proxies answered with `reqwest`'s own Display
// (which carried the control plane's address), so what leaked was worse and no screen could
// translate it — it was library prose. Now the body IS a short stable code, so it CAN be
// translated, and every surface that paints the runtime's words has to.
import { describe, it, expect } from 'vitest';
import { runtimeErrorKey, runtimeErrorSentence } from './runtime-error-sentence';
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
  it.each([...TRANSLATED_CODES, 'default'])('%s reads as a sentence in `en` and in `es`', (code) => {
    for (const [language, cat, messages] of [
      ['en', EN, en],
      ['es', ES, es],
    ] as const) {
      const key = `runtimeErrors.${code}`;
      expect(cat.te(key), `${key} has no sentence in \`${language}\``).toBe(true);
      const sentence = (messages as Record<string, Record<string, string>>).runtimeErrors[code];
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
