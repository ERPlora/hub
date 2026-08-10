// TDD (hub#564): qué enseña el historial de actualizaciones, y qué NO.
//
// Actualizamos solos, sin preguntar (ADR-0269). La contrapartida es que el dueño pueda SABER qué le
// hemos cambiado. Lo que decide si esa pantalla vale algo no es que pinte una lista: es que solo
// aparezca lo que cambió, que cada línea diga **de → a**, y que un día sin cambios no exista.
import { describe, expect, it } from 'vitest';

import {
  groupByDay,
  versionJump,
  type UpdateHistoryEntry,
} from './update-history';

// Las fechas se construyen en hora LOCAL, no con literales `…Z`. Agrupar por día es una pregunta
// sobre el huso del dueño («¿qué me cambiasteis ayer?»), así que un instante UTC fijo cae en un día
// distinto según dónde corra el test — y un test que depende del huso de quien lo ejecuta no prueba
// el agrupado, prueba la máquina.
const at = (year: number, month: number, day: number, hour: number, minute = 0): string =>
  new Date(year, month - 1, day, hour, minute).toISOString();

const TODAY = at(2026, 8, 10, 3, 14);
const YESTERDAY = at(2026, 8, 9, 22, 0);
const LAST_WEEK = at(2026, 8, 2, 4, 2);

const entry = (over: Partial<UpdateHistoryEntry> = {}): UpdateHistoryEntry => ({
  component: 'module',
  id: 'inventory',
  name: 'Inventario',
  from: '1.1.1',
  to: '1.1.2',
  outcome: 'updated',
  reason: '',
  at: TODAY,
  ...over,
});

describe('versionJump', () => {
  it('says where it came from, not just where it is', () => {
    // «Inventario 1.1.2» no dice nada; «1.1.1 → 1.1.2» sí. Es la regla 2 de la issue y la primera
    // pregunta de cualquier incidencia.
    expect(versionJump(entry())).toBe('1.1.1 → 1.1.2');
  });

  it('una vuelta atrás se lee igual de bien: la flecha apunta a donde acabó', () => {
    expect(versionJump(entry({ from: '1.1.2', to: '1.1.1', outcome: 'rolled_back' }))).toBe(
      '1.1.2 → 1.1.1',
    );
  });

  it('si el módulo se perdió no se inventa una versión de destino', () => {
    // `to` vacío = no hay nada corriendo. Escribir una versión ahí sería mentir en la única
    // pantalla que existe para no mentir.
    expect(versionJump(entry({ from: '1.1.2', to: '', outcome: 'lost' }))).toBe('1.1.2');
  });
});

describe('groupByDay', () => {
  const now = new Date(2026, 7, 10, 10, 0);

  it('agrupa por día y pone el más reciente arriba', () => {
    const groups = groupByDay(
      [
        entry({ at: TODAY, id: 'inventory' }),
        entry({ at: at(2026, 8, 10, 3, 15), id: 'hub', component: 'hub', name: 'ERPlora' }),
        entry({ at: LAST_WEEK, id: 'sales', name: 'Ventas' }),
      ],
      now,
      'es-ES',
    );

    expect(groups).toHaveLength(2);
    expect(groups[0].entries).toHaveLength(2);
    expect(groups[1].entries).toHaveLength(1);
    expect(groups[1].entries[0].id).toBe('sales');
  });

  it('un día sin cambios NO existe: no hay hueco ni fila de «sin cambios»', () => {
    // Regla 1, la que carga con la mitad del valor. Entre el 2 y el 10 de agosto no pasó nada, y
    // esos ocho días no son ocho filas vacías: son nada.
    const groups = groupByDay(
      [entry({ at: TODAY }), entry({ at: LAST_WEEK })],
      now,
      'es-ES',
    );

    expect(groups.map((g) => g.key)).toEqual(['2026-08-10', '2026-08-02']);
  });

  it('sin entradas no hay grupos (un hub sin actualizar no enseña una lista)', () => {
    expect(groupByDay([], now, 'es-ES')).toEqual([]);
  });

  it('el día de hoy y el de ayer se nombran, no se fechan', () => {
    // «Hoy» es lo que alguien busca cuando algo dejó de funcionar esta mañana. Una fecha completa
    // obliga a traducirla mentalmente.
    const groups = groupByDay(
      [entry({ at: TODAY }), entry({ at: YESTERDAY })],
      now,
      'es-ES',
    );

    expect(groups[0].isToday).toBe(true);
    expect(groups[1].isYesterday).toBe(true);
    expect(groups[1].isToday).toBe(false);
  });

  it('una entrada más vieja que hoy y ayer trae su fecha ya formateada', () => {
    const groups = groupByDay([entry({ at: LAST_WEEK })], now, 'es-ES');

    expect(groups[0].isToday).toBe(false);
    expect(groups[0].isYesterday).toBe(false);
    expect(groups[0].label).not.toBe('');
  });

  it('una fecha que no se puede leer NUNCA se pinta como «Invalid Date»', () => {
    // Salió en el QA de pantalla: una fila con un `at` que `new Date` no sabe parsear pintaba
    // literalmente «Invalid Date» como título del día y como hora de la línea. En la única
    // pantalla que existe para no mentirle al dueño, eso es basura con aspecto de dato.
    // El hecho —«esto cambió, de aquí a aquí»— sigue siendo cierto aunque el instante no se
    // pueda leer, así que la entrada se conserva y lo que se calla es la hora.
    const groups = groupByDay([entry({ at: 'no-es-una-fecha' })], now, 'es-ES');

    expect(groups).toHaveLength(1);
    expect(groups[0].entries).toHaveLength(1);
    expect(groups[0].label).not.toMatch(/invalid/i);
    expect(groups[0].entries[0].time).not.toMatch(/invalid/i);
    expect(groups[0].entries[0].time).toBe('');
    expect(groups[0].isToday).toBe(false);
    expect(groups[0].isYesterday).toBe(false);
  });

  it('cada entrada conserva su hora: dos cambios el mismo día no se funden en uno', () => {
    const groups = groupByDay(
      [entry({ at: at(2026, 8, 10, 9, 30) }), entry({ at: TODAY })],
      now,
      'es-ES',
    );

    expect(groups).toHaveLength(1);
    expect(groups[0].entries.map((e) => e.time)).toHaveLength(2);
    expect(groups[0].entries[0].time).not.toBe(groups[0].entries[1].time);
  });
});
