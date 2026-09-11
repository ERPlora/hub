import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';

// Contrato estructural del panel «Plan y límites» (ADR-0154). Igual que `system-tabs.test.ts`,
// se verifica sobre la fuente del componente: garantiza el cableado clave (fetch real, refresco
// en vivo solo-visible, barras de %, dispositivos vs plan y aviso de techo) sin montar Ionic.
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

  // El CTA de upgrade («Ver planes» → marketplace del SaaS) se retiró en hub#479: aterrizaba en una
  // página que cambia el plan con proración sobre la tarjeta guardada, y llevar al pago desde dentro
  // de la app es causa de rechazo en Google Play y Microsoft Store. El AVISO se queda —quien roza el
  // techo tiene que saberlo—; lo que desaparece es la puerta.
  it('avisa del techo del plan sin ofrecer una puerta al pago', () => {
    expect(source).toMatch(/shouldPromptUpgrade|upgradeReason/);
    expect(source).toContain("t('planLimits.upgradeTitle')");
    expect(source).toContain("t('planLimits.upgradeWhere')");
    expect(source).not.toContain('openExternal');
  });

  // hub#1685 — el plan Gratis promete «3 usuarios» y el panel no los enseñaba por ningún sitio:
  // el negocio veía su RAM, su BD y sus dispositivos, pero no cuántas personas le caben. Mismo
  // formato «n / tope» que la tarjeta de dispositivos, que es la que ya funciona.
  it('pinta las personas del hub frente al tope del plan', () => {
    expect(source).toContain('metrics.users');
    expect(source).toContain('maxUsers');
    expect(source).toContain("t('planLimits.users')");
  });

  it('usa el sistema de i18n (namespace planLimits)', () => {
    expect(source).toContain("t('planLimits.");
  });
});
