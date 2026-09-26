// hub#1620 — installing an app that needs a newer hub.
//
// The hub does the right thing (it refuses a module it cannot run whole), but the owner used to read
// the engine's log line in the toast: «runtime: the module `whatsapp_inbox` needs a newer version of
// your terminal: it requires ERPlora 1.1.16 and this hub runs 1.1.15 — update the hub…» — in
// English, with a technical prefix, on a Spanish till. The runtime now answers its own stable code
// (`core_version_too_old`) with both versions as data, and the shell says it in the owner's language.
//
// Driven from the body the runtime really sends (`install_error_response`, crates/server) through the
// real `requestInstall` and the real catalogues, read by a real `vue-i18n` so the two numbers are
// really interpolated. The versions are not literals of one release on purpose: the floor moves.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { createI18n } from 'vue-i18n';

import { requestInstall, InstallFailedError } from './runtime';
import { moduleFailureMessage } from './module-failure-message';
import { runtimeErrorSentence } from './runtime-error-sentence';
import en from '../i18n/locales/en';
import es from '../i18n/locales/es';

const REQUIRED = '7.4.2';
const CORE = '7.3.9';

function needsNewerHubResponse() {
  return {
    ok: false,
    status: 422,
    json: async () => ({
      ok: false,
      error: `the module \`whatsapp_inbox\` requires ERPlora ${REQUIRED} and this hub runs ${CORE}`,
      code: 'core_version_too_old',
      module_id: 'whatsapp_inbox',
      required: REQUIRED,
      core: CORE,
    }),
  };
}

function translator(locale: 'en' | 'es') {
  const i18n = createI18n({
    legacy: false,
    locale,
    missingWarn: false,
    fallbackWarn: false,
    messages: { en, es } as never,
  });
  const g = i18n.global as unknown as {
    t: (key: string, params?: Record<string, unknown>) => string;
    te: (key: string) => boolean;
  };
  return { t: g.t, te: g.te };
}

async function failedInstall(): Promise<unknown> {
  vi.stubGlobal('fetch', vi.fn(async () => needsNewerHubResponse()));
  return requestInstall('whatsapp_inbox', 'latest').then(
    () => null,
    (e) => e,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('installing an app that needs a newer hub (hub#1620)', () => {
  it('keeps the stable code and both versions', async () => {
    const err = await failedInstall();

    expect(err).toBeInstanceOf(InstallFailedError);
    expect((err as InstallFailedError).code).toBe('core_version_too_old');
    expect((err as InstallFailedError).params).toEqual({ required: REQUIRED, core: CORE });
  });

  it('tells a Spanish owner in Spanish, naming both versions, without the engine sentence', async () => {
    const err = await failedInstall();
    const toast = moduleFailureMessage(err, 'FALLBACK', translator('es'));

    expect(toast).toBe(es.runtimeErrorFacts.core_version_too_old.replace('{required}', REQUIRED).replace('{core}', CORE));
    expect(toast).toContain(REQUIRED);
    expect(toast).toContain(CORE);
    expect(toast).not.toContain('runtime:');
    expect(toast).not.toContain('the module');
  });

  it('says it in English too, with both versions', async () => {
    const err = await failedInstall();
    const toast = moduleFailureMessage(err, 'FALLBACK', translator('en'));

    expect(toast).toBe(en.runtimeErrorFacts.core_version_too_old.replace('{required}', REQUIRED).replace('{core}', CORE));
  });

  // Other doors answer the same stable code WITHOUT the versions (the development install by folder
  // goes through the runtime's generic error envelope). The shared line has to read whole there too:
  // «ERPlora ). El tuyo tiene la :» is worse than the engine sentence it replaced.
  it('reads whole when the code arrives without the versions', async () => {
    const bare = { code: 'core_version_too_old', detail: 'the module `x` requires ERPlora 9.0.0 and this hub runs 1.0.0' };
    for (const [locale, catalogue] of [['es', es], ['en', en]] as const) {
      const byToast = moduleFailureMessage(bare, 'FALLBACK', translator(locale));
      const byScreen = runtimeErrorSentence(bare, translator(locale));

      expect(byToast).toBe(catalogue.runtimeErrors.core_version_too_old);
      expect(byScreen).toBe(catalogue.runtimeErrors.core_version_too_old);
    }
  });
});

// The shared `runtimeErrors` catalogue is read by every screen with the bare code, never with data,
// so no sentence in it may need any: one that does paints its blanks to whoever gets the code first.
describe('the shared runtime error catalogue', () => {
  it('has no sentence that needs data to read whole', () => {
    for (const [locale, catalogue] of [['en', en], ['es', es]] as const) {
      const withHoles = Object.entries(catalogue.runtimeErrors as Record<string, unknown>)
        .filter(([, sentence]) => typeof sentence === 'string' && /\{[a-zA-Z_]+\}/.test(sentence))
        .map(([code]) => `${locale}.${code}`);
      expect(withHoles).toEqual([]);
    }
  });
});
