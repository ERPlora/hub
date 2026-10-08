// hub#2556 — what «Update» tells the person, from the body the runtime REALLY sends.
//
// `POST /api/modules/:id/update` answers inside an envelope — `{ok, data: {module_id, from, version,
// updated}}` — and, when the new version could not go in and the app stayed on the one it had, a
// 200 with `warning: {code: "module.update_failed_kept_previous", cause, message}` (module_api.rs).
// The shell read the fields at the top level, where there are none: `updated` was always missing,
// so a real update and an update that ran out of time both said «already on the latest version».
// The trickling download of hub#2556 now ends with `cause: "install_cloud_timeout"`, and the
// person has to read that it did NOT update, why, and that trying again is the way out.
//
// The bodies below are the ones the runtime builds (crates/server/src/module_api.rs, pinned by
// crates/server/tests/install_slow_download_deadline_hub2556.rs), read by a real `vue-i18n`.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { createI18n } from 'vue-i18n';

import { updateModule } from './runtime';
import { updateFailureMessage } from './module-failure-message';
import en from '../i18n/locales/en';
import es from '../i18n/locales/es';

function answer(body: Record<string, unknown>, status = 200) {
  return { ok: status < 400, status, json: async () => body };
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

const fill = (s: string, params: Record<string, string>) =>
  Object.entries(params).reduce((acc, [k, v]) => acc.split(`{${k}}`).join(v), s);

async function update(body: Record<string, unknown>, status = 200): Promise<unknown> {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => answer(body, status)),
  );
  return updateModule('notes', '').then(
    (result) => ({ result }),
    (error) => ({ error }),
  );
}

const keptPrevious = (cause: string | null) => ({
  ok: true,
  data: { module_id: 'notes', version: '1.0.0', updated: false },
  warning: {
    code: 'module.update_failed_kept_previous',
    cause,
    message: 'cloud: the marketplace did not answer in time',
  },
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('«Update» reads what the runtime answers (hub#2556)', () => {
  it('🔴 a real update says it updated, from which version to which', async () => {
    const outcome = await update({
      ok: true,
      data: { module_id: 'notes', from: '1.0.0', version: '2.0.0', updated: true },
    });
    expect(outcome).toEqual({
      result: { ok: true, module_id: 'notes', from: '1.0.0', to: '2.0.0', updated: true },
    });
  });

  it('an app already on its version says so, and nothing more', async () => {
    const outcome = (await update({
      ok: true,
      data: { module_id: 'notes', version: '1.0.0', updated: false },
    })) as { result: { updated: boolean; to: string } };
    expect(outcome.result.updated).toBe(false);
    expect(outcome.result.to).toBe('1.0.0');
  });

  it('🔴 an update that stayed on the previous version is a FAILURE, not «already up to date»', async () => {
    const outcome = (await update(keptPrevious('install_cloud_timeout'))) as { error?: unknown };
    expect(outcome.error, 'it must reject').toBeTruthy();
    expect(outcome.error).toMatchObject({
      code: 'module.update_failed_kept_previous',
      reason: 'install_cloud_timeout',
      version: '1.0.0',
    });
  });

  it('a failure the runtime answers with an error status still rejects with its code', async () => {
    const outcome = (await update(
      { ok: false, error: 'version not offered', code: 'update_version_not_offered' },
      409,
    )) as { error?: unknown };
    expect(outcome.error).toMatchObject({ code: 'update_version_not_offered' });
  });
});

describe('the sentence for an update that did not go in (hub#2556)', () => {
  for (const locale of ['en', 'es'] as const) {
    const catalogue = locale === 'en' ? en : es;

    it(`🔴 a download that ran out of time says so and to try again (${locale})`, async () => {
      const { error } = (await update(keptPrevious('install_cloud_timeout'))) as { error: unknown };
      const sentence = updateFailureMessage(error, 'Notes', translator(locale));
      expect(sentence).toBe(fill(catalogue.apps.updateTimedOut, { name: 'Notes' }));
      expect(sentence).not.toContain('{');
    });

    it(`any other reason keeps the honest generic line: it still runs the version it had (${locale})`, async () => {
      const { error } = (await update(keptPrevious('install_bad_signature'))) as { error: unknown };
      expect(updateFailureMessage(error, 'Notes', translator(locale))).toBe(
        fill(catalogue.apps.updateError, { name: 'Notes' }),
      );
    });

    it(`an older runtime that sends no cause gets the generic line too (${locale})`, async () => {
      const { error } = (await update(keptPrevious(null))) as { error: unknown };
      expect(updateFailureMessage(error, 'Notes', translator(locale))).toBe(
        fill(catalogue.apps.updateError, { name: 'Notes' }),
      );
    });
  }

  it('a failure with an error status keeps the runtime sentence for its code (hub#1693)', async () => {
    const { error } = (await update(
      { ok: false, error: 'cloud: cloud_unreachable', code: 'install_cloud_unavailable' },
      502,
    )) as { error: unknown };
    const { t, te } = translator('es');
    expect(updateFailureMessage(error, 'Notes', { t, te })).toBe(t('runtimeErrors.install_cloud_unavailable'));
  });

  it('the technical English of the warning never reaches the screen', async () => {
    const { error } = (await update(keptPrevious('install_cloud_timeout'))) as { error: unknown };
    expect(updateFailureMessage(error, 'Notes', translator('es'))).not.toContain('cloud:');
  });
});
