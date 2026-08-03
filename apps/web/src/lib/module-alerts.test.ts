// Tests de la lógica PURA de "alertas de módulo" (estado derivado de RUNTIME, no de configuración).
//
// Contexto: ADR-0067 separó "estado que se autocura" (→ banner del dashboard) de "evento" (→ campana).
// `setup-status.ts` cubre el primer bucket para "módulo sin CONFIGURAR". Este lib cubre el mismo bucket
// para "módulo con BACKLOG en runtime" (p. ej. la cola de contingencia VeriFactu: N facturas sin enviar
// a la AEAT porque no hay conexión). Es estado derivado: se calcula de una query REAL del módulo y se
// cura solo al drenar la cola. NO alimenta la campana (esa es la central de EVENTOS, core diferido).
//
// Aquí se prueba SOLO la evaluación pura (fila + declaración → alerta activa | null). La recolección
// con I/O (correr la query de cada manifest instalado) se prueba/ata aparte, igual que setup-status.
import { describe, it, expect, vi } from 'vitest';

// `module-alerts` importa `module-loader` (para `refreshModuleAlerts`), y ese módulo arrastra la
// cadena de iconos `~icons/…?raw` que el transform de vitest deniega (mismo patrón que
// dashboard-widgets.test.ts). Se stubea la I/O; la unidad que se prueba (`collectModuleAlerts`) es
// pura respecto a esa I/O (recibe los manifests + un runner de query controlados por el test).
vi.mock('./module-loader', () => ({ loadInstalledManifests: vi.fn() }));

import { alertPasses, evaluateAlert, collectModuleAlerts } from './module-alerts';
import type { ModuleAlertDef } from './module-alerts';

// Declaración de ejemplo: la que haría VeriFactu para su cola de contingencia. `when` sobre el nº en
// cola (>0), severidad tomada de la columna `severity` que ya devuelve la query, y ruta a la pantalla.
const CONTINGENCY: ModuleAlertDef = {
  query: 'verifactu.stats.contingency_summary',
  when: { field: 'queued_count', gt: 0 },
  count_field: 'queued_count',
  severity_field: 'severity',
  title: 'Facturas sin enviar a la AEAT',
  route: '/m/verifactu/contingency',
  icon: 'cloud-offline-outline',
  permission: 'verifactu.view_verifactu',
};

describe('alertPasses — evaluación de la condición `when` sobre una fila', () => {
  it('gt: verdadero cuando el valor supera el umbral, falso cuando no', () => {
    expect(alertPasses({ queued_count: 3 }, { field: 'queued_count', gt: 0 })).toBe(true);
    expect(alertPasses({ queued_count: 0 }, { field: 'queued_count', gt: 0 })).toBe(false);
  });

  it('gt: trata strings numéricos y nulos con seguridad (no dispara con 0/""/null)', () => {
    expect(alertPasses({ queued_count: '2' }, { field: 'queued_count', gt: 0 })).toBe(true);
    expect(alertPasses({ queued_count: '0' }, { field: 'queued_count', gt: 0 })).toBe(false);
    expect(alertPasses({ queued_count: null }, { field: 'queued_count', gt: 0 })).toBe(false);
    expect(alertPasses({}, { field: 'queued_count', gt: 0 })).toBe(false);
  });

  it('gte: incluye el umbral', () => {
    expect(alertPasses({ n: 5 }, { field: 'n', gte: 5 })).toBe(true);
    expect(alertPasses({ n: 4 }, { field: 'n', gte: 5 })).toBe(false);
  });

  it('truthy/equals: mismos semánticos que setup-status', () => {
    expect(alertPasses({ broken: 1 }, { field: 'broken', truthy: true })).toBe(true);
    expect(alertPasses({ broken: 0 }, { field: 'broken', truthy: true })).toBe(false);
    expect(alertPasses({ state: 'error' }, { field: 'state', equals: 'error' })).toBe(true);
    expect(alertPasses({ state: 'ok' }, { field: 'state', equals: 'error' })).toBe(false);
  });
});

describe('evaluateAlert — fila de la query + declaración → alerta activa | null', () => {
  it('sin fila (query sin resultados) → null (no se alerta)', () => {
    expect(evaluateAlert('verifactu', undefined, CONTINGENCY)).toBeNull();
  });

  it('condición NO cumplida (cola vacía) → null (se curó solo)', () => {
    expect(evaluateAlert('verifactu', { queued_count: 0, severity: 'info' }, CONTINGENCY)).toBeNull();
  });

  it('condición cumplida → alerta con título, ruta, icono, count y severidad de la columna', () => {
    const alert = evaluateAlert('verifactu', { queued_count: 3, severity: 'warning' }, CONTINGENCY);
    expect(alert).not.toBeNull();
    expect(alert).toMatchObject({
      moduleId: 'verifactu',
      title: 'Facturas sin enviar a la AEAT',
      route: '/m/verifactu/contingency',
      icon: 'cloud-offline-outline',
      severity: 'warning',
      count: 3,
    });
  });

  it('severidad: usa la columna `severity_field`; si trae un valor no válido, cae al literal/def', () => {
    const withLiteral: ModuleAlertDef = { ...CONTINGENCY, severity: 'danger' };
    // severity_field presente pero con basura → cae al literal declarado.
    const a = evaluateAlert('verifactu', { queued_count: 1, severity: 'zzz' }, withLiteral);
    expect(a?.severity).toBe('danger');
  });

  it('severidad por defecto = warning cuando no hay columna ni literal', () => {
    const noSeverity: ModuleAlertDef = { ...CONTINGENCY };
    delete (noSeverity as { severity_field?: string }).severity_field;
    const a = evaluateAlert('verifactu', { queued_count: 1 }, noSeverity);
    expect(a?.severity).toBe('warning');
  });

  it('count omitido cuando no se declara `count_field`', () => {
    const noCount: ModuleAlertDef = { ...CONTINGENCY };
    delete (noCount as { count_field?: string }).count_field;
    const a = evaluateAlert('verifactu', { queued_count: 3, severity: 'warning' }, noCount);
    expect(a?.count).toBeUndefined();
  });

  it('incluye `hint` (subtexto tranquilizador offline-first) cuando se declara; lo omite si no', () => {
    const withHint: ModuleAlertDef = { ...CONTINGENCY, hint: 'El TPV sigue; se envían solas al volver la red.' };
    const a = evaluateAlert('verifactu', { queued_count: 3, severity: 'warning' }, withHint);
    expect(a?.hint).toBe('El TPV sigue; se envían solas al volver la red.');
    const b = evaluateAlert('verifactu', { queued_count: 3, severity: 'warning' }, CONTINGENCY);
    expect(b?.hint).toBeUndefined();
  });

  it('declaración inválida (sin query/route/when) → null (no rompe el dashboard)', () => {
    const bad = { title: 'x' } as unknown as ModuleAlertDef;
    expect(evaluateAlert('verifactu', { queued_count: 3 }, bad)).toBeNull();
  });
});

describe('collectModuleAlerts — recorre manifests instalados, corre la query y evalúa', () => {
  /** Manifest instalado con un array `alerts` (forma que declararía el module.json). */
  function mods(list: Array<{ moduleId: string; alerts?: ModuleAlertDef[] }>) {
    return list.map(({ moduleId, alerts }) => ({ moduleId, manifest: { id: moduleId, alerts } }));
  }

  it('alerta ACTIVA: la query devuelve backlog>0 → una alerta con el contador', async () => {
    const query = vi.fn(async () => [{ queued_count: 3, severity: 'warning' }]);
    const out = await collectModuleAlerts(mods([{ moduleId: 'verifactu', alerts: [CONTINGENCY] }]), { query });
    expect(out).toHaveLength(1);
    expect(out[0]).toMatchObject({ moduleId: 'verifactu', count: 3, severity: 'warning' });
    expect(query).toHaveBeenCalledWith('verifactu.stats.contingency_summary', {});
  });

  it('sin backlog (cola vacía) → ninguna alerta (se curó solo)', async () => {
    const query = vi.fn(async () => [{ queued_count: 0, severity: 'info' }]);
    const out = await collectModuleAlerts(mods([{ moduleId: 'verifactu', alerts: [CONTINGENCY] }]), { query });
    expect(out).toHaveLength(0);
  });

  it('la query falla → se omite esa alerta (best-effort, no rompe el dashboard)', async () => {
    const query = vi.fn(async () => Promise.reject(new Error('boot temprano')));
    const out = await collectModuleAlerts(mods([{ moduleId: 'verifactu', alerts: [CONTINGENCY] }]), { query });
    expect(out).toHaveLength(0);
  });

  it('sin permiso → ni siquiera se corre la query', async () => {
    const query = vi.fn(async () => [{ queued_count: 3 }]);
    const out = await collectModuleAlerts(mods([{ moduleId: 'verifactu', alerts: [CONTINGENCY] }]), {
      query,
      hasPermission: () => false,
    });
    expect(out).toHaveLength(0);
    expect(query).not.toHaveBeenCalled();
  });

  it('permiso desconocido (null) → degradación permisiva: se corre y se muestra', async () => {
    const query = vi.fn(async () => [{ queued_count: 2, severity: 'warning' }]);
    const out = await collectModuleAlerts(mods([{ moduleId: 'verifactu', alerts: [CONTINGENCY] }]), {
      query,
      hasPermission: () => null,
    });
    expect(out).toHaveLength(1);
  });

  it('módulo sin bloque `alerts` → no aporta nada', async () => {
    const query = vi.fn(async () => [{ queued_count: 3 }]);
    const out = await collectModuleAlerts(mods([{ moduleId: 'inventory' }]), { query });
    expect(out).toHaveLength(0);
    expect(query).not.toHaveBeenCalled();
  });

  it('normaliza la forma del motor de listas ({rows:[…]}) además del array plano', async () => {
    const query = vi.fn(async () => ({ rows: [{ queued_count: 5, severity: 'danger' }], total: 5 }));
    const out = await collectModuleAlerts(mods([{ moduleId: 'verifactu', alerts: [CONTINGENCY] }]), { query });
    expect(out).toHaveLength(1);
    expect(out[0]).toMatchObject({ count: 5, severity: 'danger' });
  });

  it('localiza title/hint desde el locale del módulo (clave = query, ADR-0055)', async () => {
    const query = vi.fn(async () => [{ queued_count: 2, severity: 'warning' }]);
    const out = await collectModuleAlerts(
      [
        {
          moduleId: 'verifactu',
          manifest: { alerts: [CONTINGENCY] },
          locale: { alerts: { 'verifactu.stats.contingency_summary': { title: 'Título ES', hint: 'Subtexto ES' } } },
        },
      ],
      { query },
    );
    expect(out[0]).toMatchObject({ title: 'Título ES', hint: 'Subtexto ES' });
  });

  it('sin locale (o sin entrada) usa el título canónico del manifest', async () => {
    const query = vi.fn(async () => [{ queued_count: 2, severity: 'warning' }]);
    const out = await collectModuleAlerts(mods([{ moduleId: 'verifactu', alerts: [CONTINGENCY] }]), { query });
    expect(out[0]?.title).toBe(CONTINGENCY.title);
  });

  it('varias alertas activas: conserva el orden de los módulos', async () => {
    const other: ModuleAlertDef = { ...CONTINGENCY, query: 'other.stats', title: 'Otro backlog', route: '/m/other' };
    const query = vi.fn(async (name: string) =>
      name === 'other.stats' ? [{ queued_count: 1, severity: 'info' }] : [{ queued_count: 2, severity: 'warning' }],
    );
    const out = await collectModuleAlerts(
      mods([
        { moduleId: 'verifactu', alerts: [CONTINGENCY] },
        { moduleId: 'other', alerts: [other] },
      ]),
      { query },
    );
    expect(out.map((a) => a.moduleId)).toEqual(['verifactu', 'other']);
  });
});
