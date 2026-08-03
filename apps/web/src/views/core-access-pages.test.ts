import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';

const source = (name: string): string =>
  readFileSync(new URL(`./${name}`, import.meta.url), 'utf8');

describe('core access and account pages', () => {
  it('does not treat an unknown entitlement as an activated hub', () => {
    const activation = source('ActivationPage.vue');
    expect(activation).toContain("entitlementStatus.value === 'unlocked'");
    expect(activation).not.toContain('!needsActivation.value');
  });

  it('lets API documentation recover from a transient load error', () => {
    const docs = source('ApiDocsPage.vue');
    expect(docs).toContain('@click="loadSpec"');
    expect(docs).toContain('swaggerEl.value?.replaceChildren()');
  });

  it('localizes billing dates and reports external-action failures', () => {
    const billing = source('BillingPage.vue');
    expect(billing).toContain("locale.value === 'en' ? 'en-GB' : 'es-ES'");
    expect(billing).toContain("toastError(t('billing.downloadError'))");
    expect(billing).toContain("t('billing.openBillingPortal')");
  });

  it('does not revive stale PIN users or create a fake trusted PIN in demo mode', () => {
    const login = source('LoginPage.vue');
    expect(login).toContain('hubContextReady');
    expect(login).toContain('machineRegistrationRequired');
    expect(login).toContain("invokeTauri<string>('enroll_device'");
    expect(login).toContain('refreshed.machine_registered');
    expect(login).not.toContain("invokeTauri('enroll_device', {");
    expect(login).not.toContain('enroll falla, el JWT');
    expect(login).toContain('saveTrustedUsers([])');
    expect(login).toContain("role: 'owner'");
    expect(login).toContain("permissions: sess.permissions");
    expect(login).toContain("permissions: ['*']");
    expect(login).toContain("throw new Error('missing runtime session')");
  });

  it('offers a Google login that returns to the Hub (not the SaaS) #945', () => {
    // The Hub PWA must build the SaaS Google-login URL with a `next` that
    // points at the hub-bridge, so after Google auth the user is bounced back
    // to THIS hub's /auth/google/callback (not left logged into the SaaS).
    const login = source('LoginPage.vue');
    // A "Continue with Google" entry exists.
    expect(login).toContain('login.signInWithGoogle');
    // The hub-bridge `next` is built from the hub's own origin + callback path,
    // and double-encoded into the Google login URL.
    expect(login).toContain('auth/hub-bridge');
    expect(login).toContain('/auth/google/callback');
    expect(login).toContain('encodeURIComponent');
  });

  it('shows a recoverable error instead of disguising a failed cloud catalog as empty', () => {
    const apps = source('AppsPage.vue');
    expect(apps).toContain('catalogError.value = true');
    expect(apps).not.toContain('MODULES_DEMO');
    expect(apps).toContain("t('apps.catalogLoadError')");
    expect(apps).toContain('@click="loadCatalog"');
  });

  it('does not claim that updates were checked when no updater is configured', () => {
    const system = source('SystemPage.vue');
    expect(system).toContain("t('system.updatesManaged')");
    expect(system).not.toContain("t('system.upToDate')");
    expect(system).toContain('dataTableLabels(locale.value)');
  });

  it('hides the database-size card when no local DB size exists (cloud / N/A)', () => {
    // #942: the database-size card only applies in local (SQLite). In cloud
    // (Aurora) there is no local DB size, so the card must be hidden instead
    // of rendering a placeholder "N/A" value.
    const system = source('SystemPage.vue');
    expect(system).toContain('hasDbSize');
    expect(system).toMatch(/v-if="hasDbSize"[\s\S]*?dbValue/);
  });

  it('redeems the Google exchange code and bootstraps the session #945', () => {
    // The SaaS redirects back to /auth/google/callback?code=…; a dedicated view
    // must redeem that code (sessionExchange) and run the same bootstrap the
    // email login does (setTokens + runtimeCloudSession + setHubSession + setUser
    // + redirect), instead of landing on the catch-all → /login.
    const callback = source('GoogleCallbackPage.vue');
    expect(callback).toContain('sessionExchange');
    expect(callback).toContain('setTokens');
    expect(callback).toContain('runtimeCloudSession');
    expect(callback).toContain('setHubSession');
    expect(callback).toContain('setUser');
    // It reads the one-time code from the query string.
    expect(callback).toMatch(/route\.query\.code|query\.code/);
    // On failure it must NOT silently swallow — route to login with an error.
    expect(callback).toContain("name: 'login'");
  });

  it('registers the Google callback as a public route before the catch-all #945', () => {
    const router = source('../router/index.ts');
    // Public callback route (no meta.auth), named, registered before the catch-all.
    expect(router).toContain('/auth/google/callback');
    expect(router).toMatch(/name:\s*'google-callback'/);
    expect(router).toContain('GoogleCallbackPage.vue');
  });
});
