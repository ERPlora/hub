import { describe, expect, it } from 'vitest';
import {
  formatBytes,
  toPct,
  upgradeReason,
  shouldPromptUpgrade,
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
    // Contrato corregido (hub#207 diagnóstico): los enteros exactos van SIN «.0», como hace
    // `human_bytes` en el runtime Rust (fmt_decimal recorta el cero sobrante). Antes «10.0 MB».
    expect(formatBytes(10_485_760)).toBe('10 MB');
    expect(formatBytes(1_610_612_736)).toBe('1.5 GB');
    expect(formatBytes(157_286_400)).toBe('150 MB'); // ≥100 MB → sin decimales
    expect(formatBytes(2048)).toBe('2 KB');
    expect(formatBytes(512)).toBe('512 B');
    expect(formatBytes(null)).toBe('—');
    expect(formatBytes(undefined)).toBe('—');
  });

  it('el límite del free tier (96 MiB del cgroup) se muestra como «96 MB», no «96.0 MB»', () => {
    // Valor REAL de prod: memory.max=100663296. «96.0 MB» invita a confundir el límite con el
    // uso («6.4 MB») — la cifra limpia elimina el ruido y queda igual que la del runtime.
    expect(formatBytes(100_663_296)).toBe('96 MB');
    expect(formatBytes(1_073_741_824)).toBe('1 GB');
    expect(formatBytes(6_710_886)).toBe('6.4 MB'); // el uso conserva su decimal significativo
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

// `upgradeLink()` ya no existe y su test se va con ella (hub#479): apuntaba al marketplace de
// planes del SaaS, o sea a una página donde se paga, y enlazar ahí desde dentro de la app es lo que
// rechazan Google Play y Microsoft Store. Que NADIE la reintroduzca lo vigila
// `no-purchase-steering.test.ts`, que es un guard sobre toda la fuente y no sobre esta función.
//
// Lo que sí sigue probado arriba es `upgradeReason()`: saber que el hub roza su techo es útil por sí
// solo, y es lo que el panel ahora dice con palabras en vez de con un botón.
