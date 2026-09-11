// **A refused API-key gesture reaches the screen with its reason** (hub#1700).
//
// hub#1697 wrote the sentences this panel reads (`apiKeys.errors.*`) and wired `ApiKeysPanel` to
// `localDoorSentence`, and none of it could ever fire: `/api/keys*` answered `{"ok":false,
// "error":"<flat string>"}` and this client read `error.message` on a STRING — `undefined`. So
// every refusal, whatever it was, came out as the panel's own «check your connection» line.
//
// The two halves are tested together on purpose. Half a fix here is invisible: a door that sends a
// code to a client that drops it looks exactly like the bug, and so does a client that reads a code
// no door sends. The bodies below are the ones `api_key_refusals_carry_a_code_hub1700.rs` pins on
// the REAL door — that file is what keeps this one honest.
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ApiKeysError, createApiKey, listApiKeys, revokeApiKey, rotateApiKey } from './api-keys';
import { localDoorSentence } from './runtime-error-sentence';
import en from '../i18n/locales/en';
import es from '../i18n/locales/es';

/** The namespaces `ApiKeysPanel.vue` searches, in its order: the screen's own line wins. */
const API_KEY_ERRORS = ['apiKeys.errors', 'runtimeErrors'] as const;

/** The real catalogue, read the way `vue-i18n` reads it. */
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

/** The door refuses with the envelope every admin door of this hub answers with. */
function doorRefuses(status: number, code: string, message: string): void {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      ok: false,
      status,
      json: () => Promise.resolve({ ok: false, error: { code, message } }),
    }),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('a refusal of the API keys door arrives with its code (hub#1700)', () => {
  it('revoking a key that is gone', async () => {
    doorRefuses(404, 'not_found', 'API key no encontrada');

    const error = await revokeApiKey('k1').then(
      () => null,
      (e: unknown) => e,
    );

    expect(error).toBeInstanceOf(ApiKeysError);
    expect((error as ApiKeysError).code).toBe('not_found');
  });

  it('rotating a key that is gone', async () => {
    doorRefuses(404, 'not_found', 'API key no encontrada');

    const error = await rotateApiKey('k1').then(
      () => null,
      (e: unknown) => e,
    );

    expect((error as ApiKeysError).code).toBe('not_found');
  });

  it('creating one with a session that lapsed', async () => {
    doorRefuses(401, 'unauthorized', 'falta sesión (cabecera X-Hub-Session)');

    const error = await createApiKey({ name: 'Gestoría', scope: [], rate_limit_per_minute: 60 }).then(
      () => null,
      (e: unknown) => e,
    );

    expect((error as ApiKeysError).code).toBe('unauthorized');
  });

  it('listing them as somebody whose role does not manage keys', async () => {
    doorRefuses(403, 'forbidden', 'se requiere rol owner/admin para gestionar el Hub');

    const error = await listApiKeys().then(
      () => null,
      (e: unknown) => e,
    );

    expect((error as ApiKeysError).code).toBe('forbidden');
  });

  it("the hub's own key, whose code is namespaced by the module that raised it", async () => {
    doorRefuses(409, 'api_key.system_key', 'this key belongs to the hub itself');

    const error = await revokeApiKey('sys').then(
      () => null,
      (e: unknown) => e,
    );

    expect((error as ApiKeysError).code).toBe('api_key.system_key');
  });

  it('keeps the door prose for the log, instead of the client-side status line', async () => {
    doorRefuses(404, 'not_found', 'API key no encontrada');

    const error = (await revokeApiKey('k1').catch((e: unknown) => e)) as ApiKeysError;

    // Not `keys.revoke → 404`: that line is what a person read until this fix, and it says nothing.
    expect(error.message).toBe('API key no encontrada');
  });

  it('a door that answers no code at all still throws, it does not resolve', async () => {
    // Fail-closed: a refused revocation must never look like one that happened.
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: false, status: 500, json: () => Promise.reject(new Error('no body')) }),
    );

    await expect(revokeApiKey('k1')).rejects.toBeInstanceOf(ApiKeysError);
  });

  it('a network that never answers is not swallowed either', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('Failed to fetch')));

    await expect(revokeApiKey('k1')).rejects.toBeInstanceOf(ApiKeysError);
  });
});

describe('and the panel turns that code into a sentence a person can act on', () => {
  const FALLBACK = 'Could not revoke this key. Check your connection and try again.';

  const READS: ReadonlyArray<readonly [string, string]> = [
    ['not_found', 'apiKeys.errors.not_found'],
    ['unauthorized', 'apiKeys.errors.unauthorized'],
    ['forbidden', 'apiKeys.errors.forbidden'],
    ['api_key.system_key', 'apiKeys.errors.api_key.system_key'],
  ];

  it.each(READS)('%s → its own sentence, in both languages', (code, key) => {
    const error = new ApiKeysError('the door prose, written for the log', code);

    for (const [language, cat] of [
      ['en', EN],
      ['es', ES],
    ] as const) {
      const said = localDoorSentence(error, cat, API_KEY_ERRORS, FALLBACK);
      expect(said, `${key} missing in \`${language}\``).toBe(cat.t(key));
      expect(said).not.toBe(FALLBACK);
      // Never the engine's own words, and never the code with a coat of paint (hub#1693).
      expect(said).not.toContain('the door prose');
      expect(said).not.toContain(code);
    }
  });

  it('a code this shell has never heard of falls back to the panel line, never to the code', () => {
    const error = new ApiKeysError('nope', 'invented_next_year');

    expect(localDoorSentence(error, EN, API_KEY_ERRORS, FALLBACK)).toBe(FALLBACK);
  });
});
