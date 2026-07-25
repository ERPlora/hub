import { describe, expect, it } from 'vitest';
import {
  formatBytes,
  toPct,
  upgradeReason,
  shouldPromptUpgrade,
  upgradeLink,
  type SystemMetrics,
} from './system-metrics';

/** Métricas base (plan free, todo holgado) que cada test ajusta. */
function metrics(over: Partial<SystemMetrics> = {}): SystemMetrics {
  return {
    plan: 'free',
    memory: { usedBytes: 12_582_912, limitBytes: 100_663_296, fraction: 0.125 },
    cpu: { usedCores: 0.02, limitCores: 0.5, fraction: 0.04 },
    database: { engine: 'postgres', sizeBytes: 8_388_608, limitBytes: null, fraction: null },
    sessions: { active: 1, devices: 1, maxDevices: 1 },
    ...over,
  };
}

describe('formatBytes', () => {
  it('humaniza en KB/MB/GB (base 1024) y protege el caso nulo', () => {
    expect(formatBytes(10_485_760)).toBe('10.0 MB');
    expect(formatBytes(1_610_612_736)).toBe('1.5 GB');
    expect(formatBytes(157_286_400)).toBe('150 MB'); // ≥100 MB → sin decimales
    expect(formatBytes(2048)).toBe('2 KB');
    expect(formatBytes(512)).toBe('512 B');
    expect(formatBytes(null)).toBe('—');
    expect(formatBytes(undefined)).toBe('—');
  });
});

describe('toPct', () => {
  it('convierte fracción 0..1 en % entero; null si no medible', () => {
    expect(toPct(0.1256)).toBe(13);
    expect(toPct(1)).toBe(100);
    expect(toPct(null)).toBeNull();
    expect(toPct(undefined)).toBeNull();
  });
});

describe('upgradeReason (solo plan free)', () => {
  it('avisa por RAM al pasar del 80%', () => {
    const r = upgradeReason(metrics({ memory: { usedBytes: 90, limitBytes: 100, fraction: 0.9 } }));
    expect(r).toBe('memory');
  });

  it('avisa por BD al pasar del 80%', () => {
    const r = upgradeReason(
      metrics({ database: { engine: 'postgres', sizeBytes: 90, limitBytes: 100, fraction: 0.85 } }),
    );
    expect(r).toBe('database');
  });

  it('avisa por dispositivos al alcanzar el tope del plan', () => {
    expect(upgradeReason(metrics({ sessions: { active: 1, devices: 1, maxDevices: 1 } }))).toBe('devices');
  });

  it('NO avisa con todo holgado', () => {
    expect(upgradeReason(metrics({ sessions: { active: 1, devices: 0, maxDevices: 1 } }))).toBeNull();
  });

  it('NO avisa en planes de pago aunque roce límites', () => {
    const m = metrics({ plan: 'restaurant', memory: { usedBytes: 99, limitBytes: 100, fraction: 0.99 } });
    expect(upgradeReason(m)).toBeNull();
    expect(shouldPromptUpgrade(m)).toBe(false);
  });

  it('max_devices=0 (ilimitado) nunca dispara el aviso de dispositivos', () => {
    expect(upgradeReason(metrics({ sessions: { active: 5, devices: 5, maxDevices: 0 } }))).toBeNull();
  });
});

describe('upgradeLink', () => {
  it('apunta al marketplace de planes del SaaS con utm del hub', () => {
    const url = upgradeLink();
    expect(url).toContain('/dashboard/marketplace/plans/');
    expect(url).toContain('utm_source=hub');
  });
});
