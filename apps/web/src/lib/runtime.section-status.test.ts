// Normalización del `status` de una sección del informe de import (enum serde `SectionStatus`
// del runtime Rust). Lo que se prueba aquí no es cosmético: el informe es lo ÚNICO que le dice al
// usuario qué entró y qué no en su hub, así que no puede mentir ni en un sentido ni en el otro.
import { describe, it, expect } from 'vitest';

import { sectionStatusInfo } from './runtime';

describe('sectionStatusInfo · formas serde del enum', () => {
  it('Applied y Skipped llegan como string', () => {
    expect(sectionStatusInfo('Applied')).toEqual({ kind: 'applied' });
    expect(sectionStatusInfo('Skipped')).toEqual({ kind: 'skipped' });
  });

  it('Failed(motivo) llega como objeto y conserva el motivo', () => {
    expect(sectionStatusInfo({ Failed: 'módulo `taxes` no instalado' })).toEqual({
      kind: 'failed',
      reason: 'módulo `taxes` no instalado',
    });
  });

  // ADR-0195 / hub#305: el import DESCARTA las identidades de un bundle `template`. Ese estado es
  // propio —ni «aplicado» ni «lo saltaste tú»— y viaja como `{"Ignored": motivo}`.
  it('Ignored(motivo) NO es un fallo, y arrastra su motivo', () => {
    const motivo = 'una plantilla no aplica identidades: la sección `hub_users` se ha descartado';
    expect(sectionStatusInfo({ Ignored: motivo })).toEqual({ kind: 'ignored', reason: motivo });
  });

  // La razón por la que este test existe: antes de #305 una forma desconocida caía a `failed` con
  // el JSON crudo de motivo. Pintar un ✗ rojo con `{"Ignored":"…"}` delante de un hostelero es
  // exactamente el tipo de informe deshonesto que el resto de esta pantalla evita.
  it('una forma DESCONOCIDA sigue cayendo a fallo, sin inventar un éxito', () => {
    const info = sectionStatusInfo({ Vaporware: 'algo' } as unknown as Record<string, unknown>);
    expect(info.kind).toBe('failed');
  });
});
