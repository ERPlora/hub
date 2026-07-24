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
    expect(login).toContain('permissions: sess.permissions');
    expect(login).toContain("permissions: ['*']");
    expect(login).toContain("throw new Error('missing runtime session')");
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
});
