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

    expect(toast).toBe(es.runtimeErrors.core_version_too_old.replace('{required}', REQUIRED).replace('{core}', CORE));
    expect(toast).toContain(REQUIRED);
    expect(toast).toContain(CORE);
    expect(toast).not.toContain('runtime:');
    expect(toast).not.toContain('the module');
  });

  it('says it in English too, with both versions', async () => {
    const err = await failedInstall();
    const toast = moduleFailureMessage(err, 'FALLBACK', translator('en'));

    expect(toast).toBe(en.runtimeErrors.core_version_too_old.replace('{required}', REQUIRED).replace('{core}', CORE));
  });
});
