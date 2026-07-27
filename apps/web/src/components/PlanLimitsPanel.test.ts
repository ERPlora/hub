import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';

// Contrato estructural del panel «Plan y límites» (ADR-0154). Igual que `system-tabs.test.ts`,
// se verifica sobre la fuente del componente: garantiza el cableado clave (fetch real, refresco
// en vivo solo-visible, barras de %, dispositivos vs plan y CTA de upgrade) sin montar Ionic.
const source = readFileSync(new URL('./PlanLimitsPanel.vue', import.meta.url), 'utf8');

describe('PlanLimitsPanel', () => {
  it('consume el endpoint real de métricas del runtime', () => {
    expect(source).toContain("from '../lib/system-metrics'");
    expect(source).toContain('fetchSystemMetrics');
  });

  it('refresca en vivo con polling ligero SOLO mientras la página es visible', () => {
    expect(source).toContain('visibilitychange');
    expect(source).toContain('setInterval');
    expect(source).toContain('clearInterval');
    expect(source).toMatch(/5000|5_000/); // 5 s
  });

  it('pinta el uso con barras de % y muestra los dispositivos frente al tope del plan', () => {
    expect(source).toContain('ion-progress-bar');
    expect(source).toContain('sessions');
    expect(source).toContain('maxDevices');
  });

  it('pinta la BD frente a la cuota del entitlement y conserva el estado sin límite', () => {
    expect(source).toContain('metrics.database.fraction');
    expect(source).toContain('metrics.database.limitBytes');
    expect(source).toContain('usageLabel(metrics.database.sizeBytes, metrics.database.limitBytes)');
    expect(source).toContain("t('planLimits.dbNoQuota')");
  });

  it('ofrece el CTA de upgrade (gated) con deep-link externo al SaaS', () => {
    expect(source).toMatch(/shouldPromptUpgrade|upgradeReason/);
    expect(source).toContain('upgradeLink');
    expect(source).toContain('openExternal');
  });

  it('usa el sistema de i18n (namespace planLimits)', () => {
    expect(source).toContain("t('planLimits.");
  });
});
