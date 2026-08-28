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
    // hub#1212 moved the `en → en-GB` / `es-ES` mapping out of every screen and into
    // `formatLocale()` (`lib/format-datetime.ts`), which also passes the BUSINESS timezone. What
    // this page still has to do — and what "localizes billing dates" ever meant — is hand the
    // formatter the locale of the APP instead of letting the browser decide.
    expect(billing).toContain("formatDate(iso, {\n      locale: locale.value,");
    // hub#480 replaced the single `billing.downloadError` here: that sentence only ever fitted the
    // fetch half, and inside the installed app the half that fails is the SAVE. The key now comes
    // from `saveDownloadMessageKey`, which tells "this device has nowhere to put it" — the one the
    // user can act on — apart from a plain failure.
    expect(billing).toContain('toastError(t(saveDownloadMessageKey(error)))');
    // `billing.openBillingPortal` se comprobaba aquí. El botón ya no existe (hub#479): el portal de
    // facturación del SaaS es una superficie de pago, y la app no lleva a ninguna. Lo que esta
    // página sigue haciendo —y es lo que se prueba— es DECIR dónde se gestiona el plan.
    expect(billing).toContain("t('billing.managePlanHint')");
    expect(billing).not.toContain('openExternal');
  });

  it('does not revive stale PIN users or create a fake trusted PIN in demo mode', () => {
    const login = source('LoginPage.vue');
    expect(login).toContain('hubContextReady');
    expect(login).toContain('machineRegistrationRequired');
    // ADR-0159 (cliente fino): dentro del shell el login es EL MISMO que en el navegador —
    // la rama Tauri de enrol de máquina (producto local, ADR-0154) se retiró.
    expect(login).not.toContain('enroll_device');
    expect(login).not.toContain('isTauri()');
    expect(login).toContain('saveTrustedUsers([])');
    expect(login).toContain("role: 'owner'");
    expect(login).toContain('permissions: sess.permissions');
    expect(login).toContain("permissions: ['*']");
    expect(login).toContain("throw new Error('missing runtime session')");
  });

  it('shows a recoverable error instead of disguising a failed cloud catalog as empty', () => {
    const apps = source('AppsPage.vue');
    // hub#1129: the failure is a state of the LIST (`catalogState`), and the banner derives from
    // it — so the banner and the table's empty line can no longer disagree about what happened.
    expect(apps).toContain("catalogState.value = 'error'");
    expect(apps).toContain("const catalogError = computed(() => catalogState.value === 'error')");
    expect(apps).not.toContain('MODULES_DEMO');
    expect(apps).toContain("t('apps.catalogLoadError')");
    expect(apps).toContain('@click="loadCatalog"');
    // And the empty line of the catalogue says which of the three it is, instead of «nothing
    // matches your search» while it loads or after it failed.
    expect(apps).toContain('const catalogEmptyMessage');
    expect(apps).toContain("t('apps.loadingCatalog')");
  });

  it('does not claim that updates were checked when no updater is configured', () => {
    const system = source('SystemPage.vue');
    // Sigue diciendo QUIÉN gestiona las actualizaciones…
    expect(system).toContain("t('system.updatesCloudHint')");
    // …y sigue sin afirmar «estás al día», que sería contar por hecha una comprobación que no
    // existe. El titular pasó de «actualizaciones gestionadas» al historial (hub#564): la frase
    // que faltaba no era quién actualiza, era QUÉ te ha cambiado.
    expect(system).not.toContain("t('system.upToDate')");
    expect(system).toContain("t('system.updateHistory')");
    expect(system).toContain('dataTableLabels(locale.value)');
  });

  it('the update history is read-only: no update control for the hub sneaks back in', () => {
    // El botón «Actualizar» del hub para el dueño se retiró a propósito — contradice ADR-0269, que
    // actualiza siempre y sin preguntar — y ya se quitó de la tarjeta del hub en el SaaS. Esta
    // pantalla es la CONTRAPARTIDA (saber qué cambió), no la vuelta del control: si alguien añade
    // aquí una acción de update, este test se lo dice.
    const system = source('SystemPage.vue');
    expect(system).not.toContain('updateModule');
    expect(system).not.toContain('/api/modules/');
  });
});
